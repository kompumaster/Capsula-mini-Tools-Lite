"""ODAS: приём JSON `tracks` и направление на источник.

Только логика сети и разбора: TCP-сервер, поток JSON без
разделителей, вычисление азимута/возвышения. Запуск самого
`odaslive` — в `hal_odas`.
"""

import json
import math
import select
import socket
import struct
import time

from micro_hal.hal_common import HalError

__all__ = [
    "HOST", "PORT", "POT_PORT", "SEPARATED_PORT", "POSTFILTERED_PORT",
    "CATEGORY_PORT",
    "parse_stream", "direction", "Server", "AudioServer",
]

HOST = "127.0.0.1"
PORT = 9000
POT_PORT = 9001
SEPARATED_PORT = 9002
POSTFILTERED_PORT = 9003
CATEGORY_PORT = 9004

_POLL_IN = getattr(select, "POLLIN", 1)
_POLL_HUP = getattr(select, "POLLHUP", 0)
_POLL_ERR = getattr(select, "POLLERR", 0)


def _fd(obj):
    if hasattr(obj, "fileno"):
        return obj.fileno()
    return obj


def _nonblocking(sock):
    try:
        sock.setblocking(False)
    except AttributeError:
        sock.settimeout(0)


def parse_stream(data, buffer=b""):
    """Выделить JSON-объекты из TCP-потока.

    Возвращает `(objects, remainder)`: готовые объекты и хвост
    незавершённого объекта. Скобки внутри строк не считаются.
    """
    data = buffer + data
    objects = []
    start = None
    depth = 0
    in_string = False
    escape = False
    for index, byte in enumerate(data):
        if start is None:
            if byte == 123:            # {
                start = index
                depth = 1
            continue
        if in_string:
            if escape:
                escape = False
            elif byte == 92:           # backslash
                escape = True
            elif byte == 34:           # quote
                in_string = False
            continue
        if byte == 34:                 # quote
            in_string = True
        elif byte == 123:              # {
            depth += 1
        elif byte == 125:              # }
            depth -= 1
            if depth == 0:
                chunk = data[start:index + 1]
                try:
                    objects.append(json.loads(chunk.decode()))
                except (ValueError, UnicodeError) as exc:
                    raise HalError("ODAS: плохой JSON: {}".format(exc))
                start = None
    remainder = data[start:] if start is not None else b""
    return objects, remainder


def direction(track, energy_key="activity"):
    """Азимут/возвышение одного трека ODAS.

    Азимут: 0° — перед (+Y), +90° — справа (+X), −90° — слева.
    `energy_key` — `"activity"` для tracks, `"E"` для pots.
    """
    x = float(track.get("x", 0.0))
    y = float(track.get("y", 0.0))
    z = float(track.get("z", 0.0))
    horizontal = math.sqrt(x * x + y * y)
    if horizontal == 0.0 and z == 0.0:
        azimuth = 0.0
        elevation = 0.0
    else:
        azimuth = math.atan2(x, y) * 180.0 / math.pi
        elevation = math.atan2(z, horizontal) * 180.0 / math.pi
    return {
        "azimuth": azimuth,
        "elevation": elevation,
        "activity": float(track.get(energy_key, 0.0)),
        "id": track.get("id"),
    }


