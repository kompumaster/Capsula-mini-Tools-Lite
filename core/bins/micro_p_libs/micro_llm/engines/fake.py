"""Фиктивный LLM: отвечает «эхо» и отдаёт ответ кусками.

Нужен для тестов сессии и агента: без сети, детерминированно.
"""

from micro_llm.engine.base import Engine, check_messages

MAX_CHARS = 4000


class FakeEngine(Engine):
    """Ответ - префикс плюс последняя реплика пользователя."""

    name = "fake"
    version = "1"

    def __init__(self):
        Engine.__init__(self)
        self.model_name = "fake-echo"
        self.prefix = "эхо: "
        self.calls = 0

    def open(self, model=None, **options):
        if model is not None:
            self.model_name = str(model)
        self.prefix = str(options.get("prefix", self.prefix))
        self.calls = 0
        self._opened = True
        return self

    def capabilities(self):
        return {
            "stream": True,
            "system": True,
        }

    def model(self):
        return self.model_name

    def complete(self, messages):
        self._require_opened()
        items = check_messages(messages)
        self.calls += 1
        text = self.prefix + items[-1]["content"]
        return text[:MAX_CHARS]

    def stream(self, messages):
        text = self.complete(messages)
        step = max(1, len(text) // 3)
        for index in range(0, len(text), step):
            yield text[index:index + step]
