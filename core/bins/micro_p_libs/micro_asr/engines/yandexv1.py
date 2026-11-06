"""Yandex SpeechKit: синхронное распознавание, REST API v1.

`POST https://stt.api.cloud.yandex.net/speech/v1/stt:recognize`.
Тело — PCM `s16le` моно; ответ — `{"result": "..."}`.
"""

import json
import time

from micro_asr import audio
from micro_asr.engines.base import AudioFormat, Engine
from micro_asr.errors import AsrError
from micro_asr.net import http

HOST = "stt.api.cloud.yandex.net"
PATH = "/speech/v1/stt:recognize"
DEFAULT_LANGUAGE = "ru-RU"
DEFAULT_TOPIC = "general"
DEFAULT_TIMEOUT = 15.0
DEFAULT_RETRY_DELAY = 0.5
DEFAULT_KEY_FILE = "/home/.env"
MAX_SECONDS = 30.0
MAX_BYTES = 1024 * 1024
RATE_CHOICES = (8000, 16000, 48000)
KEY_NAMES = ("ASR_YANDEXV1_KEY", "ASR_YANDEX_KEY", "ASR_YANDEX_API")

_LANGUAGE_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
)
_TOPIC_CHARS = _LANGUAGE_CHARS + "_:"


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise AsrError("{} должен быть непустой строкой".format(name))
    return value.strip()


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AsrError("{} должен быть числом".format(name))
    value = float(value)
    if value < low or value > high:
        raise AsrError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AsrError("{} должен быть целым числом".format(name))
    if value < low or value > high:
        raise AsrError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _flag(value, name):
    if not isinstance(value, bool):
        raise AsrError("{} должен быть True или False".format(name))
    return value


def _chars(value, name, allowed):
    value = _text(value, name)
    for char in value:
        if char not in allowed:
            raise AsrError("неверное значение {}: {!r}".format(name, value))
    return value


def _env_key():
    try:
        import os
    except ImportError:
        return None
    for name in KEY_NAMES:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _file_key(path):
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
            if name.strip() in KEY_NAMES:
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
    finally:
        handle.close()
    return None


def _network_error(exc):
    return str(exc).startswith("сеть:")


def _error_text(body):
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    for name in ("error_message", "message", "error", "error_code"):
        value = data.get(name)
        if isinstance(value, str) and value:
            return value
    return ""


class YandexV1Engine(Engine):
    """Синхронное распознавание Yandex SpeechKit (API v1)."""

    name = "yandexv1"
    version = "1"

    def __init__(self):
        Engine.__init__(self)
        self.sample_rate = 16000
        self.language = DEFAULT_LANGUAGE
        self.topic = DEFAULT_TOPIC
        self.profanity_filter = False
        self.raw_results = False
        self.timeout = DEFAULT_TIMEOUT
        self.retries = 1
        self.retry_delay = DEFAULT_RETRY_DELAY
        self.calls = 0
        self._api_key = None
        self._transport = http

    def open(self, language=None, sample_rate=16000, **options):
        language = _chars(
            DEFAULT_LANGUAGE if language is None else language,
            "language", _LANGUAGE_CHARS)
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, int):
            raise AsrError("sample_rate должен быть целым числом")
        if sample_rate not in RATE_CHOICES:
            raise AsrError(
                "Yandex: поддерживаются частоты 8000, 16000 и 48000")
        self.sample_rate = sample_rate
        self.language = language
        self.topic = _chars(
            options.get("topic", DEFAULT_TOPIC), "topic", _TOPIC_CHARS)
        self.profanity_filter = _flag(
            options.get("profanity_filter", False), "profanity_filter")
        self.raw_results = _flag(
            options.get("raw_results", False), "raw_results")
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
        self._opened = True
        return self

    def _resolve_key(self, options):
        value = options.get("api_key")
        if value is not None:
            return _text(value, "api_key")
        value = _env_key()
        if value:
            return value
        path = options.get("key_file", DEFAULT_KEY_FILE)
        if path is not None:
            value = _file_key(path)
            if value:
                return value
        raise AsrError(
            "Yandex: нет ключа; задайте api_key, {} или key_file".format(
                ", ".join(KEY_NAMES)))

    def capabilities(self):
        return {
            "stream": False,
            "languages": True,
        }

    def format(self):
        self._require_opened()
        return AudioFormat(self.sample_rate)

    def max_seconds(self):
        return MAX_SECONDS

    def max_bytes(self):
        return MAX_BYTES

    def _path(self):
        parts = [
            "lang={}".format(self.language),
            "topic={}".format(self.topic),
            "format=lpcm",
            "sampleRateHertz={}".format(self.sample_rate),
        ]
        if self.profanity_filter:
            parts.append("profanityFilter=true")
        if self.raw_results:
            parts.append("rawResults=true")
        return PATH + "?" + "&".join(parts)

    def _result(self, status, body):
        if status == 200:
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                raise AsrError("Yandex: не разобрать ответ")
            result = data.get("result") if isinstance(data, dict) else None
            if not isinstance(result, str) or not result.strip():
                raise AsrError("Yandex: пустой результат")
            return result
        detail = _error_text(body)
        if status == 400:
            message = "Yandex: 400 — неверный запрос"
        elif status == 401:
            message = "Yandex: 401 — ключ не принят"
        elif status == 403:
            message = ("Yandex: 403 — доступ запрещён "
                       "(роль, каталог или биллинг)")
        elif status == 429:
            message = "Yandex: 429 — превышена квота"
        else:
            message = "Yandex: HTTP {}".format(status)
        if detail:
            message = "{}: {}".format(message, detail)
        raise AsrError(message)

    def recognize(self, pcm):
        self._require_opened()
        audio.validate_pcm(pcm)
        if not pcm:
            raise AsrError("пустое аудио")
        seconds = audio.duration(pcm, self.sample_rate)
        if seconds > MAX_SECONDS:
            raise AsrError(
                "Yandex: аудио {:.1f} с длиннее 30 с".format(seconds))
        if len(pcm) > MAX_BYTES:
            raise AsrError(
                "Yandex: аудио {} байт больше 1 МБ".format(len(pcm)))
        path = self._path()
        headers = {"Authorization": "Api-Key " + self._api_key}
        attempt = 0
        while True:
            try:
                status, _headers, body = self._transport.post(
                    HOST, path, pcm, headers=headers,
                    timeout=self.timeout, secure=True)
            except AsrError as exc:
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
            return self._result(status, body)

    def _pause(self):
        if self.retry_delay > 0:
            time.sleep(self.retry_delay)

    def close(self):
        self._api_key = None
        self._opened = False
