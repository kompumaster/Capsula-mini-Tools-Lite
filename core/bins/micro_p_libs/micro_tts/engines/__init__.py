"""Встроенные движки micro_tts."""

from micro_tts.engine.registry import register_engine
from micro_tts.engines.edge import EdgeEngine
from micro_tts.engines.fake import FakeEngine

register_engine("fake", FakeEngine)
register_engine("edge", EdgeEngine)

__all__ = ["FakeEngine", "EdgeEngine"]
