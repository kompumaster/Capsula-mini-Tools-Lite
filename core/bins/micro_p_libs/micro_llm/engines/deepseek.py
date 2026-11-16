"""DeepSeek: чат через REST, совместимый с OpenAI.

`POST https://api.deepseek.com/chat/completions`.
Ключ — `DEEPSEEK` в `/home/.env`, модель — `DS_MODEL` там же.
Режим размышлений по умолчанию выключен: для голосового ответа
важна скорость.
"""

import json
import time

from micro_llm.engine.base import Engine, check_messages
from micro_llm.errors import LlmError
from micro_llm.net import http, sse

HOST = "api.deepseek.com"
PATH = "/chat/completions"
MAX_ERROR_BYTES = 64 * 1024

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_MAX_TOKENS = 400
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRY_DELAY = 0.5
DEFAULT_KEY_FILE = "/home/.env"

KEY_NAMES = ("DEEPSEEK",)
MODEL_NAMES = ("DS_MODEL",)
MAX_TOKENS = 384000

_NAME_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._:"
)
_ERROR_HINTS = {
    400: "неверный запрос",
    401: "ключ не принят",
    402: "недостаточно средств",
    422: "неверные параметры",
    429: "превышен лимит",
    500: "ошибка сервиса",
    503: "сервис перегружен",
}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise LlmError("{} должен быть непустой строкой".format(name))
    return value.strip()


def _chars(value, name):
    value = _text(value, name)
    for char in value:
        if char not in _NAME_CHARS:
            raise LlmError("неверное значение {}: {!r}".format(name, value))
    return value


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LlmError("{} должен быть числом".format(name))
    value = float(value)
    if value < low or value > high:
        raise LlmError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise LlmError("{} должен быть целым числом".format(name))
    if value < low or value > high:
        raise LlmError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _flag(value, name):
    if not isinstance(value, bool):
        raise LlmError("{} должен быть True или False".format(name))
    return value


def _file_value(path, names):
    try:
        handle = open(path, "r")
    except OSError:
        return None
    try:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() in names:
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
    finally:
        handle.close()
    return None


def _env_value(names):
    try:
        import os
    except ImportError:
        return None
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _network_error(exc):
    return str(exc).startswith("сеть:")


def _delta(text):
    """Кусок текста из SSE-события `chat.completion.chunk`."""
    if not text:
        return ""
    try:
        data = json.loads(text)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices") or []
    if not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        return ""
    delta = choice.get("delta") or {}
    content = delta.get("content")
    if isinstance(content, str):
        return content
    return ""


def _error_text(body):
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        for name in ("message", "type", "code"):
            value = error.get(name)
            if isinstance(value, str) and value:
                return value
    for name in ("message", "error"):
        value = data.get(name)
        if isinstance(value, str) and value:
            return value
    return ""