class Server:
    """TCP-сервер для JSON `tracks` от `odaslive`."""

    def __init__(self, host=HOST, port=PORT, energy_key="activity"):
        self.host = host
        self.port = port
        self.energy_key = energy_key
        self._sock = None
        self._client = None
        self._client_fd = None
        self._poller = None
        self._input = b""
        self._latest = []
        self._frame = None
        self._frames = 0

    def listen(self):
        """Открыть порт; ODAS подключается как клиент."""
        if self._sock is not None:
            return
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,
                            struct.pack("i", 1))
            address = socket.getaddrinfo(self.host, self.port)[0][4]
            sock.bind(address)
            sock.listen(1)
            _nonblocking(sock)
        except OSError as exc:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            raise HalError(
                "ODAS: не открыть порт {}: {}".format(self.port, exc))
        if hasattr(sock, "getsockname"):
            name = sock.getsockname()
            if isinstance(name, tuple):
                self.port = name[1]
            elif isinstance(name, (bytes, bytearray)) and len(name) >= 4:
                self.port = (name[2] << 8) | name[3]
        self._sock = sock
        self._poller = select.poll()
        self._poller.register(sock, _POLL_IN)

    def _close_client(self):
        if self._client is None:
            return
        try:
            self._poller.unregister(self._client)
        except Exception:
            pass
        try:
            self._client.close()
        finally:
            self._client = None
            self._client_fd = None
            self._input = b""

    def close(self):
        self._close_client()
        if self._sock is not None:
            try:
                self._poller.unregister(self._sock)
            except Exception:
                pass
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._poller = None

    def _accept(self):
        try:
            client, _address = self._sock.accept()
        except OSError:
            return
        self._close_client()
        _nonblocking(client)
        self._client = client
        self._client_fd = client.fileno()
        self._poller.register(client, _POLL_IN)

    def poll(self, timeout_ms=0):
        """Принять новые данные; вернуть список разобранных кадров."""
        if self._sock is None:
            raise HalError("ODAS: сервер не слушает")
        events = self._poller.poll(max(0, int(timeout_ms)))
        objects = []
        for event, mask in events:
            fd = _fd(event)
            if fd == self._sock.fileno():
                if mask & _POLL_IN:
                    self._accept()
                continue
            if self._client is None or fd != self._client_fd:
                continue
            if mask & (_POLL_HUP | _POLL_ERR):
                self._close_client()
                continue
            if not (mask & _POLL_IN):
                continue
            try:
                data = self._client.recv(4096)
            except OSError:
                data = b""
            if not data:
                self._close_client()
                continue
            objects.extend(self._read(data))
        return objects

    def _read(self, data):
        frames, self._input = parse_stream(data, self._input)
        for frame in frames:
            self._frames += 1
            self._frame = frame
            if "src" in frame:
                self._latest = frame["src"]
        return frames

    def latest(self):
        """Последний список треков."""
        return list(self._latest)

    def tracks(self):
        """То же, что `latest()`."""
        return self.latest()

    def potentials(self):
        """То же для `pots`."""
        return self.latest()

    def direction(self):
        """Направление на самый активный трек/потенциал или None."""
        tracks = self._latest
        if not tracks:
            return None
        best = tracks[0]
        for track in tracks[1:]:
            if float(track.get(self.energy_key, 0.0)) > float(
                    best.get(self.energy_key, 0.0)):
                best = track
        return direction(best, self.energy_key)

    def frames(self):
        """Сколько JSON-кадров принято."""
        return self._frames

    def latest_frame(self):
        """Последний JSON-кадр целиком или None."""
        return self._frame

    def timestamp(self):
        """`timeStamp` последнего кадра или None."""
        frame = self._frame
        return None if frame is None else frame.get("timeStamp")

    def categories(self):
        """То же, что `latest()` для classify."""
        return self.latest()

    def read(self, timeout_ms=0):
        """Дождаться нового кадра и вернуть его или None."""
        start = self._frames
        self.poll(timeout_ms)
        if self._frames > start:
            return self._frame
        return None

    def wait(self, timeout_ms=1000):
        """Ждать новый кадр до таймаута."""
        start = self._frames
        deadline = time.time() + max(0, int(timeout_ms)) / 1000.0
        while True:
            self.poll(50)
            if self._frames > start:
                return self._frame
            if time.time() >= deadline:
                return None

    def reset(self):
        """Забыть буфер и последние данные."""
        self._input = b""
        self._latest = []
        self._frame = None
        self._frames = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class AudioServer:
    """TCP-сервер для PCM `separated`/`postfiltered` от ODAS.

    ODAS шлёт фиксированные чанки:
    `hop × channels × width` байт, без заголовков.
    """

    def __init__(self, host=HOST, port=SEPARATED_PORT,
                 channels=4, hop=128, width=2):
        self.host = host
        self.port = port
        self.channels = int(channels)
        self.hop = int(hop)
        self.width = int(width)
        self.chunk_size = self.channels * self.hop * self.width
        if self.chunk_size <= 0:
            raise HalError("ODAS: неверный размер аудиочанка")
        self._sock = None
        self._client = None
        self._client_fd = None
        self._poller = None
        self._input = b""
        self._latest = b""
        self._pending = []
        self._count = 0

    def listen(self):
        if self._sock is not None:
            return
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,
                            struct.pack("i", 1))
            address = socket.getaddrinfo(self.host, self.port)[0][4]
            sock.bind(address)
            sock.listen(1)
            _nonblocking(sock)
        except OSError as exc:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            raise HalError(
                "ODAS: не открыть порт {}: {}".format(self.port, exc))
        if hasattr(sock, "getsockname"):
            name = sock.getsockname()
            if isinstance(name, tuple):
                self.port = name[1]
            elif isinstance(name, (bytes, bytearray)) and len(name) >= 4:
                self.port = (name[2] << 8) | name[3]
        self._sock = sock
        self._poller = select.poll()
        self._poller.register(sock, _POLL_IN)

    def _close_client(self):
        if self._client is None:
            return
        try:
            self._poller.unregister(self._client)
        except Exception:
            pass
        try:
            self._client.close()
        finally:
            self._client = None
            self._client_fd = None
            self._input = b""

    def close(self):
        self._close_client()
        if self._sock is not None:
            try:
                self._poller.unregister(self._sock)
            except Exception:
                pass
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._poller = None

    def _accept(self):
        try:
            client, _address = self._sock.accept()
        except OSError:
            return
        self._close_client()
        _nonblocking(client)
        self._client = client
        self._client_fd = client.fileno()
        self._poller.register(client, _POLL_IN)

    def _read(self, data):
        self._input += data
        chunks = []
        while len(self._input) >= self.chunk_size:
            chunk = self._input[:self.chunk_size]
            self._input = self._input[self.chunk_size:]
            self._latest = chunk
            self._count += 1
            chunks.append(chunk)
        return chunks

    def poll(self, timeout_ms=0):
        if self._sock is None:
            raise HalError("ODAS: аудиосервер не слушает")
        events = self._poller.poll(max(0, int(timeout_ms)))
        chunks = []
        for event, mask in events:
            fd = _fd(event)
            if fd == self._sock.fileno():
                if mask & _POLL_IN:
                    self._accept()
                continue
            if self._client is None or fd != self._client_fd:
                continue
            if mask & (_POLL_HUP | _POLL_ERR):
                self._close_client()
                continue
            if not (mask & _POLL_IN):
                continue
            try:
                data = self._client.recv(8192)
            except OSError:
                data = b""
            if not data:
                self._close_client()
                continue
            chunks.extend(self._read(data))
        return chunks

    def latest(self):
        """Последний чанк PCM или b""."""
        return self._latest

    def channel(self, index, chunk=None):
        """Один источник из чанка (`bytes`); `None` — из последнего.

        В MicroPython нет среза с шагом, поэтому копируем побайтово:
        на чанк 128 кадров это ~256 операций, при 125 чанках/с
        незаметно.
        """
        index = int(index)
        if index < 0 or index >= self.channels:
            raise HalError("ODAS: нет канала {}".format(index))
        data = self._latest if chunk is None else chunk
        step = self.channels * 2
        if len(data) < step:
            raise HalError("ODAS: пустой чанк")
        out = bytearray(len(data) // self.channels)
        target = 0
        offset = index * 2
        while offset + 1 < len(data):
            out[target] = data[offset]
            out[target + 1] = data[offset + 1]
            target += 2
            offset += step
        return bytes(out)

    def split(self, chunk=None):
        """Разложить чанк на каналы: список `bytes` (для отладки)."""
        data = self._latest if chunk is None else chunk
        return [self.channel(index, data)
                for index in range(self.channels)]

    @staticmethod
    def pick(tracks, energy_key="activity"):
        """Индекс канала с самой большой активностью."""
        best = 0
        value = None
        for index, track in enumerate(tracks):
            level = float(track.get(energy_key, 0.0))
            if value is None or level > value:
                best = index
                value = level
        return best

    def count(self):
        """Сколько чанков принято."""
        return self._count

    def frames(self):
        """Алиас `count()`."""
        return self._count

    def read(self, timeout_ms=0):
        """Вернуть следующий PCM-чанк или None."""
        if self._pending:
            return self._pending.pop(0)
        chunks = self.poll(timeout_ms)
        if not chunks:
            return None
        self._pending.extend(chunks[1:])
        return chunks[0]

    def wait(self, timeout_ms=1000):
        """Ждать следующий чанк до таймаута."""
        deadline = time.time() + max(0, int(timeout_ms)) / 1000.0
        while True:
            chunk = self.read(50)
            if chunk is not None:
                return chunk
            if time.time() >= deadline:
                return None

    def reset(self):
        """Забыть буфер и последние данные."""
        self._input = b""
        self._latest = b""
        self._pending = []
        self._count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
