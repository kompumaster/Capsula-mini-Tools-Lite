"""PCM и WAV: заголовок, длительность, склейка, запись.

Внутренний формат библиотеки — `s16le`, моно. Функции не трогают
железо и не запускают процессов.
"""

import os
import struct

from micro_tts.errors import TtsError

HEADER_SIZE = 44
DEFAULT_RATE = 16000


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TtsError("{} должен быть положительным целым".format(name))
    return value


def _non_negative_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TtsError("{} должен быть целым неотрицательным".format(name))
    return value


def _frame_size(channels, width):
    return _positive_int(channels, "channels") * _positive_int(width, "width")


def validate_pcm(pcm, channels=1, width=2):
    """Проверить, что PCM — байты, кратные кадру."""
    if not isinstance(pcm, (bytes, bytearray)):
        raise TtsError("PCM должен быть bytes или bytearray")
    frame = _frame_size(channels, width)
    if len(pcm) % frame:
        raise TtsError(
            "PCM: {} байт не делится на кадр {}".format(len(pcm), frame))
    return pcm


def wav_header(data_size, rate=DEFAULT_RATE, channels=1, width=2):
    """WAV-заголовок PCM (44 байта)."""
    data_size = _non_negative_int(data_size, "data_size")
    rate = _positive_int(rate, "rate")
    channels = _positive_int(channels, "channels")
    width = _positive_int(width, "width")
    if data_size > 0xFFFFFFFF - 36:
        raise TtsError("WAV слишком большой")
    block = channels * width
    try:
        return (
            b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
            + b"fmt " + struct.pack(
                "<IHHIIHH", 16, 1, channels, rate,
                rate * block, block, width * 8)
            + b"data" + struct.pack("<I", data_size)
        )
    except struct.error as exc:
        raise TtsError("не собрать WAV-заголовок: {}".format(exc))


def duration(pcm, rate=DEFAULT_RATE, channels=1, width=2):
    """Длительность PCM в секундах."""
    validate_pcm(pcm, channels, width)
    rate = _positive_int(rate, "rate")
    frame = int(channels) * int(width)
    return (len(pcm) // frame) / float(rate)


def join(chunks):
    """Склеить моно-PCM-чанки в один `bytes`."""
    if isinstance(chunks, (bytes, bytearray)):
        raise TtsError("join ожидает список чанков, а не один буфер")
    try:
        iterator = iter(chunks)
    except TypeError:
        raise TtsError("join ожидает список чанков")
    parts = []
    for chunk in iterator:
        validate_pcm(chunk)
        parts.append(bytes(chunk))
    return b"".join(parts)


def write_wav(path, pcm, rate=DEFAULT_RATE, channels=1, width=2):
    """Записать WAV и вернуть путь."""
    if not isinstance(path, str) or not path:
        raise TtsError("пустой путь WAV")
    validate_pcm(pcm, channels, width)
    header = wav_header(len(pcm), rate, channels, width)
    try:
        handle = open(path, "wb")
        try:
            handle.write(header)
            handle.write(bytes(pcm))
        finally:
            handle.close()
    except OSError as exc:
        raise TtsError("не записать WAV {}: {}".format(path, exc))
    return path


def raw_to_wav(raw_path, wav_path, rate=DEFAULT_RATE, chunk_size=65536):
    """Собрать WAV из сырого PCM-файла, не читая его целиком.

    Возвращает размер PCM в байтах. Исходный raw не удаляется.
    """
    if not isinstance(raw_path, str) or not raw_path:
        raise TtsError("пустой путь raw")
    if not isinstance(wav_path, str) or not wav_path:
        raise TtsError("пустой путь WAV")
    if raw_path == wav_path:
        raise TtsError("пути raw и WAV совпадают")
    try:
        size = os.stat(raw_path)[6]
    except OSError as exc:
        raise TtsError("нет raw {}: {}".format(raw_path, exc))
    if size <= 0:
        raise TtsError("пустой raw PCM")
    if size % 2:
        raise TtsError("raw PCM: нечётный размер")
    header = wav_header(size, rate)
    try:
        source = open(raw_path, "rb")
        try:
            target = open(wav_path, "wb")
            try:
                target.write(header)
                while True:
                    chunk = source.read(chunk_size)
                    if not chunk:
                        break
                    target.write(chunk)
            finally:
                target.close()
        finally:
            source.close()
    except OSError as exc:
        raise TtsError("не собрать WAV {}: {}".format(wav_path, exc))
    return size
