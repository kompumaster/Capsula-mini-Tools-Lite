"""Отслеживание ключевого слова для колонки VK Капсула Мини."""

from micro_ww.config import Config
from micro_ww.engines.base import Engine
from micro_ww.engines.registry import available_engines, register_engine
from micro_ww.errors import WwError
from micro_ww.manifest import Manifest
from micro_ww.sources.base import Source
from micro_ww.window import ProbabilityWindow
from micro_ww.ww import WakeWord

__version__ = "0.1.0"

__all__ = [
    "Config",
    "Engine",
    "Manifest",
    "ProbabilityWindow",
    "Source",
    "WakeWord",
    "WwError",
    "register_engine",
    "available_engines",
    "__version__",
]
