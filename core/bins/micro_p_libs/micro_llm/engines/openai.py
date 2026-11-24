"""OpenAI-совместимый движок: чат через REST.

Настройки берутся только из окружения или `/home/.env`:

- `OAI_LLM_API` - ключ;
- `OAI_LLM_URL` - полный адрес с префиксом, например
  `https://api.openai.com/v1`;
- `OAI_LLM_MODEL` - имя модели.

Значений по умолчанию нет. Если чего-то не хватает или запрос не
удался, движок возвращает текст ошибки как ответ и помечает
`last_error`; клиент такой ответ не пишет в историю.
"""

import json
import time

from micro_llm.engine.base import Engine, check_messages
from micro_llm.errors import LlmError
from micro_llm.net import http, sse

KEY_NAMES = ("OAI_LLM_API",)
URL_NAMES = ("OAI_LLM_URL",)
MODEL_NAMES = ("OAI_LLM_MODEL",)
DEFAULT_KEY_FILE = "/home/.env"

DEFAULT_MAX_TOKENS = 400
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRY_DELAY = 0.5
MAX_TOKENS = 384000
MAX_ERROR_BYTES = 64 * 1024

ENDPOINT = "/chat/completions"

_ERROR_HINTS = {
    400: "неверный запрос",
    401: "ключ не принят",
    402: "недостаточно средств",
    403: "доступ запрещён",
    404: "адрес не найден",
    422: "неверные параметры",
    429: "превышен лимит",
    500: "ошибка сервиса",
    502: "шлюз недоступен",
    503: "сервис перегружен",
}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise LlmError("{} должен быть непустой строкой".format(name))
    return value.strip()


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


def _pick(options, option, names, key_file):
    """Опция, окружение, файл; None, если нигде нет."""
    value = options.get(option)
    if value is not None:
        return _text(value, option)
    value = _env_value(names)
    if value:
        return value
    if key_file is not None:
        value = _file_value(key_file, names)
        if value:
            return value
    return None


def parse_url(text):
    """Разобрать полный URL: `(host, port, path, secure)`."""
    value = _text(text, "url")
    if "://" not in value:
        raise LlmError(
            "URL должен начинаться с http:// или https://")
    scheme, rest = value.split("://", 1)
    scheme = scheme.lower()
    if scheme not in ("http", "https"):
        raise LlmError("URL: схема только http или https")
    if "?" in rest or "#" in rest:
        raise LlmError("URL не должен содержать ? или #")
    if "/" in rest:
        hostpart, path = rest.split("/", 1)
        path = "/" + path
    else:
        hostpart, path = rest, ""
    if not hostpart:
        raise LlmError("URL без хоста")
    if "@" in hostpart:
        raise LlmError("URL с логином не поддерживается")
    if any(char in hostpart for char in (" ", "\t")):
        raise LlmError("URL: пробел в хосте")

    port = None
    if hostpart.startswith("["):
        end = hostpart.find("]")
        if end < 0:
            raise LlmError("URL: незакрытая скобка IPv6")
        host = hostpart[1:end]
        tail = hostpart[end + 1:]
        if tail:
            if not tail.startswith(":"):
                raise LlmError("URL: лишние символы после IPv6")
            port = tail[1:]
    else:
        if hostpart.count(":") > 1:
            raise LlmError("URL: лишние двоеточия")
        if ":" in hostpart:
            host, port = hostpart.split(":", 1)
        else:
            host = hostpart
    if not host:
        raise LlmError("URL без хоста")
    if port:
        try:
            port = int(port)
        except ValueError:
            raise LlmError("URL: порт не число")
        if port < 1 or port > 65535:
            raise LlmError("URL: порт вне 1…65535")
    else:
        port = 443 if scheme == "https" else 80

    path = path.rstrip("/")
    if any(char in path for char in (" ", "\t")):
        raise LlmError("URL: пробел в пути")
    if not path.endswith(ENDPOINT):
        path += ENDPOINT
    if not path.startswith("/"):
        path = "/" + path
    return host, port, path, scheme == "https"


def _network_error(exc):
    return str(exc).startswith("сеть:")


def _failure(exc):
    text = str(exc)
    if text.startswith("OpenAI:"):
        return text
    return "OpenAI: " + text


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


