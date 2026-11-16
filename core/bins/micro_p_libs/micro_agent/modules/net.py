"""Сеть: watchdog и переход в точку доступа.

Проверка связи идёт по таймеру `poll(now_ms)`. Потеря — событие
`network_lost`; дольше `ap_after_ms` — `ap_mode` и портал AP. После
восстановления — `network_ok`/`ap_stop`.
"""

from micro_agent.core import events as ev
from micro_agent.errors import AgentError
from micro_agent.modules.ap import ApPortal

DEFAULT_INTERVAL_MS = 30000
DEFAULT_AP_AFTER_MS = 180000


def _int(value, name, low):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentError("{} должен быть целым числом".format(name))
    if value < low:
        raise AgentError("{} должен быть не меньше {}".format(name, low))
    return value


class Network:
    """Слежение за Wi-Fi и точка доступа."""

    def __init__(self, wifi=None, portal=None,
                 interval_ms=DEFAULT_INTERVAL_MS,
                 ap_after_ms=DEFAULT_AP_AFTER_MS):
        self._wifi = wifi
        self._portal = portal
        self.interval_ms = _int(interval_ms, "interval_ms", 1)
        self.ap_after_ms = _int(ap_after_ms, "ap_after_ms", 0)
        self._opened = False
        self._next_ms = 0
        self._connected = None
        self._lost_since = None
        self._ap = False
        self._error = None

    def open(self):
        if self._opened:
            return self
        if self._wifi is None:
            try:
                from micro_hal import lib_wifi
                self._wifi = lib_wifi
            except Exception as exc:
                raise AgentError("Wi-Fi недоступен: {}".format(exc))
        if self._portal is None:
            self._portal = ApPortal()
        self._opened = True
        return self

    def _require(self):
        if not self._opened:
            raise AgentError("сеть не открыта")

    def _check(self):
        try:
            status = self._wifi.status()
            connected = bool(status.get("ip"))
        except Exception:
            status = {}
            connected = False
        return status, connected

    def poll(self, now_ms):
        self._require()
        now_ms = _int(now_ms, "now_ms", 0)
        if now_ms < self._next_ms:
            return []
        self._next_ms = now_ms + self.interval_ms
        status, connected = self._check()
        events = []

        if self._connected is None:
            self._connected = connected
            if not connected:
                self._lost_since = now_ms
                events.append(ev.Event(ev.NETWORK_LOST))
            return events

        if connected and not self._connected:
            self._connected = True
            self._lost_since = None
            if self._ap:
                try:
                    self._portal.stop()
                except Exception as exc:
                    self._error = str(exc)
                self._ap = False
                events.append(ev.Event(ev.AP_STOP))
            else:
                events.append(ev.Event(ev.NETWORK_OK))
            return events

        if not connected and self._connected:
            self._connected = False
            self._lost_since = now_ms
            events.append(ev.Event(ev.NETWORK_LOST))
            return events

        if (not connected and not self._ap
                and self._lost_since is not None
                and now_ms - self._lost_since >= self.ap_after_ms):
            try:
                self._portal.start()
                self._ap = True
                events.append(ev.Event(ev.AP_MODE))
            except Exception as exc:
                self._error = str(exc)
        return events

    def start_ap(self):
        self._require()
        if not self._ap:
            try:
                self._portal.start()
            except Exception as exc:
                raise AgentError("AP: {}".format(exc))
            self._ap = True
        return True

    def stop_ap(self):
        if self._ap:
            try:
                self._portal.stop()
            finally:
                self._ap = False
        return True

    def close(self):
        if self._opened:
            self.stop_ap()
            self._opened = False
        return True

    def status(self):
        result = {
            "connected": self._connected,
            "ap": self._ap,
            "lost_since": self._lost_since,
            "error": self._error,
            "interval_ms": self.interval_ms,
            "ap_after_ms": self.ap_after_ms,
        }
        if self._opened:
            try:
                result["wifi"] = self._wifi.status()
            except Exception:
                result["wifi"] = None
        return result
