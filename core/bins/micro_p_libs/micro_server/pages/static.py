"""Отдача статических файлов из `web/` (читаются один раз)."""

from micro_server import utils
from micro_server.errors import ServerError

# маршрут, файл, content-type, cache-control
ROUTES = (
    ("/", "index.html", "text/html; charset=utf-8", "no-store"),
    ("/index.html", "index.html", "text/html; charset=utf-8", "no-store"),
    ("/test", "test.html", "text/html; charset=utf-8", "no-store"),
    ("/css/style.css", "css/style.css", "text/css; charset=utf-8",
     "public, max-age=3600"),
    ("/js/app.js", "js/app.js", "application/javascript; charset=utf-8",
     "public, max-age=3600"),
    ("/js/test.js", "js/test.js", "application/javascript; charset=utf-8",
     "public, max-age=3600"),
)


def _web_dir():
    """Путь к `web/` от расположения пакета (без os.path)."""
    here = __file__
    index = max(here.rfind("/"), here.rfind("\\"))
    pages_dir = here[:index] if index >= 0 else "."
    index = max(pages_dir.rfind("/"), pages_dir.rfind("\\"))
    root = pages_dir[:index] if index >= 0 else "."
    return root + "/web"


def _read(path):
    try:
        handle = open(path, "rb")
    except OSError as exc:
        raise ServerError("не прочитать {}: {}".format(path, exc))
    try:
        return handle.read()
    finally:
        handle.close()


def _handler(server, data, content_type, cache):
    def handler(request):
        utils.send_response(
            server, data, 200, content_type,
            ["Cache-Control: {}".format(cache)])
    return handler


def register(server):
    """Загрузить файлы и подключить маршруты."""
    folder = _web_dir()
    for route, name, content_type, cache in ROUTES:
        data = _read(folder + "/" + name)
        server.add_route(route, _handler(server, data, content_type, cache))
    return server
