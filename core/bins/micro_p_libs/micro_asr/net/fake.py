"""Подставной транспорт: записывает запросы и отдаёт готовые ответы."""

from micro_asr.errors import AsrError


class FakeTransport:
    """Заменитель `post()` для тестов движка."""

    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def post(self, host, path, body=b"", headers=None, timeout=None,
             secure=True, port=None, limit=None):
        self.calls.append({
            "host": host,
            "path": path,
            "body": bytes(body),
            "headers": dict(headers or {}),
            "timeout": timeout,
            "secure": secure,
            "port": port,
        })
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AsrError("fake: нет ответа")
        return self.responses.pop(0)
