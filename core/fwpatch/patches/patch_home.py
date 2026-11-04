"""Home: восстановить `/home -> /data/permanent/home` при загрузке.

Скрипт `S05home.sh` кладётся в `system_b`; он выполняется после
монтирования `/data` и overlay и переживает очистку overlay.
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_sha, drop_asset, present_sha,
                     put_asset)

KEY = "home"
TITLE = "Подключить /home"
SUMMARY = "подключить /data/permanent/home как /home"
PART = "system_b"
KIND = "toggle"
FLAG = "home"
ORDER = 16

ASSET = "S05home.sh"
PATH = "etc/init.d/S05home.sh"
LOGICAL = "S05home.sh"


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    put_asset(tree, PATH, ASSET, 0o755, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    drop_asset(tree, PATH, ASSET, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — наш скрипт на месте, `off` — нет или чужой."""
    digest = present_sha(tree, PATH)
    if digest is None:
        return "off", {}
    state = "on" if digest == asset_sha(ASSET) else "off"
    return state, {LOGICAL: digest}
