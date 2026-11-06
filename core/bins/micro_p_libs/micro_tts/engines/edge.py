"""Edge TTS: WebSocket, SSML, MP3 и Sec-MS-GEC.

Сетевой транспорт и C-обёртки подключаются лениво. Для тестов можно
передать fake-транспорт, fake-декодер и fake-DRM.
"""

import json
import os
import random
import time

from micro_tts.engine.base import AudioFormat, Engine
from micro_tts.errors import TtsError

URL_BASE = (
    "wss://speech.platform.bing.com/consumer/speech/synthesize/"
    "readaloud/edge/v1")
TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
SEC_MS_GEC_VERSION = "2-143.0.3650.75"
DEFAULT_VOICE = "ru-RU-DmitryNeural"
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
ORIGIN = "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 "
    "Edg/143.0.0.0")

VOICES = (
    {"name": "ru-RU-DmitryNeural", "language": "ru-RU",
     "description": "мужской"},
    {"name": "ru-RU-SvetlanaNeural", "language": "ru-RU",
     "description": "женский"},
)


def _hex(count):
    try:
        data = os.urandom(count)
    except AttributeError:
        data = bytes(random.getrandbits(8) for _index in range(count))
    result = ""
    for byte in data:
        result += "{:02x}".format(byte)
    return result


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TtsError("{} должен быть числом".format(name))
    value = float(value)
    if value < 0.5 or value > 2.0:
        raise TtsError("{} должен быть в 0.5…2.0".format(name))
    return value


def _date_string():
    now = time.gmtime()
    weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return ("{} {} {:02d} {:04d} {:02d}:{:02d}:{:02d} "
            "GMT+0000 (Coordinated Universal Time)").format(
                weekdays[now[6] % 7], months[now[1] - 1], now[2],
                now[0], now[3], now[4], now[5])


def _retryable(exc):
    """Стоит ли повторять запрос после этой ошибки."""
    text = str(exc).lower()
    for marker in ("соединение закрыто", "etimedout", "timed out",
                   "connection reset", "errno 110"):
        if marker in text:
            return True
    return False


def _escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _voice_full(voice):
    if voice.startswith("Microsoft Server Speech Text to Speech Voice"):
        return voice
    parts = voice.split("-", 2)
    if len(parts) != 3:
        raise TtsError("неверное имя голоса: {!r}".format(voice))
    language, region, name = parts
    if "-" in name:
        extra, name = name.split("-", 1)
        region = region + "-" + extra
    return (
        "Microsoft Server Speech Text to Speech Voice "
        "({}-{}, {})".format(language, region, name))


def _rate_string(value):
    percent = int(round((_number(value, "rate") - 1.0) * 100))
    return "{:+d}%".format(percent)


def _pitch_string(value):
    hertz = int(round((_number(value, "pitch") - 1.0) * 100))
    return "{:+d}Hz".format(hertz)


def _parse_headers(raw):
    headers = {}
    for line in raw.split(b"\r\n"):
        if b":" not in line:
            continue
        name, value = line.split(b":", 1)
        headers[name.strip().lower()] = value.strip()
    return headers


