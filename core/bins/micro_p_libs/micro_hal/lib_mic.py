"""Микрофоны: WAV, уровни и моно поверх `hal_mic`.

Только логика: заголовок WAV, RMS/пик, смесь каналов и запись файла.
Сырой PCM берётся у `hal_mic`. Большие файлы обрабатываются кусками.
"""

import math
import os
import struct
import time

from micro_hal import hal_common, hal_mic, lib_wav
from micro_hal.hal_common import HalError

__all__ = [
    "RATE", "CHANNELS", "WIDTH", "RAW", "RING_SECONDS", "SILENCE_DBFS",
    "wav_header", "record", "level", "levels", "peak", "mono", "dbfs",
    "MicStream", "Odas", "open_odas", "close_odas", "wait_ready",
    "direction", "tracks", "separate",
]

RATE = 16000
CHANNELS = 4
WIDTH = 2
RAW = "/tmp/micro_hal_mic.{}.raw".format(hal_common.self_pid())

CHUNK = 4096
RING_SECONDS = 2.0
SILENCE_DBFS = -120.0


def _size(path):
    try:
        return os.stat(str(path))[6]
    except OSError as exc:
        raise HalError("нет файла {}: {}".format(path, exc))


def wav_header(data_size, channels=CHANNELS, rate=RATE, width=WIDTH):
    """Заголовок WAV PCM; умолчания — микрофонные (см. `lib_wav`)."""
    return lib_wav.wav_header(data_size, channels=channels, rate=rate,
                              width=width)


def record(path, seconds, source=hal_mic.SOURCE, channels=CHANNELS,
           rate=RATE):
    """Записать WAV и вернуть путь; временный raw удаляется."""
    path = str(path)
    if path == RAW:
        raise HalError("путь WAV не должен совпадать с временным raw")
    channels = int(channels)
    rate = int(rate)
    try:
        hal_mic.capture(RAW, seconds, source=source,
                        channels=channels, rate=rate)
        size = _size(RAW)
        header = wav_header(size, channels, rate, WIDTH)
        try:
            out = open(path, "wb")
        except OSError as exc:
            raise HalError("не открыть {}: {}".format(path, exc))
        try:
            out.write(header)
            source_file = open(RAW, "rb")
            try:
                while True:
                    chunk = source_file.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
            finally:
                source_file.close()
        finally:
            out.close()
    finally:
        try:
            os.remove(RAW)
        except OSError:
            pass
    return path


def _chunks(data, channels=1):
    total = len(data) // 2
    offset = 0
    while offset < total:
        size = min(CHUNK, total - offset)
        if channels > 1 and size % channels:
            size -= size % channels
            if size <= 0:
                size = total - offset
        values = struct.unpack(
            "<%dh" % size, data[offset * 2:(offset + size) * 2])
        yield offset, values
        offset += size


def level(data, channels=CHANNELS):
    """Общий RMS 0…1."""
    channels = int(channels)
    if channels <= 0:
        raise HalError("channels должен быть больше нуля")
    power = 0
    count = 0
    for _offset, values in _chunks(data, channels):
        for value in values:
            power += value * value
        count += len(values)
    if count == 0:
        return 0.0
    return (power / count) ** 0.5 / 32768.0


def levels(data, channels=CHANNELS):
    """RMS по каждому каналу 0…1."""
    channels = int(channels)
    if channels <= 0:
        raise HalError("channels должен быть больше нуля")
    power = [0] * channels
    count = [0] * channels
    for offset, values in _chunks(data):
        for index in range(len(values)):
            channel = (offset + index) % channels
            value = values[index]
            power[channel] += value * value
            count[channel] += 1
    result = []
    for channel in range(channels):
        if count[channel] == 0:
            result.append(0.0)
        else:
            result.append(
                (power[channel] / count[channel]) ** 0.5 / 32768.0)
    return result


def peak(data, channels=CHANNELS):
    """Максимальный модуль сэмпла 0…1."""
    channels = int(channels)
    if channels <= 0:
        raise HalError("channels должен быть больше нуля")
    maximum = 0
    for _offset, values in _chunks(data, channels):
        for value in values:
            absolute = abs(value)
            if absolute > maximum:
                maximum = absolute
    return maximum / 32768.0


