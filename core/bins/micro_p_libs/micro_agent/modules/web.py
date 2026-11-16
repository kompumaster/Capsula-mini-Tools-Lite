"""Встроенный `micro_server`: статус агента по HTTP."""

import json

from micro_agent.errors import AgentError

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080


class Web:
    """HTTP-сервер в процессе агента; опрашивается через `poll()`."""

    def __init__(self, server=None, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 utils=None):
        self._server = server
        self.host = str(host)
        self.port = int(port)
        self._utils = utils
        self.snapshot = {}
        self._opened = False

    def open(self):
        if self._opened:
            return self
        if self._utils is None:
            try:
                from micro_server import utils
                self._utils = utils
            except Exception as exc:
                raise AgentError("micro_server недоступен: {}".format(exc))
        if self._server is None:
            try:
                from micro_server import MicroServer
                self._server = MicroServer(self.host, self.port)
            except Exception as exc:
                raise AgentError("micro_server: {}".format(exc))
        try:
            self._server.add_route("/api/status", self._status)
            self._server.start()
        except Exception as exc:
            raise AgentError("веб-сервер: {}".format(exc))
        self._opened = True
        return self

    def _status(self, request):
        body = json.dumps(self.snapshot)
        self._utils.send_response(
            self._server, body, 200,
            "application/json; charset=utf-8",
            ["Cache-Control: no-store"])

    def update(self, snapshot):
        self.snapshot = dict(snapshot or {})
        return self.snapshot

    def poll(self, now_ms):
        if not self._opened:
            raise AgentError("веб-сервер не открыт")
        self._server.poll(0)
        return []

    def close(self):
        if not self._opened:
            return True
        try:
            self._server.stop()
        finally:
            self._opened = False
        return True

    def status(self):
        return {
            "opened": self._opened,
            "host": self.host,
            "port": self.port,
            "keys": sorted(self.snapshot.keys()),
        }
