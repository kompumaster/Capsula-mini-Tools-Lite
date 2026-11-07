"""GET /api/status."""

import json

from micro_server import info, utils


def status(server, store, collector, request):
    """Статус сервера, колонки и текущие настройки."""
    data = collector(server)
    data["ok"] = True
    if store is not None:
        data["settings"] = store.all()
    utils.send_response(
        server, json.dumps(data), 200,
        "application/json; charset=utf-8", ["Cache-Control: no-store"])


def register(server, store=None, collector=None):
    collector = collector or info.collect
    server.add_route(
        "/api/status",
        lambda request: status(server, store, collector, request))
    return server
