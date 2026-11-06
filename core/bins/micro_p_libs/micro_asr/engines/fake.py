"""Фиктивный движок: детерминированный текст без сети.

Нужен для тестов и скелета: `recognize()` возвращает заданную строку
и запоминает размер и длительность аудио.
"""

from micro_asr import audio
from micro_asr.engines.base import AudioFormat, Engine
from micro_asr.errors import AsrError

DEFAULT_TEXT = "распознано"
DEFAULT_MAX_SECONDS = 30.0
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 48000


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise AsrError("{} должен быть непустой строкой".format(name))
    return value


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AsrError("{} должен быть целым числом".format(name))
    if value < low or value > high:
        raise AsrError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AsrError("{} должен быть числом".format(name))
    value = float(value)
    if value <= 0:
        raise AsrError("{} должен быть больше нуля".format(name))
    return value


class FakeEngine(Engine):
    """PCM → фиксированный текст."""

    name = "fake"
    version = "1"

    def __init__(self):
        Engine.__init__(self)
        self.sample_rate = 16000
        self.language = None
        self.text = DEFAULT_TEXT
        self.limit = DEFAULT_MAX_SECONDS
        self.calls = 0
        self.last_bytes = 0
        self.last_seconds = 0.0

    def open(self, language=None, sample_rate=16000, **options):
        if language is not None:
            language = _text(language, "language")
        sample_rate = _integer(
            sample_rate, "sample_rate", MIN_SAMPLE_RATE, MAX_SAMPLE_RATE)
        text = options.get("text", self.text)
        self.text = _text(text, "text")
        self.limit = _number(
            options.get("max_seconds", self.limit), "max_seconds")
        self.sample_rate = sample_rate
        self.language = language or "ru-RU"
        self.calls = 0
        self.last_bytes = 0
        self.last_seconds = 0.0
        self._opened = True
        return self

    def capabilities(self):
        return {
            "stream": False,
            "languages": True,
        }

    def format(self):
        self._require_opened()
        return AudioFormat(self.sample_rate)

    def max_seconds(self):
        return self.limit

    def recognize(self, pcm):
        self._require_opened()
        audio.validate_pcm(pcm)
        if not pcm:
            raise AsrError("пустое аудио")
        seconds = audio.duration(pcm, self.sample_rate)
        if seconds > self.limit:
            raise AsrError(
                "аудио {:.1f} с длиннее предела {:.1f} с".format(
                    seconds, self.limit))
        self.calls += 1
        self.last_bytes = len(pcm)
        self.last_seconds = seconds
        return self.text
