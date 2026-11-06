"""micro_tts: синтез речи для MicroPython.

Публичный API пополняется по этапам. Сейчас доступны ошибка,
интерфейсы движка и плеера, формат PCM, реестр движков и координатор
`TTS`.
"""

from micro_tts.engine.base import AudioFormat, Engine
from micro_tts.engine.registry import available_engines, register_engine
from micro_tts.errors import TtsError
from micro_tts.player.base import Player
from micro_tts.text.base import Normalizer
from micro_tts.tts import TTS

__version__ = "0.2.0"

__all__ = [
    "TtsError", "Engine", "AudioFormat", "Player", "Normalizer", "TTS",
    "register_engine", "available_engines", "__version__",
]
