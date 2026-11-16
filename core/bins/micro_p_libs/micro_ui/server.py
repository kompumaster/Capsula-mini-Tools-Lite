"""UDP-сервер команд micro_ui на loopback."""

import socket

try:
    import uselect as _select
except ImportError:
    import select as _select

from micro_ui.errors import UiError
from micro_ui.protocol import MAX_BYTES, parse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766


def _sockaddr(host, port):
    """Адрес для bind/sendto.

    В этой сборке MicroPython `bind(("127.0.0.1", port))` не работает,
    а sockaddr из `getaddrinfo` - работает.
    """
    try:
        infos = socket.getaddrinfo(
            host, port, socket.AF_INET, socket.SOCK_DGRAM)
        return infos[0][-1]
    except Exception:
        return (host, port)


class UiServer:
    """Приём команд, применение к `UiCore`, необязательный `status`."""

    def __init__(self, core, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 max_bytes=MAX_BYTES, log=None):
        self.core = core
        self.host = str(host)
        self.port = int(port)
        if not self.host:
            raise UiError("пустой host")
        if self.port < 0 or self.port > 65535:
            raise UiError("порт вне 0…65535")
        self.max_bytes = int(max_bytes)
        if self.max_bytes < 1:
            raise UiError("max_bytes должен быть положительным")
        self.log = log
        self._sock = None
        self._poller = None
        self._opened = False
        self.address = None
        self.received = 0
        self.applied = 0
        self.errors = 0
        self.send_errors = 0
        self.last_error = None

    def _require(self):
        if not self._opened:
            raise UiError("UDP-сервер не открыт")

    def open(self):
        if self._opened:
            return self
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            option = getattr(socket, "SO_REUSEADDR", None)
            if option is not None:
                try:
                    sock.setsockopt(socket.SOL_SOCKET, option, 1)
                except Exception:
                    pass
            sock.bind(_sockaddr(self.host, self.port))
            sock.setblocking(False)
            poller = _select.poll()
            poller.register(sock, _select.POLLIN)
        except Exception:
            try:
                sock.close()
            except Exception:
                pass
            raise
        self._sock = sock
        self._poller = poller
        self._opened = True
        getter = getattr(sock, "getsockname", None)
        if callable(getter):
            try:
                self.address = getter()
            except Exception:
                self.address = None
        if self.address is None:
            self.address = (self.host, self.port)
        try:
            self.port = int(self.address[1])
        except Exception:
            pass
        return self

    def close(self):
        if not self._opened:
            return True
        if self._poller is not None:
            try:
                self._poller.unregister(self._sock)
            except Exception:
                pass
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._poller = None
        self._opened = False
        return True

    def _error(self, message):
        self.errors += 1
        self.last_error = message
        if callable(self.log):
            try:
                self.log("UI protocol: {}".format(message))
            except Exception:
                pass

    def _send(self, address, text):
        try:
            self._sock.sendto(text.encode("utf-8"), address)
            return True
        except Exception as exc:
            self.send_errors += 1
            self._error("send: {}".format(exc))
            return False

    def _status(self, address):
        info = self.core.info()
        text = ("status mode={} persistent={} overlay={} "
                "overlay_until={} mode_until={} "
                "bright={}/{}/{} effective={}/{} "
                "auto={} phase={} dither={} lux={}").format(
                    info["mode"], info["persistent"],
                    info["overlay"] or "none",
                    info["overlay_until"], info["mode_until"],
                    info["display_brightness"],
                    info["ring_brightness"],
                    info["global_brightness"],
                    info["display_effective"],
                    info["ring_effective"],
                    "on" if info["auto"] else "off",
                    info["phase"],
                    "on" if info["dither"] else "off",
                    info["auto_lux"])
        self._send(address, text)

    def _apply(self, command, now_ms, address):
        kind = command["type"]
        if kind == "status":
            self._status(address)
            return True
        if kind == "mode":
            self.core.set_mode(
                command["name"], lease_ms=command["lease_ms"],
                now_ms=now_ms)
            return True
        if kind == "sync":
            self.core.sync(
                command["name"], lease_ms=command["lease_ms"],
                now_ms=now_ms)
            return True
        if kind == "overlay":
            if command["name"] == "date":
                self.core.show_date(now_ms=now_ms,
                                    ttl_ms=command["ttl_ms"])
            else:
                self.core.show_volume(
                    command["value"], ttl_ms=command["ttl_ms"],
                    now_ms=now_ms)
            return True
        if kind == "face":
            self.core.show_face(
                command["name"], ttl_ms=command["ttl_ms"],
                now_ms=now_ms)
            return True
        if kind == "bright":
            self.core.set_brightness(
                display=command["display"], ring=command["ring"])
            return True
        if kind == "global":
            self.core.set_global(command["value"])
            return True
        if kind == "dither":
            self.core.set_dither(command["enabled"])
            return True
        if kind == "auto":
            self.core.set_auto(command["enabled"])
            return True
        raise UiError("неизвестный тип команды: {}".format(kind))

    def poll(self, now_ms):
        """Принять все доступные датаграммы; вернуть число команд."""
        self._require()
        count = 0
        while True:
            try:
                data, address = self._sock.recvfrom(self.max_bytes + 1)
            except OSError:
                break
            self.received += 1
            if len(data) > self.max_bytes:
                self._error("датаграмма длиннее {} байт".format(
                    self.max_bytes))
                continue
            text = ""
            try:
                text = data.decode("utf-8")
                command = parse(text)
                self._apply(command, now_ms, address)
            except UiError as exc:
                self._error("{}: {!r}".format(exc, text))
                continue
            except Exception as exc:
                self._error("{}: {!r}".format(exc, text))
                continue
            self.applied += 1
            count += 1
        return count

    def wait(self, timeout_ms=10):
        """Подождать активности сокета (для главного цикла)."""
        self._require()
        return self._poller.poll(timeout_ms)

    def info(self):
        return {
            "host": self.host,
            "port": self.port,
            "address": self.address,
            "opened": self._opened,
            "received": self.received,
            "applied": self.applied,
            "errors": self.errors,
            "send_errors": self.send_errors,
            "last_error": self.last_error,
        }