def mono(data, channels=CHANNELS):
    """Смешать каналы в моно s16le."""
    channels = int(channels)
    if channels <= 0:
        raise HalError("channels должен быть больше нуля")
    if channels == 1:
        return bytes(data[:len(data) // 2 * 2])
    out = bytearray()
    for _offset, values in _chunks(data, channels):
        frames = len(values) // channels
        for frame in range(frames):
            base = frame * channels
            total = 0
            for channel in range(channels):
                total += values[base + channel]
            out.extend(struct.pack("<h", int(total / channels)))
    return bytes(out)


def dbfs(rms_value, full_scale=32768.0):
    """Значение RMS → dBFS; 0 и меньше — `SILENCE_DBFS`."""
    rms_value = float(rms_value)
    if rms_value <= 0:
        return SILENCE_DBFS
    return 20.0 * math.log10(rms_value / float(full_scale))


class MicStream:
    """Непрерывный поток: окна, моно, кольцо и dBFS.

    `read()` отдаёт моно-кусок (окно 20 мс), `read_raw()` — сырое
    окно как есть. Кольцо хранит последние `ring_seconds` секунд
    моно: пре-ролл и `snapshot()`. Политики (VAD, тишина, границы
    фраз) здесь нет — это дело вызывающего.
    """

    def __init__(self, stream=None, channels=1, source=hal_mic.SOURCE,
                 rate=RATE, window_ms=hal_mic.WINDOW_MS,
                 settle_ms=hal_mic.SETTLE_MS, ring_seconds=RING_SECONDS):
        if stream is None:
            stream = hal_mic.Stream(source=source, rate=rate,
                                    channels=channels,
                                    window_ms=window_ms,
                                    settle_ms=settle_ms)
        self._stream = stream
        self._ring = []
        self._ring_chunks = 0
        self._frames = 0
        self._levels = []
        self._raw = None
        self._opened = False
        ring_seconds = float(ring_seconds)
        if ring_seconds < 0:
            raise HalError("ring_seconds не может быть отрицательным")
        self.ring_seconds = ring_seconds
        self.channels = 0
        self.rate = 0
        self.window_frames = 0

    def open(self):
        if self._opened:
            raise HalError("поток уже открыт")
        self._stream.open()
        self._opened = True
        frames = int(self._stream.window())
        rate = int(self._stream.rate)
        self.rate = rate
        self.window_frames = frames
        self.channels = int(self._stream.channels)
        self.ring_frames = int(self.ring_seconds * rate)
        self._ring_chunks = max(1, int(
            math.ceil(self.ring_frames / float(frames))))
        self.ring_frames = self._ring_chunks * frames
        self._frames = 0
        self._levels = []
        self._ring = []
        return self

    def running(self):
        return self._opened

    def read(self):
        """Моно-кусок за одно окно; кладёт его в кольцо."""
        if not self._opened:
            raise HalError("поток не открыт")
        raw = self._stream.read()
        self._raw = raw
        data = raw if self._stream.channels == 1 else self._stream.mono()
        stats = self._stream.stats()
        self._levels = [dbfs(value) for value in stats["rms"]]
        self._frames += len(data) // 2
        self._push(data)
        return data

    def read_raw(self):
        """Сырое окно последнего `read()` (4 канала при `channels > 1`)."""
        if not self._opened:
            raise HalError("поток не открыт")
        if self._raw is None:
            raise HalError("нет данных: сначала read()")
        return self._raw

    def chunks(self):
        """Генератор моно-кусков, пока поток открыт."""
        while self._opened:
            yield self.read()

    def level(self):
        """dBFS текущего окна: максимум по каналам."""
        if not self._levels:
            raise HalError("нет данных: сначала read()")
        return max(self._levels)

    def levels(self):
        """dBFS по каналам текущего окна."""
        if not self._levels:
            raise HalError("нет данных: сначала read()")
        return list(self._levels)

    def _push(self, data):
        self._ring.append(data)
        while len(self._ring) > self._ring_chunks:
            del self._ring[0]

    def snapshot(self, seconds=None):
        """Последние секунды моно: `(bytes, номер первого кадра)`."""
        if not self._ring:
            return b"", self._frames
        chunks = self._ring
        parts = len(self._ring)
        if seconds is not None:
            need = int(float(seconds) * int(self._stream.rate)) * 2
            total = 0
            parts = 0
            for data in reversed(chunks):
                total += len(data)
                parts += 1
                if total >= need:
                    break
        selected = chunks[len(chunks) - parts:]
        data = b"".join(selected)
        first = self._frames - len(data) // 2
        return data, first

    def frames(self):
        """Сколько кадров прочитано с открытия."""
        return self._frames

    def window(self):
        """Кадров в одном окне (`rate * window_ms / 1000`)."""
        return self.window_frames

    def close(self):
        if not self._opened:
            return False
        self._opened = False
        self._ring = []
        self._levels = []
        self._raw = None
        return self._stream.close()

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


_odas = None


class Odas:
    """Все выходы ODAS: tracks, pots, categories и (опционально) SSS.

    `odaslive` подключается ко всем сокетам конфига и падает, если
    хотя бы один не слушает; поэтому открываем и опрашиваем весь
    набор. `sss=True` добавляет `separated` 9002 и
    `postfiltered` 9003.
    """

    def __init__(self, sss=False):
        from micro_hal import lib_odas

        self.sss = bool(sss)
        self.tracks = lib_odas.Server(port=lib_odas.PORT)
        self.pots = lib_odas.Server(port=lib_odas.POT_PORT, energy_key="E")
        self.categories = lib_odas.Server(port=lib_odas.CATEGORY_PORT)
        self.separated = None
        self.postfiltered = None
        if self.sss:
            self.separated = lib_odas.AudioServer(
                port=lib_odas.SEPARATED_PORT)
            self.postfiltered = lib_odas.AudioServer(
                port=lib_odas.POSTFILTERED_PORT)

    def servers(self):
        items = [self.tracks, self.pots, self.categories]
        if self.separated is not None:
            items.append(self.separated)
        if self.postfiltered is not None:
            items.append(self.postfiltered)
        return items

    def listen(self):
        for server in self.servers():
            server.listen()
        return self

    def poll(self, timeout_ms=0):
        """Опрос всех выходов; вернуть всё, что пришло."""
        result = []
        for server in self.servers():
            result.extend(server.poll(timeout_ms))
        return result

    def close(self):
        for server in self.servers():
            server.close()


def open_odas(sss=False):
    """Подготовить выходы ODAS до запуска `odaslive`.

    Порядок: `open_odas()` → `hal_odas.start()` (с тем же набором
    выходов). Повторный вызов с тем же набором возвращает то же
    соединение; с другим — `HalError` (сначала `close_odas()`).
    """
    global _odas
    sss = bool(sss)
    if _odas is None:
        _odas = Odas(sss=sss).listen()
    elif _odas.sss != sss:
        raise HalError(
            "ODAS уже открыт {}; нужен набор {} — вызовите close_odas() "
            "и откройте заново".format(
                "с SSS" if _odas.sss else "без SSS",
                "с SSS" if sss else "без SSS"))
    return _odas


def close_odas():
    """Закрыть выходы ODAS; True, если они были открыты."""
    global _odas
    if _odas is None:
        return False
    _odas.close()
    _odas = None
    return True


def wait_ready(timeout=5.0, odas=None):
    """Ждать первых данных от ODAS; True, если они пришли.

    После `hal_odas.start()` первые кадры появляются примерно через
    2,2 с (инициализация Pulse и модулей ODAS), поэтому перед
    `direction()` стоит вызвать `wait_ready()`.
    """
    if odas is None:
        odas = open_odas()
    if not isinstance(odas, Odas):
        return odas.wait(int(float(timeout) * 1000)) is not None
    deadline = time.time() + float(timeout)
    while odas.tracks.frames() == 0:
        odas.poll(50)
        if time.time() >= deadline:
            return False
    return True


def _prepare(odas, timeout):
    """Слить данные и вернуть объект с `tracks()`/`direction()`."""
    if odas is None:
        odas = open_odas()
    if isinstance(odas, Odas):
        if timeout and float(timeout) > 0:
            deadline = time.time() + float(timeout)
            start = odas.tracks.frames()
            while True:
                odas.poll(20)
                if odas.tracks.frames() > start:
                    break
                if time.time() >= deadline:
                    break
        else:
            odas.poll(0)
        return odas.tracks
    if timeout and float(timeout) > 0:
        odas.wait(int(float(timeout) * 1000))
    else:
        odas.poll(0)
    return odas


def tracks(timeout=0.0, odas=None):
    """Последние треки ODAS; `odas` — свой `Odas` или `lib_odas.Server`.

    `timeout` — сколько ждать новый кадр, секунды (0 — только
    накопленное). Пустой список, если ODAS ещё ничего не прислал.
    """
    return _prepare(odas, timeout).tracks()


def direction(timeout=1.0, odas=None):
    """Азимут/возвышение самого активного трека ODAS.

    Возвращает `{"azimuth", "elevation", "activity", "id"}`;
    азимут: 0° — спереди, +90° — справа, −90° — слева.
    Если ODAS не прислал ни одного кадра — `HalError`.
    """
    value = _prepare(odas, timeout).direction()
    if value is None:
        raise HalError(
            "ODAS: нет данных (слушает ли сервер и запущен ли odaslive?)")
    return value


def separate(path=None):
    """Разделение источников — через `lib_odas.AudioServer`.

    SSS отдаёт PCM на 9002 (`separated`) и 9003 (`postfiltered`);
    сервер нужно открыть до запуска `odaslive` и работать с ним
    напрямую: `lib_odas.AudioServer(port=lib_odas.SEPARATED_PORT)`.
    """
    raise HalError(
        "разделение: используйте lib_odas.AudioServer(port=9002/9003)")
