"""Micropython: положить бинарник в overlay раздела data.

После overlay-монтирования `/data/overlay/upper` файл виден как
`/usr/bin/micropython`. `system_b` не меняется.
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_sha, drop_asset, present_sha,
                     put_asset)

KEY = "mpython"
TITLE = "Micropython"
SUMMARY = "MicroPython в overlay data"
PART = "data"
KIND = "toggle"
FLAG = "mpython"
ORDER = 15

ASSET = "micropython/micropython"
PATH = "overlay/upper/usr/bin/micropython"
NAME = "micropython"


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    put_asset(tree, PATH, ASSET, 0o755, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    drop_asset(tree, PATH, ASSET, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — наш бинарник, `off` — нет или чужой."""
    digest = present_sha(tree, PATH)
    if digest is None:
        return "off", {}
    state = "on" if digest == asset_sha(ASSET) else "off"
    return state, {NAME: digest}
