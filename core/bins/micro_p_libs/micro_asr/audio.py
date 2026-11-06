"""PCM и WAV: проверки, длительность, моно, ресемплинг.

Внутренний формат библиотеки — `s16le`, моно. Функции не трогают
железо, сеть и не запускают процессов.
"""

import struct

from micro_asr.errors import AsrError

HEADER_SIZE = 44
DEFAULT_RATE = 16000
WIDTH = 2


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AsrError("{} должен быть положительным целым".format(name))
    return value


def _frame_size(channels, width):
    return _positive_int(channels, "channels") * _positive_int(width, "width")


def validate_pcm(pcm, channels=1, width=2):
    """Проверить, что PCM — байты, кратные кадру."""
    if not isinstance(pcm, (bytes, bytearray)):
        raise AsrError("PCM должен быть bytes или bytearray")
    frame = _frame_size(channels, width)
    if len(pcm) % frame:
        raise AsrError(
            "PCM: {} байт не делится на кадр {}".format(len(pcm), frame))
    return pcm


def duration(pcm, rate=DEFAULT_RATE, channels=1, width=2):
    """Длительность PCM в секундах."""
    validate_pcm(pcm, channels, width)
    rate = _positive_int(rate, "rate")
    frame = int(channels) * int(width)
    return (len(pcm) // frame) / float(rate)


def parse_wav(data):
    """Разобрать WAV: `(pcm, rate, channels, width)`.

    Поддерживается только целочисленный PCM 16 бит.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise AsrError("WAV должен быть bytes")
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AsrError("не WAV-файл")
    position = 12
    fmt = None
    pcm = None
    rate = channels = bits = None
    while position + 8 <= len(data):
        name = bytes(data[position:position + 4])
        size = int.from_bytes(data[position + 4:position + 8], "little")
        body = position + 8
        end = body + size
        if end > len(data):
            end = len(data)
        if name == b"fmt ":
            if size < 16 or body + 16 > len(data):
                raise AsrError("WAV: повреждён fmt")
            fmt = int.from_bytes(data[body:body + 2], "little")
            channels = int.from_bytes(data[body + 2:body + 4], "little")
            rate = int.from_bytes(data[body + 4:body + 8], "little")
            bits = int.from_bytes(data[body + 14:body + 16], "little")
        elif name == b"data":
            pcm = bytes(data[body:end])
        position = body + size + (size & 1)
    if fmt is None or pcm is None:
        raise AsrError("WAV: нет fmt или data")
    if fmt != 1:
        raise AsrError("WAV: поддерживается только PCM")
    if bits != 16:
        raise AsrError("WAV: поддерживается только 16 бит")
    if channels is None or channels < 1 or channels > 8:
        raise AsrError("WAV: неверное число каналов")
    rate = _positive_int(rate, "WAV rate")
    if len(pcm) % (channels * 2):
        raise AsrError("WAV: неполный кадр")
    return pcm, rate, channels, 2


def read_pcm(path):
    """Прочитать файл с сырым PCM."""
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise AsrError("не прочитать {}: {}".format(path, exc))


def read_wav(path):
    """Прочитать WAV-файл: `(pcm, rate, channels, width)`."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise AsrError("не прочитать {}: {}".format(path, exc))
    return parse_wav(data)


BLOCK = 1024


def _unpack(pcm, start, count):
    """Прочитать `count` сэмплов `s16le` с позиции `start`."""
    data = pcm[start * 2:(start + count) * 2]
    return struct.unpack("<{}h".format(count), bytes(data))


def _pack(values):
    """Упаковать сэмплы в `s16le`."""
    return struct.pack("<{}h".format(len(values)), *values)


def to_mono(pcm, channels=1, width=2):
    """Свести каналы в моно (усреднение)."""
    validate_pcm(pcm, channels, width)
    if width != 2:
        raise AsrError("поддерживается только 16-битный PCM")
    if channels == 1:
        return bytes(pcm)
    frames = len(pcm) // (channels * 2)
    output = bytearray()
    for start in range(0, frames, BLOCK):
        count = min(BLOCK, frames - start)
        values = struct.unpack(
            "<{}h".format(count * channels),
            bytes(pcm[start * channels * 2:
                      (start + count) * channels * 2]))
        mono = []
        for index in range(0, len(values), channels):
            total = 0
            for channel in range(channels):
                total += values[index + channel]
            mono.append(int(total / channels))
        output.extend(_pack(mono))
    return bytes(output)


def resample(pcm, src_rate=DEFAULT_RATE, dst_rate=DEFAULT_RATE):
    """Линейный ресемплер моно-PCM `s16le`."""
    validate_pcm(pcm)
    src_rate = _positive_int(src_rate, "src_rate")
    dst_rate = _positive_int(dst_rate, "dst_rate")
    if src_rate == dst_rate:
        return bytes(pcm)
    count = len(pcm) // 2
    if count == 0:
        return b""
    if count == 1:
        return bytes(pcm)
    out_count = int(round(count * dst_rate / float(src_rate)))
    if out_count < 1:
        out_count = 1
    if out_count == 1:
        return bytes(pcm[0:2])
    last = count - 1
    step = last / float(out_count - 1)
    output = bytearray()
    index = 0
    while index < out_count:
        position = index * step
        left = int(position)
        start = (left // BLOCK) * BLOCK
        end = min(start + BLOCK, count)
        read_end = min(end + 1, count)
        values = _unpack(pcm, start, read_end - start)
        chunk = []
        while index < out_count:
            position = index * step
            left = int(position)
            if left >= end and left < last:
                break
            if left >= last:
                chunk.append(values[last - start])
            else:
                frac = position - left
                base = left - start
                value = (values[base]
                         + (values[base + 1] - values[base]) * frac)
                chunk.append(int(round(value)))
            index += 1
        output.extend(_pack(chunk))
    return bytes(output)


def prepare(pcm, src_rate=DEFAULT_RATE, channels=1, width=2,
            target_rate=DEFAULT_RATE):
    """Привести PCM к моно и целевой частоте."""
    validate_pcm(pcm, channels, width)
    mono = to_mono(pcm, channels, width)
    return resample(mono, src_rate, target_rate)
