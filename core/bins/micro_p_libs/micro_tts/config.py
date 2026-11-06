"""Настройки micro_tts и их проверка.

Здесь нет работы с железом: только значения по умолчанию и проверки.
"""

from micro_tts.errors import TtsError

DEFAULT_CACHE_DIR = "/home/microp/tts_cache"
DEFAULT_CHUNK_CHARS = 200
DEFAULT_CACHE_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_CACHE_MAX_ENTRIES = 256
DEFAULT_CACHE_MAX_CHARS = 300

MIN_RATE = 0.5
MAX_RATE = 2.0
MIN_VOLUME = 0
MAX_VOLUME = 100
MIN_CHUNK_CHARS = 1
MAX_CHUNK_CHARS = 2000

_SINK_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_.-"
)


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TtsError("{} должен быть числом".format(name))
    value = float(value)
    if value < low or value > high:
        raise TtsError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _integer(value, name, low, high=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TtsError("{} должен быть целым числом".format(name))
    if value < low:
        raise TtsError("{} должен быть не меньше {}".format(name, low))
    if high is not None and value > high:
        raise TtsError("{} должен быть не больше {}".format(name, high))
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise TtsError("{} должен быть непустой строкой".format(name))
    return value


def _engine(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise TtsError("пустое имя движка")
        return value
    return value


def _voice(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise TtsError("голос должен быть строкой или None")
    value = value.strip()
    if not value:
        raise TtsError("пустое имя голоса")
    return value


def _volume(value):
    if value is None:
        return None
    return _integer(value, "volume", MIN_VOLUME, MAX_VOLUME)


def _sink(value):
    if not isinstance(value, str) or not value:
        raise TtsError("sink должен быть непустой строкой")
    for char in value:
        if char not in _SINK_CHARS:
            raise TtsError("неверное имя sink: {!r}".format(value))
    return value


def _bool(value, name):
    if not isinstance(value, bool):
        raise TtsError("{} должен быть True или False".format(name))
    return value


def _options(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TtsError("options должен быть словарём или None")
    return dict(value)


class Config:
    """Настройки TTS с проверкой значений."""

    def __init__(self, engine=None, voice=None, rate=1.0, pitch=1.0,
                 volume=None, sink="master", chunk_chars=DEFAULT_CHUNK_CHARS,
                 player=None, normalizer=None, cache=False,
                 cache_dir=DEFAULT_CACHE_DIR,
                 cache_max_bytes=DEFAULT_CACHE_MAX_BYTES,
                 cache_max_entries=DEFAULT_CACHE_MAX_ENTRIES,
                 cache_max_chars=DEFAULT_CACHE_MAX_CHARS, options=None):
        self.engine = _engine(engine)
        self.voice = _voice(voice)
        self.rate = _number(rate, "rate", MIN_RATE, MAX_RATE)
        self.pitch = _number(pitch, "pitch", MIN_RATE, MAX_RATE)
        self.volume = _volume(volume)
        self.sink = _sink(sink)
        self.chunk_chars = _integer(
            chunk_chars, "chunk_chars", MIN_CHUNK_CHARS, MAX_CHUNK_CHARS)
        self.player = player
        self.normalizer = normalizer
        self.cache = _bool(cache, "cache")
        self.cache_dir = _text(cache_dir, "cache_dir")
        self.cache_max_bytes = _integer(
            cache_max_bytes, "cache_max_bytes", 0)
        self.cache_max_entries = _integer(
            cache_max_entries, "cache_max_entries", 0)
        self.cache_max_chars = _integer(
            cache_max_chars, "cache_max_chars", 0)
        self.options = _options(options)

    def as_dict(self):
        """Настройки словарём; `options` копируется."""
        return {
            "engine": self.engine,
            "voice": self.voice,
            "rate": self.rate,
            "pitch": self.pitch,
            "volume": self.volume,
            "sink": self.sink,
            "chunk_chars": self.chunk_chars,
            "player": self.player,
            "normalizer": self.normalizer,
            "cache": self.cache,
            "cache_dir": self.cache_dir,
            "cache_max_bytes": self.cache_max_bytes,
            "cache_max_entries": self.cache_max_entries,
            "cache_max_chars": self.cache_max_chars,
            "options": dict(self.options),
        }
