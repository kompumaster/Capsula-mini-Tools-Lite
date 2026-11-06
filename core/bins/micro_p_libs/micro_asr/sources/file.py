"""Источник аудио из файла: PCM и WAV; MP3 — отдельный этап."""

from micro_asr import audio
from micro_asr.errors import AsrError
from micro_asr.sources.base import (
    DEFAULT_RATE, WIDTH, Source, check_channels, check_width,
    positive_int)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise AsrError("{} должен быть непустой строкой".format(name))
    return value


class FileSource(Source):
    """Файл PCM или WAV.

    WAV определяется по заголовку, расширение — подсказка. Файлы `.mp3`
    пока не поддерживаются.
    """

    name = "file"

    def __init__(self, path, rate=DEFAULT_RATE, channels=1, width=WIDTH):
        self.path = _text(path, "path")
        self._rate = positive_int(rate, "rate")
        self._channels = check_channels(channels)
        check_width(width)
        self._width = WIDTH
        self._kind = None
        self._pcm = None
        self._info = None

    def open(self):
        if self._pcm is None:
            self._load()
        return self

    def read(self):
        if self._pcm is None:
            self._load()
        return self._pcm

    def info(self):
        if self._info is None:
            self._load()
        return dict(self._info)

    def close(self):
        self._pcm = None
        self._info = None

    def _load(self):
        try:
            with open(self.path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            raise AsrError("не прочитать {}: {}".format(self.path, exc))
        is_wav = (len(data) >= 12 and data[0:4] == b"RIFF"
                  and data[8:12] == b"WAVE")
        lower = self.path.lower()
        if is_wav or lower.endswith(".wav"):
            pcm, rate, channels, width = audio.parse_wav(data)
            self._pcm = pcm
            self._rate = rate
            self._channels = channels
            self._width = width
            self._kind = "wav"
        elif lower.endswith(".mp3"):
            from micro_asr.mp3 import decode
            pcm, rate, channels = decode(data)
            self._pcm = pcm
            self._rate = rate
            self._channels = channels
            self._width = WIDTH
            self._kind = "mp3"
        else:
            audio.validate_pcm(data, self._channels, WIDTH)
            self._pcm = data
            self._width = WIDTH
            self._kind = "pcm"
        self._info = {
            "kind": self._kind,
            "rate": self._rate,
            "channels": self._channels,
            "width": self._width,
            "bytes": len(self._pcm),
            "duration": audio.duration(
                self._pcm, self._rate, self._channels, self._width),
        }
