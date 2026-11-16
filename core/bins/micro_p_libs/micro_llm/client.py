"""Клиент LLM: движок + сессия.

`ask()` — один запрос-ответ (блокирующий). `stream()` — то же, но
ответ приходит кусками; история пополняется только после полного
ответа.
"""

from micro_llm.engine.registry import get_engine
from micro_llm.errors import LlmError
from micro_llm.session import (
    DEFAULT_MAX_CHARS, DEFAULT_MAX_TURNS, DEFAULT_TTL_MS, ChatSession,
    clock_ms)
from micro_llm.text.system import DEFAULT_SYSTEM_FILE, load_system

_UNSET = object()


class LlmClient:
    """Диалог с LLM: собирает сообщения, зовёт движок, ведёт сессию."""

    def __init__(self, engine=None, system="", system_file=_UNSET,
                 ttl_ms=DEFAULT_TTL_MS, max_turns=DEFAULT_MAX_TURNS,
                 max_chars=DEFAULT_MAX_CHARS, system_chars=2000,
                 session=None):
        self.engine_spec = engine
        self.system = system
        self.system_file = (DEFAULT_SYSTEM_FILE
                            if system_file is _UNSET else system_file)
        self.ttl_ms = ttl_ms
        self.max_turns = max_turns
        self.max_chars = max_chars
        self.system_chars = system_chars
        self._engine = None
        self._session = session
        self._opened = False

    # --- открытие ---------------------------------------------------

    def open(self, model=None, **options):
        if self._opened:
            return self
        if self._engine is None:
            self._engine = get_engine(self.engine_spec)
            self._manager = True
        self._engine.open(model, **options)
        if self._session is None:
            text = self.system
            if not text and self.system_file:
                text = load_system(self.system_file,
                                   self.system_chars)
            self._session = ChatSession(
                system=text, ttl_ms=self.ttl_ms,
                max_turns=self.max_turns, max_chars=self.max_chars,
                system_chars=self.system_chars)
        self._opened = True
        return self

    def _require(self):
        if not self._opened:
            raise LlmError("LLM-клиент не открыт")

    # --- запросы ----------------------------------------------------

    def ask(self, text, now_ms=None):
        """Вопрос → ответ; история пополняется."""
        self._require()
        messages = self._session.prepare(text, now_ms)
        answer = self._engine.complete(messages)
        self._session.commit(text, answer, now_ms)
        return answer

    def stream(self, text, now_ms=None):
        """Вопрос → куски ответа; история — после полного ответа."""
        self._require()
        messages = self._session.prepare(text, now_ms)
        parts = []
        for piece in self._engine.stream(messages):
            if not piece:
                continue
            parts.append(piece)
            yield piece
        answer = "".join(parts).strip()
        if answer:
            self._session.commit(text, answer, now_ms)

    def reset(self):
        """Забыть историю (системный промпт остаётся)."""
        self._require()
        return self._session.reset()

    def session(self):
        return self._session

    def engine(self):
        return self._engine

    def info(self):
        session = self._session
        return {
            "engine": getattr(self._engine, "name", None),
            "model": (self._engine.model()
                      if self._engine is not None else None),
            "opened": self._opened,
            "turns": session.turns() if session is not None else 0,
            "chars": session.chars() if session is not None else 0,
            "last_ms": (session.info()["last_ms"]
                        if session is not None else None),
            "now_ms": clock_ms(),
        }

    def close(self):
        self._opened = False
        if self._engine is not None:
            try:
                self._engine.close()
            except Exception:
                pass
        return True
