"""Фиктивный движок: заданные вероятности без C и без модели.

Нужен для тестов координатора и источников. На каждый `push()`
отдаёт одну вероятность из списка; после конца списка — либо пусто,
либо начинает сначала (`repeat=True`).
"""

from micro_ww.engines.base import Engine
from micro_ww.errors import WwError

DEFAULT_PROBABILITIES = (0.0,)
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 48000


def _sample_rate(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise WwError("sample_rate должен быть целым числом")
    if value < MIN_SAMPLE_RATE or value > MAX_SAMPLE_RATE:
        raise WwError("sample_rate должен быть в {}…{}".format(
            MIN_SAMPLE_RATE, MAX_SAMPLE_RATE))
    return value


def _probabilities(value):
    if value is None:
        value = DEFAULT_PROBABILITIES
    if not isinstance(value, (list, tuple)):
        raise WwError("probabilities должен быть списком")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise WwError("вероятность должна быть числом")
        item = float(item)
        if item != item or item < 0.0 or item > 1.0:
            raise WwError("вероятность должна быть в 0…1")
        result.append(item)
    return result


class FakeEngine(Engine):
    """PCM → заданная последовательность вероятностей."""

    name = "fake"
    version = "1"

    def __init__(self):
        Engine.__init__(self)
        self.sample_rate = 16000
        self.model = None
        self.probabilities = []
        self.repeat = False
        self.index = 0
        self.calls = 0

    def open(self, model=None, sample_rate=16000, **options):
        self.sample_rate = _sample_rate(sample_rate)
        self.model = model
        self.probabilities = _probabilities(
            options.get("probabilities"))
        repeat = options.get("repeat", False)
        if not isinstance(repeat, bool):
            raise WwError("repeat должен быть True или False")
        self.repeat = repeat
        self.index = 0
        self.calls = 0
        self._opened = True
        return self

    def push(self, pcm):
        self._require_opened()
        if not isinstance(pcm, (bytes, bytearray)):
            raise WwError("PCM должен быть bytes или bytearray")
        if not self.probabilities:
            return []
        if self.index >= len(self.probabilities):
            if not self.repeat:
                return []
            self.index = 0
        value = self.probabilities[self.index]
        self.index += 1
        self.calls += 1
        return [value]

    def reset(self):
        self.index = 0
        self.calls = 0

    def close(self):
        self._opened = False
        return True

    def info(self):
        return {
            "name": self.name,
            "version": self.version,
            "sample_rate": self.sample_rate,
            "probabilities": len(self.probabilities),
            "repeat": self.repeat,
            "calls": self.calls,
            "index": self.index,
        }
