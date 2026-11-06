"""Кодеки кеша: PCM ↔ байты файла."""

import struct

from micro_tts import audio
from micro_tts.errors import TtsError


class Codec:
    """Сжатие и распаковка аудио для кеша."""

    name = "base"

    def encode(self, pcm, rate):
        raise TtsError("кодек не реализует encode()")

    def decode(self, data):
        """`bytes` → `(pcm, rate)`."""
        raise TtsError("кодек не реализует decode()")


class WavCodec(Codec):
    """WAV PCM `s16le`, моно."""

    name = "wav"

    def encode(self, pcm, rate):
        audio.validate_pcm(pcm)
        if not pcm:
            raise TtsError("пустой PCM")
        if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
            raise TtsError("частота должна быть положительным целым")
        return audio.wav_header(len(pcm), rate) + bytes(pcm)

    def decode(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TtsError("WAV должен быть bytes")
        data = bytes(data)
        if len(data) < audio.HEADER_SIZE:
            raise TtsError("короткий WAV")
        riff, _riff_size, wave = struct.unpack("<4sI4s", data[:12])
        if riff != b"RIFF" or wave != b"WAVE":
            raise TtsError("не WAV")
        (fmt, fmt_size, codec, channels, rate, _byte_rate, _block,
         bits) = struct.unpack("<4sIHHIIHH", data[12:36])
        if fmt != b"fmt " or fmt_size != 16:
            raise TtsError("неверный fmt WAV")
        if codec != 1 or channels != 1 or bits != 16:
            raise TtsError("WAV должен быть PCM s16le моно")
        if rate <= 0:
            raise TtsError("неверная частота WAV")
        marker, size = struct.unpack("<4sI", data[36:44])
        if marker != b"data":
            raise TtsError("нет блока data в WAV")
        if len(data) < audio.HEADER_SIZE + size:
            raise TtsError("WAV обрезан")
        pcm = data[audio.HEADER_SIZE:audio.HEADER_SIZE + size]
        audio.validate_pcm(pcm)
        if not pcm:
            raise TtsError("пустой WAV")
        return pcm, rate
