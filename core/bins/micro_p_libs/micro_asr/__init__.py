"""Распознавание речи для колонки VK Капсула Мини."""

from micro_asr.asr import ASR
from micro_asr.engines.base import AudioFormat, Engine
from micro_asr.engines.registry import available_engines, register_engine
from micro_asr.errors import AsrError
from micro_asr.job import RecognitionJob

__version__ = "0.2.0"

__all__ = [
    "ASR",
    "AsrError",
    "AudioFormat",
    "Engine",
    "RecognitionJob",
    "register_engine",
    "available_engines",
    "__version__",
]
