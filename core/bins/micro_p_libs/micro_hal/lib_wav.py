"""WAV: заголовок PCM-файла.

Общий примитив для микрофона (`lib_mic`) и динамика
(`lib_speaker`): RIFF/WAVE, PCM, 16 бит по умолчанию.
"""

import struct

from micro_hal.hal_common import HalError

__all__ = ["HEADER_SIZE", "wav_header"]

HEADER_SIZE = 44


def wav_header(data_size, channels=1, rate=16000, width=2):
    """Заголовок WAV PCM (44 байта)."""
    data_size = int(data_size)
    channels = int(channels)
    rate = int(rate)
    width = int(width)
    if data_size < 0 or channels <= 0 or rate <= 0 or width <= 0:
        raise HalError("неверные параметры WAV")
    block = channels * width
    return (
        b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
        + b"fmt " + struct.pack(
            "<IHHIIHH", 16, 1, channels, rate,
            rate * block, block, width * 8)
        + b"data" + struct.pack("<I", data_size)
    )
