"""Интерфейс нормализатора текста."""

from micro_tts.errors import TtsError


class Normalizer:
    """Готовит текст и делит его на чанки для движка."""

    language = "ru"
    version = "1"

    def prepare(self, text, limit=200):
        """Текст → список непустых чанков."""
        raise TtsError("нормализатор не реализует prepare()")

    def normalize(self, text):
        """Текст → нормализованная строка без деления на чанки.

        Необязательный метод: если его нет, `TTS` при `split=False`
        откатывается на `prepare()` и обычное деление.
        """
        raise TtsError("нормализатор не реализует normalize()")
