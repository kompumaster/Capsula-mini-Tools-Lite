"""Минимальный WebSocket-клиент для Edge TTS.

Поддерживает ws/wss, текстовые/бинарные кадры, ping/pong и close.
Без aiohttp и без permessage-deflate.
"""

import os
import socket
import ssl
import struct

from micro_tts.errors import TtsError
from micro_tts.net.base import Transport

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# Разумные пределы: Edge присылает небольшие кадры.
MAX_FRAME = 1 << 20
MAX_MESSAGE = 4 << 20


def parse_url(url):
    """`ws/wss://host[:port]/path` → `(secure, host, port, path)`."""
    if not isinstance(url, str):
        raise TtsError("URL должен быть строкой")
    if url.startswith("wss://"):
        secure = True
        rest = url[6:]
        default_port = 443
    elif url.startswith("ws://"):
        secure = False
        rest = url[5:]
        default_port = 80
    else:
        raise TtsError("URL должен начинаться с ws:// или wss://")
    if "/" in rest:
        authority, tail = rest.split("/", 1)
        path = "/" + tail
    else:
        authority = rest
        path = "/"
    if not authority:
        raise TtsError("пустой хост в URL")
    if authority.startswith("["):
        end = authority.find("]")
        if end < 0:
            raise TtsError("неверный IPv6-хост")
        host = authority[1:end]
        rest = authority[end + 1:]
        if rest.startswith(":"):
            try:
                port = int(rest[1:])
            except ValueError:
                raise TtsError("неверный порт в URL")
        elif rest:
            raise TtsError("неверный хост в URL")
        else:
            port = default_port
    elif ":" in authority:
        host, text = authority.rsplit(":", 1)
        try:
            port = int(text)
        except ValueError:
            raise TtsError("неверный порт в URL")
    else:
        host = authority
        port = default_port
    if not host:
        raise TtsError("пустой хост в URL")
    if port < 1 or port > 65535:
        raise TtsError("неверный порт в URL")
    return secure, host, port, path


def _random_bytes(count):
    try:
        return os.urandom(count)
    except AttributeError:
        import random
        data = bytearray(count)
        for index in range(count):
            data[index] = random.getrandbits(8)
        return bytes(data)


def _b64(data):
    try:
        import binascii
    except ImportError:
        import ubinascii as binascii
    value = binascii.b2a_base64(data).strip()
    if isinstance(value, bytes):
        value = value.decode("ascii")
    return value


def _accept(key):
    """`Sec-WebSocket-Accept` для отправленного ключа."""
    try:
        import hashlib
    except ImportError:
        raise TtsError("WebSocket: нет hashlib для проверки handshake")
    digest = hashlib.sha1((key + GUID).encode("ascii")).digest()
    return _b64(digest)


