"""GET /api/ping."""

import json

from micro_server import utils


def ping(server, request):
    import micro_server
    body = json.dumps({"ok": True, "version": micro_server.__version__})
    utils.send_response(
        server, body, 200, "application/json; charset=utf-8",
        ["Cache-Control: no-store"])


def register(server):
    server.add_route("/api/ping", lambda request: ping(server, request))
    return server
