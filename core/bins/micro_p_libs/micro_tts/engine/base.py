"""Базовый интерфейс движка TTS.

Движок только синтезирует PCM. Он не играет звук, не трогает
громкость и не знает про `micro_hal`.
"""

from micro_tts.errors import TtsError


class AudioFormat:
    """Формат PCM: `s16le`, моно."""

    def __init__(self, rate, channels=1, width=2):
        if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
            raise TtsError("частота должна быть положительным целым")
        if channels != 1:
            raise TtsError("поддерживается только моно")
        if width != 2:
            raise TtsError("поддерживается только s16le (2 байта)")
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
    raise TtsError("формат движка должен быть AudioFormat или словарём")


class Engine:
    """Базовый класс движка.

    Наследник реализует `open`, `format` и `synthesize`; остальное
    имеет значения по умолчанию.
    """

    name = "base"
    version = "1"

    def __init__(self):
        self._opened = False

    def open(self, voice=None, rate=1.0, pitch=1.0, **options):
        """Подготовить движок; ошибка — `TtsError`."""
        raise TtsError("движок {} не реализует open()".format(self.name))

    def voices(self):
        """Список голосов: имя, язык, описание."""
        return []

    def capabilities(self):
        """Что умеет движок."""
        return {
            "stream": False,
            "ssml": False,
            "rate": False,
            "pitch": False,
            "voices": False,
        }

    def cache_tag(self):
        """Стабильная строка для ключа кеша."""
        return "{}:{}".format(self.name, self.version)

    def format(self):
        """Формат PCM после `open()`."""
        raise TtsError("движок {} не сообщает формат".format(self.name))

    def synthesize(self, text):
        """Текст → PCM `s16le` моно."""
        raise TtsError(
            "движок {} не реализует synthesize()".format(self.name))

    def stream(self, text):
        """Необязательный поток PCM."""
        raise TtsError(
            "движок {} не поддерживает поток".format(self.name))

    def request_bytes(self):
        """Сколько байт текста движок принимает за один запрос.

        `0` — без ограничения. По умолчанию 4096: столько принимает
        Edge. Потоковый режим склеивает текст до этого размера.
        """
        return 4096

    def encoded_format(self):
        """Формат сжатого аудио для кеша (`mp3`) или `None`."""
        return None

    def synthesize_pair(self, text):
        """Текст → `(pcm, сжатые байты)`; для кеша без перекодирования."""
        raise TtsError(
            "движок {} не отдаёт сжатое аудио".format(self.name))

    def close(self):
        """Освободить ресурсы; повторный вызов безопасен."""
        self._opened = False

    def opened(self):
        return self._opened

    def _require_opened(self):
        if not self._opened:
            raise TtsError("движок {} не открыт".format(self.name))
