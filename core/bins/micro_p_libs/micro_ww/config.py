"""Настройки `WakeWord` и их проверка.

Здесь нет железа, C и моделей: только значения по умолчанию и
проверки. Порог и окно по умолчанию берутся из манифеста, поэтому в
`Config` они могут быть `None`.
"""

from micro_ww.errors import WwError

DEFAULT_ENGINE = "fake"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_COOLDOWN_MS = 1000

MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 48000


def _engine(value):
    if value is None:
        return DEFAULT_ENGINE
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise WwError("пустое имя движка")
        return value
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise WwError("{} должен быть непустой строкой".format(name))
    return value.strip()


def _sample_rate(value):
    if value is None:
        return DEFAULT_SAMPLE_RATE
    if isinstance(value, bool) or not isinstance(value, int):
        raise WwError("sample_rate должен быть целым числом")
    if value < MIN_SAMPLE_RATE or value > MAX_SAMPLE_RATE:
        raise WwError("sample_rate должен быть в {}…{}".format(
            MIN_SAMPLE_RATE, MAX_SAMPLE_RATE))
    return value


def _threshold(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WwError("threshold должен быть числом")
    value = float(value)
    if value != value:
        raise WwError("threshold не может быть NaN")
    if value <= 0.0 or value > 1.0:
        raise WwError("threshold должен быть в (0…1]")
    return value


def _window(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise WwError("window должен быть целым числом")
    if value < 1 or value > 1000:
        raise WwError("window должен быть в 1…1000")
    return value


def _cooldown(value):
    if value is None:
        return DEFAULT_COOLDOWN_MS
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WwError("cooldown_ms должен быть числом")
    value = float(value)
    if value != value:
        raise WwError("cooldown_ms не может быть NaN")
    if value < 0:
        raise WwError("cooldown_ms не может быть отрицательным")
    return value


def _options(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WwError("engine_options должен быть словарём")
    return dict(value)


class Config:
    """Проверенные настройки `WakeWord`."""

    def __init__(self, engine=None, model=None, sample_rate=None,
                 threshold=None, window=None, cooldown_ms=None,
                 engine_options=None):
        self.engine = _engine(engine)
        self.model = None if model is None else _text(model, "model")
        self.sample_rate = _sample_rate(sample_rate)
        self.threshold = _threshold(threshold)
        self.window = _window(window)
        self.cooldown_ms = _cooldown(cooldown_ms)
        self.engine_options = _options(engine_options)

    def as_dict(self):
        """Словарь для отладки."""
        return {
            "engine": self.engine,
            "model": self.model,
            "sample_rate": self.sample_rate,
            "threshold": self.threshold,
            "window": self.window,
            "cooldown_ms": self.cooldown_ms,
            "engine_options": dict(self.engine_options),
        }
