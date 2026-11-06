"""Настройки micro_asr и их проверка.

Здесь нет работы с железом и сетью: только значения по умолчанию и
проверки.
"""

from micro_asr.errors import AsrError

DEFAULT_LANGUAGE = "ru-RU"
DEFAULT_SAMPLE_RATE = 16000
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 48000


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise AsrError("{} должен быть непустой строкой".format(name))
    return value


def _engine(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise AsrError("пустое имя движка")
        return value
    return value


def _sample_rate(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AsrError("sample_rate должен быть целым числом")
    if value < MIN_SAMPLE_RATE or value > MAX_SAMPLE_RATE:
        raise AsrError(
            "sample_rate должен быть в {}…{}".format(
                MIN_SAMPLE_RATE, MAX_SAMPLE_RATE))
    return value


def _options(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AsrError("engine_options должен быть словарём")
    return dict(value)


class Config:
    """Проверенные настройки объекта `ASR`."""

    def __init__(self, engine=None, language=None, sample_rate=None,
                 engine_options=None):
        self.engine = _engine(engine)
        self.language = _text(
            DEFAULT_LANGUAGE if language is None else language,
            "language")
        self.sample_rate = _sample_rate(
            DEFAULT_SAMPLE_RATE if sample_rate is None else sample_rate)
        self.engine_options = _options(engine_options)

    def as_dict(self):
        """Словарь для отладки."""
        return {
            "engine": self.engine,
            "language": self.language,
            "sample_rate": self.sample_rate,
            "engine_options": dict(self.engine_options),
        }
