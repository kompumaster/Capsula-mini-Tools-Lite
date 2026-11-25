"""micro_llm: клиент LLM для MicroPython.

Публичный API: клиент и сессия, ошибка слоя, интерфейс движка,
реестр движков.
"""

from micro_llm.engine.base import Engine, check_messages
from micro_llm.engine.registry import (
    available_engines, get_engine, register_engine)
from micro_llm.errors import LlmError
from micro_llm.session import ChatSession
from micro_llm.client import LlmClient

__version__ = "0.1.3"

__all__ = [
    "LlmError", "Engine", "check_messages", "ChatSession", "LlmClient",
    "register_engine", "available_engines", "get_engine",
    "__version__",
]
