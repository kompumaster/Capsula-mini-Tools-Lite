"""Hostapd: положить бинарник в overlay раздела data.

После overlay-монтирования `/data/overlay/upper` файл виден как
`/usr/bin/hostapd`. `system_b` не меняется.
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_sha, drop_asset, present_sha,
                     put_asset)

KEY = "hostapd"
TITLE = "Hostapd"
SUMMARY = "hostapd 2.9 для точки доступа"
PART = "data"
KIND = "toggle"
FLAG = "hostapd"
ORDER = 19

ASSET = "net/hostapd"
PATH = "overlay/upper/usr/bin/hostapd"
NAME = "hostapd"


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
