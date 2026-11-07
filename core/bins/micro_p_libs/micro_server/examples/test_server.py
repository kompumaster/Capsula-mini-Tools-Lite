#!/usr/bin/env python3
"""Тестовый сервер micro_server.

Запуск на колонке:
`micropython /home/microp/micro_server/examples/test_server.py`
"""

import sys

HERE = __file__
if "/" in HERE:
    ROOT = HERE.rsplit("/", 3)[0]
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

from micro_server import MicroServer, Store  # noqa: E402
from micro_server.pages import register  # noqa: E402

PORT = 8080

store = Store()
server = MicroServer(port=store.get("port", PORT))
register(server, store)
print("micro_server на порту", PORT)
server.serve_forever()
