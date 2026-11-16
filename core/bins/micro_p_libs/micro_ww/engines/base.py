"""Базовый интерфейс движка детектора.

Движок только превращает PCM в вероятности по шагам. Он не трогает
микрофон, `micro_hal` и сеть: это дело источников и координатора.
"""

from micro_ww.errors import WwError


class Engine:
    """Базовый класс движка.

    Наследник реализует `open` и `push`; остальное имеет значения по
    умолчанию.
    """

    name = "base"
    version = "1"

    def __init__(self):
        self._opened = False

    def open(self, model=None, sample_rate=16000, **options):
        raise NotImplementedError

    def push(self, pcm):
        """PCM → список вероятностей за обработанные шаги."""
        raise NotImplementedError

    def reset(self):
        """Сбросить состояние потока, не закрывая движок."""

    def close(self):
        self._opened = False
        return True

    def info(self):
        return {"name": self.name, "version": self.version}

    def _require_opened(self):
        if not getattr(self, "_opened", False):
            raise WwError("движок не открыт")
