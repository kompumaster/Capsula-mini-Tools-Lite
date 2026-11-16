"""Встроенные движки micro_tts."""

from micro_tts.engine.registry import register_engine
from micro_tts.engines.edge import EdgeEngine
from micro_tts.engines.fake import FakeEngine
from micro_tts.engines.yandexv1 import YandexV1Engine

register_engine("fake", FakeEngine)
register_engine("edge", EdgeEngine)
register_engine("yandexv1", YandexV1Engine)

__all__ = ["FakeEngine", "EdgeEngine", "YandexV1Engine"]
