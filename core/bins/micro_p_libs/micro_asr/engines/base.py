"""Базовый интерфейс движка распознавания.

Движок только превращает PCM в текст. Он не трогает микрофон, сеть и
`micro_hal`; всё это — дело источников и координатора.
"""

from micro_asr.errors import AsrError


class AudioFormat:
    """Формат PCM: `s16le`, моно."""

    def __init__(self, rate, channels=1, width=2):
        if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
            raise AsrError("частота должна быть положительным целым")
        if channels != 1:
            raise AsrError("поддерживается только моно")
        if width != 2:
            raise AsrError("поддерживается только s16le (2 байта)")
        self.rate = rate
        self.channels = 1
        self.width = 2

    def as_dict(self):
        return {
            "rate": self.rate,
            "channels": self.channels,
            "width": self.width,
        }

    def __eq__(self, other):
        if isinstance(other, AudioFormat):
            return (self.rate == other.rate
                    and self.channels == other.channels
                    and self.width == other.width)
        if isinstance(other, dict):
            return self.as_dict() == other
        return NotImplemented

    def __repr__(self):
        return "AudioFormat({}, channels={}, width={})".format(
            self.rate, self.channels, self.width)


def check_format(value):
    """Привести формат движка к `AudioFormat`."""
    if isinstance(value, AudioFormat):
        return value
    if isinstance(value, dict):
        return AudioFormat(value.get("rate"), value.get("channels", 1),
                           value.get("width", 2))
    raise AsrError("формат движка должен быть AudioFormat или словарём")


class Engine:
    """Базовый класс движка.

    Наследник реализует `open`, `format` и `recognize`; остальное
    имеет значения по умолчанию.
    """

    name = "base"
    version = "1"

    def __init__(self):
        self._opened = False

    def open(self, language=None, sample_rate=16000, **options):
        """Подготовить движок; ошибка — `AsrError`."""
        raise AsrError("движок {} не реализует open()".format(self.name))

    def capabilities(self):
        """Что умеет движок."""
        return {
            "stream": False,
            "languages": False,
        }

    def format(self):
        """Формат PCM после `open()`."""
        raise AsrError("движок {} не сообщает формат".format(self.name))

    def max_seconds(self):
        """Предел длительности одного запроса."""
        return 30.0

    def recognize(self, pcm):
        """PCM `s16le` моно → текст."""
        raise AsrError(
            "движок {} не реализует recognize()".format(self.name))

    def close(self):
        """Освободить ресурсы; повторный вызов безопасен."""
        self._opened = False

    def opened(self):
        return self._opened

    def _require_opened(self):
        if not self._opened:
            raise AsrError("движок {} не открыт".format(self.name))
