"""Транспорт для тестов: заранее заданные входящие сообщения."""

from micro_tts.net.base import Transport


class FakeTransport(Transport):
    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.sent = []
        self.connected = None
        self.closed = False

    def connect(self, url, headers=None, timeout=10.0):
        self.connected = (url, dict(headers or {}), timeout)
        return self

    def send_text(self, text):
        self.sent.append(("text", text))

    def send_binary(self, data):
        self.sent.append(("binary", data))

    def recv(self, timeout=None):
        if not self.messages:
            return "close", b""
        return self.messages.pop(0)

    def close(self):
        self.closed = True
