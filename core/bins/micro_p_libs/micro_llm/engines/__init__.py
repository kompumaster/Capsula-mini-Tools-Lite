"""Встроенные LLM-движки."""

from micro_llm.engine.registry import register_engine
from micro_llm.engines.deepseek import DeepSeekEngine
from micro_llm.engines.fake import FakeEngine
from micro_llm.engines.openai import OpenAiEngine

register_engine("fake", FakeEngine)
register_engine("deepseek", DeepSeekEngine)
register_engine("openai", OpenAiEngine)

__all__ = ["FakeEngine", "DeepSeekEngine", "OpenAiEngine"]
