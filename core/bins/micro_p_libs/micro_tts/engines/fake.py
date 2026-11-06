"""Фиктивный движок: текст превращается в тишину.

Нужен для тестов и скелета: детерминированная длина, без железа и
внешних библиотек. Длительность зависит от числа символов, частоты и
темпа.
"""

from micro_tts.engine.base import AudioFormat, Engine
from micro_tts.errors import TtsError

BASE_RATE = 16000
MS_PER_CHAR = 20
MIN_RATE = 0.5
MAX_RATE = 2.0
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 48000
MIN_MS_PER_CHAR = 1
MAX_MS_PER_CHAR = 1000


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TtsError("{} должен быть числом".format(name))
    value = float(value)
    if value < MIN_RATE or value > MAX_RATE:
        raise TtsError("{} должен быть в {}…{}".format(
            name, MIN_RATE, MAX_RATE))
    return value


def _range_int(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TtsError("{} должен быть целым числом".format(name))
    if value < low or value > high:
        raise TtsError("{} должен быть в {}…{}".format(name, low, high))
    return value


class FakeEngine(Engine):
    """Текст → тишина `s16le` моно."""

    name = "fake"
    version = "1"

    def __init__(self):
        Engine.__init__(self)
        self.sample_rate = BASE_RATE
        self.ms_per_char = MS_PER_CHAR
        self.speaking_rate = 1.0
        self.pitch_value = 1.0
        self.voice_name = None
        self.options = {}
        self.calls = 0
        self.last_text = None

    def open(self, voice=None, rate=1.0, pitch=1.0, **options):
        if voice is not None and voice != "fake":
            raise TtsError("fake: нет голоса {}".format(voice))
        rate = _number(rate, "rate")
        pitch = _number(pitch, "pitch")
        sample_rate = _range_int(
            options.get("sample_rate", BASE_RATE), "sample_rate",
            MIN_SAMPLE_RATE, MAX_SAMPLE_RATE)
        ms_per_char = _range_int(
            options.get("ms_per_char", MS_PER_CHAR), "ms_per_char",
            MIN_MS_PER_CHAR, MAX_MS_PER_CHAR)
        self.sample_rate = sample_rate
        self.ms_per_char = ms_per_char
        self.speaking_rate = rate
        self.pitch_value = pitch
        self.voice_name = voice or "fake"
        self.options = dict(options)
        self.calls = 0
        self._opened = True
        return self

    def voices(self):
        return [{
            "name": "fake",
            "language": "ru",
            "description": "тишина заданной длины",
        }]

    def capabilities(self):
        return {
            "stream": True,
            "ssml": False,
            "rate": True,
            "pitch": False,
            "voices": True,
        }

    def cache_tag(self):
        return "{}:{}:{}".format(self.name, self.version, self.ms_per_char)

    def request_bytes(self):
        return 1000000

    def format(self):
        self._require_opened()
        return AudioFormat(self.sample_rate)

    def synthesize(self, text):
        pcm = bytearray()
        for chunk in self.stream(text):
            pcm.extend(chunk)
        return bytes(pcm)

    def stream(self, text):
        self._require_opened()
        if not isinstance(text, str):
            raise TtsError("текст должен быть строкой")
        if not text.strip():
            raise TtsError("текст пустой")
        milliseconds = len(text) * self.ms_per_char / self.speaking_rate
        frames = int(milliseconds * self.sample_rate / 1000.0)
        if frames < 1:
            frames = 1
        self.calls += 1
        self.last_text = text
        left = frames
        while left > 0:
            count = min(left, 1024)
            yield b"\x00\x00" * count
            left -= count

    def close(self):
        Engine.close(self)
