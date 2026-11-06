"""Источники аудио."""

from micro_asr.sources.base import Source
from micro_asr.sources.file import FileSource
from micro_asr.sources.memory import MemorySource
from micro_asr.sources.mic import MicroHalMic

__all__ = ["Source", "MemorySource", "FileSource", "MicroHalMic"]