class WebSocketTransport(Transport):
    def __init__(self, connector=None):
        self._connector = connector
        self._sock = None
        self._buffer = b""
        self.url = None

    def connect(self, url, headers=None, timeout=10.0):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buffer = b""
        secure, host, port, path = parse_url(url)
        try:
            if self._connector is not None:
                sock = self._connector(host, port, timeout)
            else:
                try:
                    sock = socket.create_connection((host, port), timeout)
                except AttributeError:
                    infos = socket.getaddrinfo(host, port)
                    if not infos:
                        raise TtsError(
                            "WebSocket: не разрешить {}".format(host))
                    chosen = infos[0]
                    for info in infos:
                        if info[0] == socket.AF_INET:
                            chosen = info
                            break
                    sock = socket.socket(chosen[0], chosen[1], chosen[2])
                    sock.settimeout(timeout)
                    sock.connect(chosen[4])
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("WebSocket: {}".format(exc))
        try:
            if secure:
                try:
                    context = ssl.create_default_context()
                    sock = context.wrap_socket(
                        sock, server_hostname=host)
                except AttributeError:
                    sock = ssl.wrap_socket(
                        sock, server_hostname=host)
            key = _b64(_random_bytes(16))
            host_header = host
            if ":" in host:
                host_header = "[{}]".format(host)
            default_port = 443 if secure else 80
            if port != default_port:
                host_header += ":{}".format(port)
            lines = [
                "GET {} HTTP/1.1".format(path),
                "Host: {}".format(host_header),
                "Upgrade: websocket",
                "Connection: Upgrade",
                "Sec-WebSocket-Key: {}".format(key),
                "Sec-WebSocket-Version: 13",
            ]
            for name, value in (headers or {}).items():
                text = str(value)
                if "\r" in text or "\n" in text:
                    raise TtsError("неверный заголовок {}".format(name))
                lines.append("{}: {}".format(name, text))
            request = "\r\n".join(lines) + "\r\n\r\n"
            sock.sendall(request.encode("utf-8"))
            response = b""
            while b"\r\n\r\n" not in response:
                chunk = sock.recv(4096)
                if not chunk:
                    raise TtsError("WebSocket: соединение закрыто")
                response += chunk
                if len(response) > 16384:
                    raise TtsError("WebSocket: слишком большой ответ")
            head, tail = response.split(b"\r\n\r\n", 1)
            self._buffer = tail
            head_lines = head.split(b"\r\n")
            status = head_lines[0].decode("ascii", "replace")
            if " 101 " not in status:
                raise TtsError("WebSocket: {}".format(status))
            received_headers = {}
            for line in head_lines[1:]:
                if b":" in line:
                    name, value = line.split(b":", 1)
                    received_headers[name.strip().lower()] = value.strip()
            upgrade = received_headers.get(b"upgrade", b"").lower()
            if upgrade != b"websocket":
                raise TtsError("WebSocket: нет Upgrade: websocket")
            connection = received_headers.get(b"connection", b"").lower()
            if b"upgrade" not in connection:
                raise TtsError("WebSocket: нет Connection: Upgrade")
            received = received_headers.get(b"sec-websocket-accept")
            if received is None:
                raise TtsError("WebSocket: нет Sec-WebSocket-Accept")
            try:
                received = received.decode("ascii")
            except Exception:
                raise TtsError("WebSocket: неверный Sec-WebSocket-Accept")
            if received != _accept(key):
                raise TtsError("WebSocket: неверный Sec-WebSocket-Accept")
        except Exception as exc:
            self._buffer = b""
            try:
                sock.close()
            except Exception:
                pass
            if isinstance(exc, TtsError):
                raise
            raise TtsError("WebSocket: {}".format(exc))
        self._sock = sock
        self.url = url
        return self

    def _send_frame(self, opcode, payload):
        if self._sock is None:
            raise TtsError("WebSocket не подключён")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        mask = _random_bytes(4)
        header = bytearray()
        header.append(0x80 | opcode)
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4]
                       for index, byte in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def _recv_exact(self, size):
        data = self._buffer[:size]
        if len(data) == size:
            self._buffer = self._buffer[size:]
            return data
        self._buffer = b""
        while len(data) < size:
            chunk = self._sock.recv(size - len(data))
            if not chunk:
                raise TtsError("WebSocket: соединение закрыто")
            data += chunk
        return data

    def _recv_frame(self):
        if self._sock is None:
            raise TtsError("WebSocket не подключён")
        first, second = self._recv_exact(2)
        if first & 0x70:
            raise TtsError("WebSocket: RSV без расширения")
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        if opcode in (3, 4, 5, 6, 7, 11, 12, 13, 14, 15):
            raise TtsError("WebSocket: неизвестный opcode {}".format(opcode))
        masked = bool(second & 0x80)
        length = second & 0x7F
        if opcode >= 8:
            if not fin:
                raise TtsError("WebSocket: control-кадр без FIN")
            if length > 125:
                raise TtsError("WebSocket: control-кадр слишком длинный")
        elif length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        if opcode < 8 and length > MAX_FRAME:
            raise TtsError("WebSocket: кадр больше {}".format(MAX_FRAME))
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4]
                            for index, byte in enumerate(payload))
        return fin, opcode, payload

    def _recv_message(self):
        fragments = []
        message_opcode = None
        total = 0
        while True:
            fin, opcode, payload = self._recv_frame()
            if opcode == 9:
                self._send_frame(10, payload)
                continue
            if opcode == 10:
                continue
            if opcode == 8:
                return 8, payload
            if opcode in (1, 2):
                if message_opcode is not None:
                    raise TtsError(
                        "WebSocket: новый кадр во время фрагментации")
                message_opcode = opcode
                fragments = [payload]
                total = len(payload)
                if fin:
                    return message_opcode, b"".join(fragments)
                continue
            if opcode == 0:
                if message_opcode is None:
                    raise TtsError("WebSocket: continuation без начала")
                fragments.append(payload)
                total += len(payload)
                if total > MAX_MESSAGE:
                    raise TtsError(
                        "WebSocket: сообщение больше {}".format(MAX_MESSAGE))
                if fin:
                    return message_opcode, b"".join(fragments)
                continue
            raise TtsError("WebSocket: неизвестный opcode {}".format(opcode))

    def send_text(self, text):
        self._send_frame(1, text)

    def send_binary(self, data):
        self._send_frame(2, data)

    def recv(self, timeout=None):
        if self._sock is None:
            raise TtsError("WebSocket не подключён")
        if timeout is not None:
            try:
                self._sock.settimeout(timeout)
            except AttributeError:
                pass
        try:
            opcode, payload = self._recv_message()
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("WebSocket: {}".format(exc))
        if opcode == 1:
            return "text", payload
        if opcode == 2:
            return "binary", payload
        return "close", payload

    def close(self):
        if self._sock is None:
            self._buffer = b""
            return
        try:
            self._send_frame(8, b"")
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass
        finally:
            self._sock = None
            self._buffer = b""
