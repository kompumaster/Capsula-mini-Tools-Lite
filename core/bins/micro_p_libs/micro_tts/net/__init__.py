"""Транспорт для Edge TTS: WebSocket и тестовая заглушка."""

from micro_tts.net.base import Transport
from micro_tts.net.fake import FakeTransport
from micro_tts.net.websocket import WebSocketTransport, parse_url

__all__ = ["Transport", "WebSocketTransport", "FakeTransport", "parse_url"]
