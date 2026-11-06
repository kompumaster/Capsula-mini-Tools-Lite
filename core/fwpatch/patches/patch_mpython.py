"""Micropython: бинарник и профиль окружения в overlay раздела data.

После overlay-монтирования `/data/overlay/upper` файлы видны как
`/usr/bin/micropython` и `/etc/profile.d/10-micropython.sh`.
`system_b` не меняется.
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
ORDER = 17

ASSET = "micropython/micropython"
PATH = "overlay/upper/usr/bin/micropython"
NAME = "micropython"

ENV_ASSET = "micropython_env.sh"
ENV_PATH = "overlay/upper/etc/profile.d/10-micropython.sh"
ENV_NAME = "micropython-profile"

FILES = (
    (PATH, ASSET, 0o755, NAME),
    (ENV_PATH, ENV_ASSET, 0o644, ENV_NAME),
)


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, mode, _name in FILES:
        put_asset(tree, path, asset, mode, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, _mode, _name in FILES:
        drop_asset(tree, path, asset, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — бинарник и профиль наши, `off` — нет или чужие."""
    hashes = {}
    state = "on"
    for path, asset, _mode, name in FILES:
        digest = present_sha(tree, path)
        if digest is None:
            state = "off"
            continue
        hashes[name] = digest
        if digest != asset_sha(asset):
            state = "off"
    return state, hashes