class EdgeEngine(Engine):
    name = "edge"
    version = "1"

    def __init__(self, transport=None, decoder=None, drm=None,
                 clock=None, trusted_token=TRUSTED_CLIENT_TOKEN,
                 output_format=OUTPUT_FORMAT):
        Engine.__init__(self)
        self._transport = transport
        self._decoder = decoder
        self._drm = drm
        self._clock = clock if clock is not None else time.time
        self.trusted_token = trusted_token
        self.output_format = output_format
        self.voice = None
        self.edge_rate = "+0%"
        self.edge_pitch = "+0Hz"
        self.edge_volume = "+0%"
        self.timeout = 30.0
        self.retries = 2
        self.retry_delay = 0.5

    # --- интерфейс движка -----------------------------------------

    def open(self, voice=None, rate=1.0, pitch=1.0, **options):
        voice = DEFAULT_VOICE if voice is None else str(voice)
        self.voice = _voice_full(voice)
        self.edge_rate = options.get("edge_rate", _rate_string(rate))
        self.edge_pitch = options.get("edge_pitch", _pitch_string(pitch))
        self.edge_volume = options.get("edge_volume", "+0%")
        self.output_format = options.get(
            "output_format", self.output_format)
        self.trusted_token = options.get(
            "trusted_token", self.trusted_token)
        self.timeout = float(options.get("timeout", self.timeout))
        if self.timeout <= 0:
            raise TtsError("timeout должен быть больше нуля")
        self.retries = int(options.get("retries", self.retries))
        if self.retries < 0:
            raise TtsError("retries не может быть отрицательным")
        self.retry_delay = float(options.get(
            "retry_delay", self.retry_delay))
        if self.retry_delay < 0:
            raise TtsError("retry_delay не может быть отрицательным")
        if "'" in self.voice:
            raise TtsError("недопустимое имя голоса")
        self._opened = True
        return self

    def voices(self):
        return [dict(item) for item in VOICES]

    def capabilities(self):
        return {
            "stream": True,
            "ssml": False,
            "rate": True,
            "pitch": True,
            "voices": True,
        }

    def cache_tag(self):
        return "{}:{}:{}".format(self.name, self.version,
                                 self.output_format)

    def format(self):
        self._require_opened()
        return AudioFormat(24000)

    # --- создание зависимостей ------------------------------------

    def _make(self, spec, factory):
        if spec is None:
            return factory()
        if callable(spec):
            return spec()
        return spec

    def _new_transport(self):
        if self._transport is None:
            try:
                from micro_tts.net.websocket import WebSocketTransport
            except Exception as exc:
                raise TtsError("нет WebSocket/TLS: {}".format(exc))
            return WebSocketTransport()
        return self._make(self._transport, None)

    def _new_decoder(self):
        if self._decoder is None:
            from micro_tts.engines.mp3 import Mp3Decoder
            return Mp3Decoder()
        return self._make(self._decoder, None)

    def _new_drm(self):
        if self._drm is None:
            from micro_tts.engines.edge_drm import EdgeDrm
            return EdgeDrm(trusted_token=self.trusted_token)
        return self._make(self._drm, None)

    # --- сообщения -------------------------------------------------

    def _url(self, connection_id, token):
        return (
            "{}?TrustedClientToken={}&ConnectionId={}"
            "&Sec-MS-GEC={}&Sec-MS-GEC-Version={}".format(
                URL_BASE, self.trusted_token, connection_id,
                token, SEC_MS_GEC_VERSION))

    def _headers(self, muid):
        return {
            "Origin": ORIGIN,
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": USER_AGENT,
            "Cookie": "muid={};".format(muid),
        }

    def _config(self):
        body = json.dumps({
            "context": {
                "synthesis": {
                    "audio": {
                        "metadataoptions": {
                            "sentenceBoundaryEnabled": "false",
                            "wordBoundaryEnabled": "false",
                        },
                        "outputFormat": self.output_format,
                    }
                }
            }
        }, separators=(",", ":"))
        return (
            "X-Timestamp:{}\r\n"
            "Content-Type:application/json; charset=utf-8\r\n"
            "Path:speech.config\r\n\r\n"
            "{}\r\n".format(_date_string(), body))

    def _ssml(self, text, request_id):
        body = (
            "<speak version='1.0' "
            "xmlns='http://www.w3.org/2001/10/synthesis' "
            "xml:lang='en-US'>"
            "<voice name='{}'>"
            "<prosody pitch='{}' rate='{}' volume='{}'>{}</prosody>"
            "</voice></speak>".format(
                self.voice, self.edge_pitch, self.edge_rate,
                self.edge_volume, _escape(text)))
        return (
            "X-RequestId:{}\r\n"
            "Content-Type:application/ssml+xml\r\n"
            "X-Timestamp:{}Z\r\n"
            "Path:ssml\r\n\r\n"
            "{}".format(request_id, _date_string(), body))

    # --- синтез ----------------------------------------------------

    def encoded_format(self):
        return "mp3"

    def synthesize(self, text):
        """Текст → весь PCM (для коротких фраз)."""
        pcm = bytearray()
        for chunk, _data in self._collect(text):
            if chunk:
                pcm.extend(chunk)
        return bytes(pcm)

    def synthesize_pair(self, text):
        """Текст → `(pcm, mp3)` для кеша без перекодирования."""
        pcm = bytearray()
        encoded = bytearray()
        for chunk, data in self._collect(text):
            if chunk:
                pcm.extend(chunk)
            if data:
                encoded.extend(data)
        return bytes(pcm), bytes(encoded)

    def stream(self, text):
        """Текст → куски PCM; обрыв соединения повторяем."""
        for chunk, _data in self._collect(text):
            if chunk:
                yield chunk

    def _collect(self, text):
        """Поток `(pcm, mp3)`; обрыв повторяется, пока нет данных."""
        self._require_opened()
        if not isinstance(text, str):
            raise TtsError("текст должен быть строкой")
        if not text.strip():
            raise TtsError("текст пустой")
        try:
            size = len(text.encode("utf-8"))
        except AttributeError:
            size = len(text)
        limit = self.request_bytes()
        if limit and size > limit:
            raise TtsError(
                "Edge: текст длиннее {} байт".format(limit))

        attempt = 0
        while True:
            emitted = False
            try:
                for chunk, data in self._collect_once(text):
                    emitted = True
                    yield chunk, data
                return
            except TtsError as exc:
                if (emitted or attempt >= self.retries
                        or not _retryable(exc)):
                    raise
                attempt += 1
                if self.retry_delay > 0:
                    time.sleep(self.retry_delay)

    def _collect_once(self, text):
        """Одна попытка: кадры Edge, PCM и исходный MP3."""
        transport = self._new_transport()
        decoder = self._new_decoder()
        drm = self._new_drm()
        timestamp = self._clock()
        token = drm.token(timestamp)
        connection_id = _hex(16)
        request_id = _hex(16)
        muid = _hex(16).upper()

        audio_seen = False
        response_body = b""
        try:
            try:
                transport.connect(
                    self._url(connection_id, token),
                    self._headers(muid), timeout=self.timeout)
            except TtsError as exc:
                if "403" in str(exc):
                    raise TtsError(
                        "Edge: 403 — доступ запрещён "
                        "(проверьте время/NTP)")
                raise
            decoder.open(24000)
            transport.send_text(self._config())
            transport.send_text(self._ssml(text, request_id))
            while True:
                kind, payload = transport.recv(self.timeout)
                if kind == "close":
                    raise TtsError(
                        "Edge: соединение закрыто без turn.end")
                if kind == "text":
                    if b"\r\n\r\n" not in payload:
                        continue
                    head, body = payload.split(b"\r\n\r\n", 1)
                    headers = _parse_headers(head)
                    path = headers.get(b"path", b"").decode(
                        "ascii", "replace")
                    if path == "turn.end":
                        break
                    if path == "response":
                        response_body = body
                    continue
                if kind != "binary":
                    continue
                if len(payload) < 2:
                    continue
                header_length = int.from_bytes(payload[:2], "big")
                if header_length <= 0 or len(payload) < 2 + header_length:
                    continue
                headers = _parse_headers(
                    payload[2:2 + header_length])
                content_type = headers.get(b"content-type", b"").decode(
                    "ascii", "replace")
                if not content_type.startswith("audio/"):
                    continue
                data = payload[2 + header_length:]
                if not data:
                    continue
                audio_seen = True
                yield b"", data
                decoder.feed(data)
                while True:
                    chunk = decoder.read(4096)
                    if not chunk:
                        break
                    yield chunk, b""
            if not audio_seen:
                detail = response_body[:160].decode(
                    "utf-8", "replace")
                raise TtsError(
                    "Edge: нет аудио{}".format(
                        ": " + detail if detail else ""))
            rate = decoder.rate()
            channels = decoder.channels()
            if rate != 24000 or channels != 1:
                raise TtsError(
                    "Edge: неожиданный PCM {} Гц, {} канал(ов)".format(
                        rate, channels))
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("Edge: {}".format(exc))
        finally:
            try:
                transport.close()
            except Exception:
                pass
            try:
                decoder.close()
            except Exception:
                pass

    def close(self):
        Engine.close(self)
        self.voice = None
