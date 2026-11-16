"""UDP-клиент micro_ui для агента.

Не знает про `micro_hal`: только собирает команды и отправляет их
процессу `micro_ui`. Ошибки отправки не поднимаются в цикл агента.
"""

import socket

from micro_agent.errors import AgentError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
DEFAULT_SYNC_MS = 10000
DEFAULT_DATE_MS = 20000
DEFAULT_VOLUME_MS = 5000
DEFAULT_DISPLAY_BRIGHTNESS = 80
DEFAULT_RING_BRIGHTNESS = 30
DEFAULT_GLOBAL_BRIGHTNESS = 100

MODES = (
    "base", "bt_mode", "netlost", "apmode", "muted",
    "wake", "asr", "think", "speak", "error",
)


def _int(value, name, low, high=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentError("{} должен быть целым числом".format(name))
    if value < low or (high is not None and value > high):
        raise AgentError("{} вне допустимого диапазона".format(name))
    return value


def _sockaddr(host, port):
    """Адрес для MicroPython: `getaddrinfo` даёт рабочий sockaddr."""
    try:
        infos = socket.getaddrinfo(
            host, port, socket.AF_INET, socket.SOCK_DGRAM)
        return infos[0][-1]
    except Exception:
        return (host, port)


class UiClient:
    """Клиент команд micro_ui; не блокирует цикл агента."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 sync_ms=DEFAULT_SYNC_MS, date_ms=DEFAULT_DATE_MS,
                 volume_ms=DEFAULT_VOLUME_MS,
                 display_brightness=DEFAULT_DISPLAY_BRIGHTNESS,
                 ring_brightness=DEFAULT_RING_BRIGHTNESS,
                 global_brightness=DEFAULT_GLOBAL_BRIGHTNESS,
                 auto_brightness=False, sock=None, address=None):
        self.host = str(host)
        if not self.host:
            raise AgentError("пустой host UI")
        self.port = _int(port, "port", 1, 65535)
        self.sync_ms = _int(sync_ms, "sync_ms", 1, None)
        self.date_ms = _int(date_ms, "date_ms", 1, None)
        self.volume_ms = _int(volume_ms, "volume_ms", 1, None)
        self.display_brightness = _int(
            display_brightness, "display_brightness", 0, 100)
        self.ring_brightness = _int(
            ring_brightness, "ring_brightness", 0, 100)
        self.global_brightness = _int(
            global_brightness, "global_brightness", 0, 100)
        if not isinstance(auto_brightness, bool):
            raise AgentError("auto_brightness должен быть True или False")
        self.auto_brightness = auto_brightness
        self._sock = sock
        self._address = address
        self._opened = False
        self._mode = "base"
        self._last_sync = 0
        self.sent = 0
        self.errors = 0
        self.last_error = None
        self.available = sock is not None

    def _require(self):
        if not self._opened:
            raise AgentError("UI-клиент не открыт")

    def open(self):
        if self._opened:
            return self
        if self._sock is None:
            try:
                self._sock = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM)
                self._sock.setblocking(False)
                self._address = _sockaddr(self.host, self.port)
                self.available = True
            except Exception as exc:
                self._sock = None
                self._address = None
                self.available = False
                self.last_error = "socket: {}".format(exc)
        elif self._address is None:
            self._address = _sockaddr(self.host, self.port)
        self._opened = True
        self._mode = "base"
        self._last_sync = 0
        self._send("sync base")
        self._send("bright {} {}".format(
            self.display_brightness, self.ring_brightness))
        self._send("global {}".format(self.global_brightness))
        self._send("auto {}".format(
            "on" if self.auto_brightness else "off"))
        return self

    def _send(self, text):
        if not self._opened or self._sock is None or self._address is None:
            return False
        try:
            self._sock.sendto(text.encode("utf-8"), self._address)
        except Exception as exc:
            self.errors += 1
            self.last_error = "send: {}".format(exc)
            return False
        self.sent += 1
        return True

    def show(self, mode):
        self._require()
        if mode not in MODES:
            raise AgentError("неизвестный режим UI: {}".format(mode))
        self._mode = mode
        self._send("mode {}".format(mode))
        return mode

    def show_date(self, now_ms=0):
        self._require()
        self._send("overlay date {}".format(self.date_ms))

    def show_volume(self, percent):
        self._require()
        percent = _int(percent, "percent", 0, 100)
        self._send("overlay volume {} {}".format(
            percent, self.volume_ms))

    def show_face(self, name, ttl_ms=5000):
        self._require()
        if not isinstance(name, str) or not name:
            raise AgentError("пустое имя смайла")
        ttl_ms = _int(ttl_ms, "ttl_ms", 1, None)
        self._send("face {} {}".format(name.lower(), ttl_ms))

    def set_auto(self, enabled):
        self._require()
        if not isinstance(enabled, bool):
            raise AgentError("auto должен быть True или False")
        self.auto_brightness = enabled
        self._send("auto {}".format("on" if enabled else "off"))
        return enabled

    def poll(self, now_ms):
        self._require()
        now_ms = _int(now_ms, "now_ms", 0, None)
        if now_ms - self._last_sync >= self.sync_ms:
            self._send("sync {}".format(self._mode))
            self._send("bright {} {}".format(
                self.display_brightness, self.ring_brightness))
            self._send("global {}".format(self.global_brightness))
            self._send("auto {}".format(
                "on" if self.auto_brightness else "off"))
            self._last_sync = now_ms
        return []

    def close(self):
        if not self._opened:
            return True
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._address = None
        self._opened = False
        self.available = False
        return True

    def info(self):
        return {
            "host": self.host,
            "port": self.port,
            "opened": self._opened,
            "available": self.available,
            "mode": self._mode,
            "display_brightness": self.display_brightness,
            "ring_brightness": self.ring_brightness,
            "global_brightness": self.global_brightness,
            "auto_brightness": self.auto_brightness,
            "sent": self.sent,
            "errors": self.errors,
            "last_error": self.last_error,
            "last_sync": self._last_sync,
        }
