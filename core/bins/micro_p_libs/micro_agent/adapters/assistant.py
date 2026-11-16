"""Ассистент: интерфейс LLM и простые заглушки.

`LlmAssistant` — настоящий ответ через `micro_llm`;
`EchoAssistant` и `ScriptedAssistant` нужны для тестов и когда LLM
недоступна.
"""

import time


class Assistant:
    """Ответ на текст вопроса."""

    def ask(self, text):
        raise NotImplementedError


class LlmAssistant(Assistant):
    """Ответ через `micro_llm.LlmClient` (движок и сессия)."""

    def __init__(self, client):
        if client is None:
            raise ValueError("нужен клиент LLM")
        self.client = client

    def ask(self, text):
        if not isinstance(text, str) or not text.strip():
            return ""
        return self.client.ask(text)


class EchoAssistant(Assistant):
    """Заглушка LLM: пауза `delay` секунд и тот же текст."""

    def __init__(self, delay=3.0, sleep=None):
        if isinstance(delay, bool) or not isinstance(delay, (int, float)):
            raise ValueError("delay должен быть числом")
        delay = float(delay)
        if delay < 0:
            raise ValueError("delay не может быть отрицательным")
        self.delay = delay
        self._sleep = sleep if sleep is not None else time.sleep

    def ask(self, text):
        if not isinstance(text, str) or not text.strip():
            return ""
        if self.delay:
            self._sleep(self.delay)
        return text


class ScriptedAssistant(Assistant):
    """Заглушка для тестов: заранее заданные ответы."""

    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.asked = []

    def ask(self, text):
        self.asked.append(text)
        if not self.answers:
            return ""
        return self.answers.pop(0)