class OpenAiEngine(Engine):
    """OpenAI-совместимый чат: `messages` → текст ответа."""

    name = "openai"
    version = "1"

    def __init__(self):
        Engine.__init__(self)
        self.model_name = None
        self.host = None
        self.port = None
        self.path = None
        self.secure = True
        self.max_tokens = DEFAULT_MAX_TOKENS
        self.temperature = DEFAULT_TEMPERATURE
        self.timeout = DEFAULT_TIMEOUT
        self.retries = 1
        self.retry_delay = DEFAULT_RETRY_DELAY
        self.calls = 0
        self.last_finish = None
        self.last_usage = None
        self._api_key = None
        self._config_error = None
        self._transport = http

    def open(self, model=None, **options):
        self.last_error = None
        self._config_error = None
        self.calls = 0
        self.last_finish = None
        self.last_usage = None
        self._opened = True

        try:
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
        except LlmError as exc:
            self._config_error = _failure(exc)
            return self

        key_file = options.get("key_file", DEFAULT_KEY_FILE)
        problems = []
        try:
            key = options.get("api_key")
            if key is None:
                key = _pick({}, "api_key", KEY_NAMES, key_file)
            self._api_key = _text(key, "api_key") if key else None
        except LlmError as exc:
            self._api_key = None
            problems.append(str(exc))
        if not self._api_key:
            problems.append("нет OAI_LLM_API")

        url = _pick(options, "url", URL_NAMES, key_file)
        if not url:
            problems.append("нет OAI_LLM_URL")
        else:
            try:
                self.host, self.port, self.path, self.secure = parse_url(url)
            except LlmError as exc:
                problems.append(str(exc))

        value = model if model is not None else _pick(
            options, "model", MODEL_NAMES, key_file)
        if not value:
            problems.append("нет OAI_LLM_MODEL")
        else:
            try:
                self.model_name = _text(value, "model")
            except LlmError as exc:
                problems.append(str(exc))

        if problems:
            self._config_error = "OpenAI: " + "; ".join(problems)
        return self

    def capabilities(self):
        return {
            "stream": True,
            "system": True,
        }

    def model(self):
        return self.model_name or ""

    def cache_tag(self):
        return "{}:{}:{}".format(self.name, self.version, self.model_name)

    def _payload(self, messages):
        return {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

    def _answer(self, status, body):
        if status == 200:
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                raise LlmError("OpenAI: не разобрать ответ")
            if not isinstance(data, dict):
                raise LlmError("OpenAI: не разобрать ответ")
            choices = data.get("choices") or []
            if not choices:
                raise LlmError("OpenAI: в ответе нет choices")
            choice = choices[0]
            message = choice.get("message") or {}
            content = message.get("content")
            finish = choice.get("finish_reason")
            self.last_finish = finish
            self.last_usage = data.get("usage")
            if not isinstance(content, str) or not content.strip():
                raise LlmError(
                    "OpenAI: пустой ответ (finish_reason={})".format(finish))
            return content.strip()
        detail = _error_text(body)
        hint = _ERROR_HINTS.get(status)
        if hint:
            message = "OpenAI: {} - {}".format(status, hint)
        else:
            message = "OpenAI: HTTP {}".format(status)
        if detail:
            message = "{}: {}".format(message, detail)
        raise LlmError(message)

    def _pause(self):
        if self.retry_delay > 0:
            time.sleep(self.retry_delay)

    def complete(self, messages):
        """Список сообщений → текст ответа (или текст ошибки)."""
        self._require_opened()
        self.last_error = None
        if self._config_error:
            self.last_error = self._config_error
            return self._config_error
        try:
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
                        self.host, self.path, body, headers=headers,
                        timeout=self.timeout, secure=self.secure,
                        port=self.port)
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
        except LlmError as exc:
            self.last_error = _failure(exc)
            return self.last_error

    def stream(self, messages):
        """Список сообщений → куски текста (SSE) или текст ошибки."""
        self._require_opened()
        self.last_error = None
        if self._config_error:
            self.last_error = self._config_error
            yield self._config_error
            return
        response = None
        try:
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
                self.host, self.path, body, headers=headers,
                timeout=self.timeout, secure=self.secure,
                port=self.port)
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
        except LlmError as exc:
            self.last_error = _failure(exc)
            yield self.last_error
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
