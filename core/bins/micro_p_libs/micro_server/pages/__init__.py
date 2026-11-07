"""Страницы micro_server: статические HTML/CSS/JS из `web/`."""

from micro_server import info
from micro_server.api import ping as ping_api
from micro_server.api import status as status_api
from micro_server.pages import static


def register(server, store=None, collector=None):
    """Подключить страницы и API к серверу."""
    collector = collector or info.collect
    static.register(server)
    ping_api.register(server)
    status_api.register(server, store, collector)
    return server
