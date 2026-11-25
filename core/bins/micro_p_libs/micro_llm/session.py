"""Одна беседа с LLM: системный промпт, история и TTL.

Сессия сама не ходит в сеть: она собирает `messages` для движка и
запоминает пару «вопрос - ответ». Время передаётся снаружи
(`now_ms`), чтобы поведение проверялось на хосте.

Если между вопросами прошло больше `ttl_ms`, история сбрасывается:
каждый вопрос становится новым разговором, системный промпт остаётся.
"""

from micro_llm.errors import LlmError
from micro_llm.text.plain import one_line
from micro_llm.text.system import limit_text

DEFAULT_TTL_MS = 10 * 60 * 1000
DEFAULT_MAX_TURNS = 6
DEFAULT_MAX_CHARS = 4000
DEFAULT_SYSTEM_CHARS = 2000


def clock_ms():
    """Текущее время в миллисекундах для MicroPython и хоста."""
    try:
        import time
    except ImportError:
        return 0
    ticks = getattr(time, "ticks_ms", None)
    if ticks is not None:
        return int(ticks())
    monotonic = getattr(time, "monotonic", None)
    if monotonic is not None:
        return int(monotonic() * 1000)
    return 0


def elapsed_ms(now_ms, start_ms):
    """Сколько прошло; учитывает переполнение `ticks_ms`."""
    try:
        import time
        diff = getattr(time, "ticks_diff", None)
        if diff is not None:
            return int(diff(now_ms, start_ms))
    except ImportError:
        pass
    return now_ms - start_ms


def _int(value, name, low):
    if isinstance(value, bool) or not isinstance(value, int):
        raise LlmError("{} должен быть целым числом".format(name))
    if value < low:
        raise LlmError("{} должен быть не меньше {}".format(name, low))
    return value


def _text(value, name):
    if not isinstance(value, str):
        raise LlmError("{} должен быть строкой".format(name))
    return value.strip()


class ChatSession:
    """История одной беседы и сборка `messages` для движка."""

    def __init__(self, system="", ttl_ms=DEFAULT_TTL_MS,
                 max_turns=DEFAULT_MAX_TURNS,
                 max_chars=DEFAULT_MAX_CHARS,
                 system_chars=DEFAULT_SYSTEM_CHARS):
        self.system = limit_text(_text(system, "system"), system_chars)
        self.ttl_ms = _int(ttl_ms, "ttl_ms", 0)
        self.max_turns = _int(max_turns, "max_turns", 0)
        self.max_chars = _int(max_chars, "max_chars", 0)
        self._pairs = []
        self._last_ms = None

    # --- состояние -------------------------------------------------

    def turns(self):
        return len(self._pairs)

    def chars(self):
        total = len(self.system)
        for question, answer in self._pairs:
            total += len(question) + len(answer)
        return total

    def history(self):
        result = []
        for question, answer in self._pairs:
            result.append({"role": "user", "content": question})
            result.append({"role": "assistant", "content": answer})
        return result

    def info(self):
        return {
            "turns": self.turns(),
            "chars": self.chars(),
            "system_chars": len(self.system),
            "last_ms": self._last_ms,
        }

    # --- время и сброс ---------------------------------------------

    def expired(self, now_ms=None):
        if self._last_ms is None:
            return False
        now_ms = clock_ms() if now_ms is None else _int(
            now_ms, "now_ms", 0)
        return elapsed_ms(now_ms, self._last_ms) > self.ttl_ms

    def reset(self):
        """Забыть историю; системный промпт остаётся."""
        self._pairs = []
        self._last_ms = None
        return self

    def _expire(self, now_ms):
        if self.expired(now_ms):
            self.reset()

    # --- сборка запроса --------------------------------------------

    def prepare(self, text, now_ms=None):
        """Сообщения для движка: system + история + новый вопрос."""
        question = _text(text, "text")
        if not question:
            raise LlmError("пустой текст вопроса")
        now_ms = clock_ms() if now_ms is None else _int(
            now_ms, "now_ms", 0)
        self._expire(now_ms)
        messages = []
        if self.system:
            system = one_line(self.system)
            if system:
                messages.append({"role": "system", "content": system})
        for item in self.history():
            content = one_line(item["content"])
            if content:
                messages.append({"role": item["role"], "content": content})
        messages.append({"role": "user", "content": one_line(question)})
        return messages

    def commit(self, question, answer, now_ms=None):
        """Запомнить пару «вопрос - ответ» и обрезать историю."""
        question = one_line(_text(question, "question"))
        answer = one_line(_text(answer, "answer"))
        if not question or not answer:
            raise LlmError("пустые вопрос или ответ")
        now_ms = clock_ms() if now_ms is None else _int(
            now_ms, "now_ms", 0)
        self._pairs.append((question, answer))
        self._last_ms = now_ms
        self._trim()
        return self

    def _trim(self):
        while self._pairs:
            too_many = len(self._pairs) > self.max_turns
            too_long = self.chars() > self.max_chars
            if not too_many and not too_long:
                return
            del self._pairs[0]
