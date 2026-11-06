"""Источники аудио: общий интерфейс.

`Source` — `open()`, `read()`, `info()`, `close()`. `read()` отдаёт
сырой PCM в том виде, в каком он лежит в источнике; приведение к
16 кГц / моно делает `audio.prepare()`.
"""

from micro_asr import audio
from micro_asr.errors import AsrError

DEFAULT_RATE = audio.DEFAULT_RATE
WIDTH = 2


def positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AsrError("{} должен быть положительным целым".format(name))
    return value


def check_channels(channels):
    channels = positive_int(channels, "channels")
    if channels > 8:
        raise AsrError("channels не может быть больше 8")
    return channels


def check_width(width):
    if width != WIDTH:
        raise AsrError("поддерживается только 16-битный PCM")
    return WIDTH


class Source:
    """Общий интерфейс источника аудио."""

    name = "source"

    def open(self):
        return self

    def read(self):
        raise NotImplementedError

    def info(self):
        raise NotImplementedError

    def duration(self):
        return self.info()["duration"]

    def close(self):
        pass

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
