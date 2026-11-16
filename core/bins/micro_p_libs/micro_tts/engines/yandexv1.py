"""Yandex SpeechKit: синтез речи, REST API v1.

`POST https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize`.
Параметры - в теле формы, ответ - PCM `s16le` моно (`format=lpcm`),
поэтому декодер не нужен.

Ключ - общий для платформы Яндекса (ASR и TTS): `api_key` или
`YANDEX_API` в `/home/.env`.
"""

import time

from micro_tts.engine.base import AudioFormat, Engine
from micro_tts.errors import TtsError
from micro_tts.net import http

HOST = "tts.api.cloud.yandex.net"
PATH = "/speech/v1/tts:synthesize"

DEFAULT_LANGUAGE = "ru-RU"
DEFAULT_VOICE = "filipp"
DEFAULT_EMOTION = "neutral"
DEFAULT_SPEED = 1.0
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_TIMEOUT = 15.0
DEFAULT_RETRY_DELAY = 0.5
DEFAULT_KEY_FILE = "/home/.env"

MAX_CHARS = 5000
MAX_REQUEST_BYTES = 9000
RATE_CHOICES = (8000, 16000, 48000)
EMOTIONS = ("neutral", "good", "evil")
KEY_NAMES = ("YANDEX_API",)

VOICES = (
    {"name": "filipp", "language": "ru-RU", "description": "мужской"},
    {"name": "ermil", "language": "ru-RU", "description": "мужской"},
    {"name": "zahar", "language": "ru-RU", "description": "мужской"},
    {"name": "madirus", "language": "ru-RU", "description": "мужской"},
    {"name": "oksana", "language": "ru-RU", "description": "женский"},
    {"name": "jane", "language": "ru-RU", "description": "женский"},
    {"name": "omazh", "language": "ru-RU", "description": "женский"},
)

_NAME_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)
_LANG_CHARS = _NAME_CHARS
_UNRESERVED = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.~"
)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise TtsError("{} должен быть непустой строкой".format(name))
    return value.strip()


def _chars(value, name, allowed):
    value = _text(value, name)
    for char in value:
        if char not in allowed:
            raise TtsError("неверное значение {}: {!r}".format(name, value))
    return value


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TtsError("{} должен быть числом".format(name))
    value = float(value)
    if value < low or value > high:
        raise TtsError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TtsError("{} должен быть целым числом".format(name))
    if value < low or value > high:
        raise TtsError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _optional(value, name, allowed):
    if value is None:
        return None
    value = _text(value, name)
    if value not in allowed:
        raise TtsError("{}: допустимо {}".format(name, ", ".join(allowed)))
    return value


def _encode(value):
    """Percent-encoding для формы (UTF-8)."""
    parts = []
    for byte in str(value).encode("utf-8"):
        char = chr(byte)
        if char in _UNRESERVED:
            parts.append(char)
        else:
            parts.append("%{:02X}".format(byte))
    return "".join(parts)


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
        import json
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
    """Синтез Yandex SpeechKit (API v1), PCM `s16le` моно."""

    name = "yandexv1"
    version = "1"

    def __init__(self):
        Engine.__init__(self)
        self.voice = DEFAULT_VOICE
        self.language = DEFAULT_LANGUAGE
        self.emotion = DEFAULT_EMOTION
        self.speed = DEFAULT_SPEED
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.folder_id = None
        self.timeout = DEFAULT_TIMEOUT
        self.retries = 1
        self.retry_delay = DEFAULT_RETRY_DELAY
        self.calls = 0
        self._api_key = None
        self._transport = http

    def open(self, voice=None, rate=1.0, pitch=1.0, **options):
        self.voice = _chars(
            DEFAULT_VOICE if voice is None else voice,
            "voice", _NAME_CHARS)
        self.language = _chars(
            options.get("lang", DEFAULT_LANGUAGE), "lang", _LANG_CHARS)
        self.emotion = _optional(
            options.get("emotion", DEFAULT_EMOTION),
            "emotion", EMOTIONS)
        self.speed = _number(
            options.get("speed", rate), "speed", 0.1, 3.0)
        sample_rate = options.get(
            "sample_rate", DEFAULT_SAMPLE_RATE)
        if isinstance(sample_rate, bool) or not isinstance(
                sample_rate, int):
            raise TtsError("sample_rate должен быть целым числом")
        if sample_rate not in RATE_CHOICES:
            raise TtsError(
                "Yandex: поддерживаются частоты 8000, 16000 и 48000")
        self.sample_rate = sample_rate
        folder = options.get("folder_id")
        self.folder_id = None if folder is None else _text(
            folder, "folder_id")
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
        raise TtsError(
            "Yandex: нет ключа; задайте api_key, {} или key_file".format(
                ", ".join(KEY_NAMES)))

    def voices(self):
        return [dict(item) for item in VOICES]

    def capabilities(self):
        return {
            "stream": False,
            "ssml": False,
            "rate": True,
            "pitch": False,
            "voices": True,
        }

    def cache_tag(self):
        return "{}:{}:{}:{}:{}:{}".format(
            self.name, self.version, self.voice, self.emotion,
            "{:.2f}".format(self.speed), self.sample_rate)

    def format(self):
        self._require_opened()
        return AudioFormat(self.sample_rate)

    def request_bytes(self):
        return MAX_REQUEST_BYTES

    def _form(self, text):
        params = [
            ("text", text),
            ("lang", self.language),
            ("voice", self.voice),
            ("emotion", self.emotion),
            ("speed", "{:.2f}".format(self.speed)),
            ("format", "lpcm"),
            ("sampleRateHertz", str(self.sample_rate)),
        ]
        if self.folder_id:
            params.append(("folderId", self.folder_id))
        pairs = []
        for name, value in params:
            pairs.append("{}={}".format(_encode(name), _encode(value)))
        return "&".join(pairs).encode("utf-8")

    def _audio(self, status, body):
        if status == 200:
            if not body:
                raise TtsError("Yandex: пустой ответ")
            return bytes(body)
        detail = _error_text(body)
        if status == 400:
            message = "Yandex: 400 - неверный запрос"
        elif status == 401:
            message = "Yandex: 401 - ключ не принят"
        elif status == 402:
            message = "Yandex: 402 - не оплачен биллинг"
        elif status == 403:
            message = ("Yandex: 403 - доступ запрещён "
                       "(роль, каталог или биллинг)")
        elif status == 429:
            message = "Yandex: 429 - превышена квота"
        else:
            message = "Yandex: HTTP {}".format(status)
        if detail:
            message = "{}: {}".format(message, detail)
        raise TtsError(message)

    def synthesize(self, text):
        """Текст → PCM `s16le` моно."""
        self._require_opened()
        text = _text(text, "text")
        if len(text) > MAX_CHARS:
            raise TtsError(
                "Yandex: текст {} символов, максимум {}".format(
                    len(text), MAX_CHARS))
        body = self._form(text)
        headers = {
            "Authorization": "Api-Key " + self._api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        attempt = 0
        while True:
            try:
                status, _headers, payload = self._transport.post(
                    HOST, PATH, body, headers=headers,
                    timeout=self.timeout, secure=True)
            except TtsError as exc:
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
            return self._audio(status, payload)

    def _pause(self):
        if self.retry_delay > 0:
            time.sleep(self.retry_delay)

    def close(self):
        self._api_key = None
        self._opened = False
