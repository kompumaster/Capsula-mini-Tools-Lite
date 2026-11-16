"""Разбор Server-Sent Events поверх `http.Response`.

Каждое событие - набор строк `field: value`, события разделены пустой
строкой. Нам нужны `data` и (необязательно) `event`.
"""

from micro_llm.errors import LlmError

READ_SIZE = 4096


def _parse(raw):
    try:
        text = raw.decode("utf-8")
    except Exception:
        raise LlmError("SSE: не разобрать текст")
    lines = text.replace("\r", "").split("\n")
    data = []
    event = None
    for line in lines:
        if not line or line.startswith(":"):
            continue
        name, separator, value = line.partition(":")
        if not separator:
            continue
        name = name.strip()
        value = value[1:] if value.startswith(" ") else value
        if name == "data":
            data.append(value)
        elif name == "event":
            event = value.strip()
    payload = "\n".join(data)
    return {
        "event": event,
        "data": payload,
        "done": payload == "[DONE]",
    }


class SseReader:
    """Читает события по одному, не буферизуя весь ответ."""

    def __init__(self, response, size=READ_SIZE):
        self._response = response
        self._size = int(size)
        self._buffer = bytearray()
        self._pos = 0
        self._eof = False

    def _fill(self):
        chunk = self._response.read(self._size)
        if not chunk:
            self._eof = True
            return False
        self._buffer.extend(chunk)
        return True

    def _rest(self):
        if self._pos >= len(self._buffer):
            return b""
        return bytes(self._buffer[self._pos:])

    def read_event(self):
        """Следующее событие или `None` в конце."""
        while True:
            index = self._buffer.find(b"\n\n", self._pos)
            if index >= 0:
                raw = bytes(self._buffer[self._pos:index])
                self._pos = index + 2
                if self._pos >= len(self._buffer):
                    self._buffer = bytearray()
                    self._pos = 0
                return _parse(raw)
            if not self._fill():
                raw = self._rest()
                self._buffer = bytearray()
                self._pos = 0
                if raw.strip():
                    return _parse(raw)
                return None
