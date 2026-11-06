"""Источник аудио из памяти."""

from micro_asr import audio
from micro_asr.sources.base import (
    DEFAULT_RATE, WIDTH, Source, check_channels, check_width,
    positive_int)


class MemorySource(Source):
    """PCM из памяти."""

    name = "memory"

    def __init__(self, pcm, rate=DEFAULT_RATE, channels=1, width=WIDTH):
        audio.validate_pcm(pcm, channels, width)
        self._pcm = bytes(pcm)
        self._rate = positive_int(rate, "rate")
        self._channels = check_channels(channels)
        check_width(width)

    def read(self):
        return self._pcm

    def info(self):
        return {
            "kind": self.name,
            "rate": self._rate,
            "channels": self._channels,
            "width": WIDTH,
            "bytes": len(self._pcm),
            "duration": audio.duration(
                self._pcm, self._rate, self._channels, WIDTH),
        }
