"""Скользящее окно вероятностей и порог срабатывания.

Движок отдаёт вероятности по шагам (обычно 10 мс). Окно хранит
последние `size` значений, считает среднее и решает, было ли
срабатывание. Дополнительно действует пауза `cooldown_ms`, чтобы одна
фраза не дала несколько событий подряд.

Время можно передавать явно (`now_ms`) — так тесты детерминированы.
"""

from micro_ww.errors import WwError

DEFAULT_WINDOW = 5
DEFAULT_CUTOFF = 0.97
DEFAULT_COOLDOWN_MS = 1000


def _now_ms():
    """Монотонное время в миллисекундах для MicroPython и CPython."""
    try:
        import time
    except ImportError:
        return 0
    ticks = getattr(time, "ticks_ms", None)
    if ticks is not None:
        return int(ticks())
    monotonic = getattr(time, "monotonic", None)
    if monotonic is not None:
        return int(monotonic() * 1000)
    return 0


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise WwError("{} должен быть целым числом".format(name))
    if value < low or value > high:
        raise WwError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WwError("{} должен быть числом".format(name))
    value = float(value)
    if value != value:
        raise WwError("{} не может быть NaN".format(name))
    if value < low or (high is not None and value > high):
        if high is None:
            raise WwError("{} должен быть не меньше {}".format(name, low))
        raise WwError("{} должен быть в {}…{}".format(name, low, high))
    return value


class ProbabilityWindow:
    """Последние вероятности, среднее, порог и пауза."""

    def __init__(self, size=DEFAULT_WINDOW, cutoff=DEFAULT_CUTOFF,
                 cooldown_ms=DEFAULT_COOLDOWN_MS):
        self.size = _integer(size, "size", 1, 1000)
        self.cutoff = _number(cutoff, "cutoff", 0.0, 1.0)
        self.cooldown_ms = _number(cooldown_ms, "cooldown_ms", 0.0, None)
        self._values = []
        self._last_detect_ms = None

    def push(self, probability, now_ms=None):
        """Добавить вероятность; вернуть снимок окна.

        `detected` — окно заполнено, среднее не ниже порога и пауза
        после прошлого срабатывания прошла.
        """
        probability = _number(probability, "probability", 0.0, 1.0)
        if now_ms is None:
            now_ms = _now_ms()
        else:
            now_ms = _number(now_ms, "now_ms", 0.0, None)

        self._values.append(probability)
        while len(self._values) > self.size:
            del self._values[0]

        average = self.average
        full = self.full
        detected = full and average >= self.cutoff
        if detected and self._last_detect_ms is not None:
            if now_ms - self._last_detect_ms < self.cooldown_ms:
                detected = False
        if detected:
            self._last_detect_ms = now_ms

        return {
            "detected": detected,
            "average": average,
            "probability": probability,
            "count": len(self._values),
            "full": full,
        }

    def reset(self):
        """Забыть значения и прошлое срабатывание."""
        self._values = []
        self._last_detect_ms = None

    @property
    def average(self):
        if not self._values:
            return 0.0
        return sum(self._values) / float(len(self._values))

    @property
    def full(self):
        return len(self._values) == self.size

    @property
    def count(self):
        return len(self._values)

    @property
    def last_detect_ms(self):
        return self._last_detect_ms

    def as_dict(self):
        return {
            "size": self.size,
            "cutoff": self.cutoff,
            "cooldown_ms": self.cooldown_ms,
            "count": self.count,
            "average": self.average,
            "last_detect_ms": self._last_detect_ms,
        }

    def __repr__(self):
        return "ProbabilityWindow(size={}, cutoff={})".format(
            self.size, self.cutoff)
