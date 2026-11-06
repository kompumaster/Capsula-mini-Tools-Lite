"""MP3-кодек кеша: только чтение.

Edge уже отдаёт MP3, поэтому в кеш пишутся готовые байты
(`FileCache.put_encoded`), а при выдаче они декодируются в PCM через
`libc_mp3.so`. Кодировать PCM в MP3 библиотека не умеет.
"""

from micro_tts.cache.codec import Codec
from micro_tts.errors import TtsError


class Mp3Codec(Codec):
    """MP3 → PCM `s16le` моно 24 кГц."""

    name = "mp3"

    def encode(self, pcm, rate):
        raise TtsError("MP3-кеш: кодирование не поддерживается")

    def decode(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TtsError("MP3 должен быть bytes")
        data = bytes(data)
        if not data:
            raise TtsError("пустой MP3")
        try:
            from micro_tts.engines.mp3 import Mp3Decoder
        except Exception as exc:
            raise TtsError("нет MP3-декодера: {}".format(exc))
        decoder = Mp3Decoder()
        try:
            decoder.open(24000)
            decoder.feed(data)
            pcm = bytearray()
            while True:
                chunk = decoder.read(4096)
                if not chunk:
                    break
                pcm.extend(chunk)
            rate = decoder.rate()
            channels = decoder.channels()
        finally:
            try:
                decoder.close()
            except Exception:
                pass
        if not pcm:
            raise TtsError("MP3: нет аудио")
        if channels != 1:
            raise TtsError("MP3: не моно")
        return bytes(pcm), rate