class DeepSeekEngine(Engine):
    """Чат DeepSeek: `messages` → текст ответа."""

    name = "deepseek"
    version = "1"

    def __init__(self):
        Engine.__init__(self)
        self.model_name = DEFAULT_MODEL
        self.thinking = False
        self.max_tokens = DEFAULT_MAX_TOKENS
        self.temperature = DEFAULT_TEMPERATURE
        self.timeout = DEFAULT_TIMEOUT
        self.retries = 1
        self.retry_delay = DEFAULT_RETRY_DELAY
        self.calls = 0
        self.last_finish = None
        self.last_usage = None
        self._api_key = None
        self._transport = http

    def open(self, model=None, **options):
        value = model if model is not None else options.get("model")
        if value is None:
            value = _env_value(MODEL_NAMES) or DEFAULT_MODEL
        self.model_name = _chars(value, "model")
        self.thinking = _flag(
            options.get("thinking", False), "thinking")
        self.max_tokens = _integer(
            options.get("max_tokens", DEFAULT_MAX_TOKENS),
            "max_tokens", 1, MAX_TOKENS)
        self.temperature = _number(
            options.get("temperature", DEFAULT_TEMPERATURE),
            "temperature", 0, 2)
        self.timeout = _number(
            options.get("timeout", DEFAULT_TIMEOUT), "timeout", 1, 120)
        self.retries = _integer(
            options.get("retries", 1), "retries", 0, 5)
        self.retry_delay = _number(
            options.get("retry_delay", DEFAULT_RETRY_DELAY),
            "retry_delay", 0, 10)
        self._transport = options.get("transport") or http
        self._api_key = self._resolve_key(options)
        self.calls = 0
        self.last_finish = None
        self.last_usage = None
        self._opened = True
        return self

    def _resolve_key(self, options):
        value = options.get("api_key")
        if value is not None:
            return _text(value, "api_key")
        value = _env_value(KEY_NAMES)
        if value:
            return value
        path = options.get("key_file", DEFAULT_KEY_FILE)
        if path is not None:
            value = _file_value(path, KEY_NAMES)
            if value:
                return value
        raise LlmError(
            "DeepSeek: нет ключа; задайте api_key, {} или key_file".format(
                ", ".join(KEY_NAMES)))

    def capabilities(self):
        return {
            "stream": True,
            "system": True,
        }

    def model(self):
        return self.model_name

    def cache_tag(self):
        return "{}:{}:{}".format(self.name, self.version, self.model_name)

    def _payload(self, messages):
        return {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "thinking": {
                "type": "enabled" if self.thinking else "disabled",
            },
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

    def _answer(self, status, body):
        if status == 200:
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                raise LlmError("DeepSeek: не разобрать ответ")
            if not isinstance(data, dict):
                raise LlmError("DeepSeek: не разобрать ответ")
            choices = data.get("choices") or []
            if not choices:
                raise LlmError("DeepSeek: в ответе нет choices")
            choice = choices[0]
            message = choice.get("message") or {}
            content = message.get("content")
            finish = choice.get("finish_reason")
            self.last_finish = finish
            self.last_usage = data.get("usage")
            if not isinstance(content, str) or not content.strip():
                raise LlmError(
                    "DeepSeek: пустой ответ (finish_reason={})".format(
                        finish))
            return content.strip()
        detail = _error_text(body)
        hint = _ERROR_HINTS.get(status)
        if hint:
            message = "DeepSeek: {} — {}".format(status, hint)
        else:
            message = "DeepSeek: HTTP {}".format(status)
        if detail:
            message = "{}: {}".format(message, detail)
        raise LlmError(message)

    def complete(self, messages):
        """Список сообщений → текст ответа."""
        self._require_opened()
        items = check_messages(messages)
        body = json.dumps(self._payload(items)).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
        }
        attempt = 0
        while True:
            try:
                status, _headers, payload = self._transport.post(
                    HOST, PATH, body, headers=headers,
                    timeout=self.timeout, secure=True)
            except LlmError as exc:
                if attempt >= self.retries or not _network_error(exc):
                    raise
                attempt += 1
                self._pause()
                continue
            if status >= 500 and attempt < self.retries:
                attempt += 1
                self._pause()
                continue
            self.calls += 1
            return self._answer(status, payload)

    def _pause(self):
        if self.retry_delay > 0:
            time.sleep(self.retry_delay)

    def stream(self, messages):
        """Список сообщений → куски текста (SSE)."""
        self._require_opened()
        items = check_messages(messages)
        payload = self._payload(items)
        payload["stream"] = True
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        response = self._transport.start(
            HOST, PATH, body, headers=headers,
            timeout=self.timeout, secure=True)
        try:
            if response.status != 200:
                data = response.read_all(limit=MAX_ERROR_BYTES)
                self._answer(response.status, data)
            self.calls += 1
            reader = sse.SseReader(response)
            while True:
                event = reader.read_event()
                if event is None or event["done"]:
                    break
                piece = _delta(event["data"])
                if piece:
                    yield piece
        finally:
            response.close()

    def close(self):
        self._api_key = None
        self._opened = False
