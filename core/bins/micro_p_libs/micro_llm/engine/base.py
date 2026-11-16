"""Базовый интерфейс LLM-движка.

Движок только ведёт диалог: получает готовый список сообщений и
возвращает текст ответа (или его куски). Он не знает про ASR, TTS,
железо и сессии.
"""

from micro_llm.errors import LlmError

ROLES = ("system", "user", "assistant")


def check_messages(messages):
    """Проверить и нормализовать список сообщений."""
    if not isinstance(messages, (list, tuple)) or not messages:
        raise LlmError("messages: нужен непустой список")
    result = []
    for item in messages:
        if not isinstance(item, dict):
            raise LlmError("messages: элемент должен быть словарём")
        role = item.get("role")
        if role not in ROLES:
            raise LlmError("messages: неверная роль {!r}".format(role))
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LlmError("messages: пустой content")
        result.append({"role": role, "content": content})
    return result


class Engine:
    """Базовый класс LLM-движка.

    Наследник реализует `open` и `complete`; потоковый `stream`
    необязателен.
    """

    name = "base"
    version = "1"

    def __init__(self):
        self._opened = False

    def open(self, model=None, **options):
        """Подготовить движок; ошибка - `LlmError`."""
        raise LlmError(
            "движок {} не реализует open()".format(self.name))

    def capabilities(self):
        """Что умеет движок."""
        return {
            "stream": False,
            "system": True,
        }

    def model(self):
        """Имя модели, с которой работает движок."""
        return ""

    def cache_tag(self):
        """Стабильная строка для ключа кеша и логов."""
        return "{}:{}".format(self.name, self.version)

    def complete(self, messages):
        """Список сообщений → текст ответа."""
        raise LlmError(
            "движок {} не реализует complete()".format(self.name))

    def stream(self, messages):
        """Куски текста ответа; по умолчанию - один кусок."""
        raise LlmError(
            "движок {} не поддерживает поток".format(self.name))

    def close(self):
        """Освободить ресурсы; повторный вызов безопасен."""
        self._opened = False

    def opened(self):
        return self._opened

    def _require_opened(self):
        if not self._opened:
            raise LlmError("движок {} не открыт".format(self.name))
