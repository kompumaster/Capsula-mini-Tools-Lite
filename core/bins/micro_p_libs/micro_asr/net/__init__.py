"""Сетевой слой: HTTP-транспорт и подстановка для тестов."""

from micro_asr.net.fake import FakeTransport
from micro_asr.net.http import parse_response, post

__all__ = ["post", "parse_response", "FakeTransport"]
