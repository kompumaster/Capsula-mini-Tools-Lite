"""SSH: dropbear, dropbearkey и `S90dropbear` в разделе system_b."""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_sha, drop_asset, present_sha,
                     put_asset)

KEY = "ssh"
TITLE = "SSH(:22)"
SUMMARY = "SSH, порт 22, capsula/mini"
PART = "system_b"
KIND = "toggle"
FLAG = "ssh"
ORDER = 30

FILES = (
    ("usr/bin/dropbear", "dropbear", 0o755),
    ("usr/bin/dropbearkey", "dropbearkey", 0o755),
    ("etc/init.d/S90dropbear", "S90dropbear", 0o755),
)

# Имена файлов в status.txt.
LOGICAL = {
    "usr/bin/dropbear": "dropbear",
    "usr/bin/dropbearkey": "dropbearkey",
    "etc/init.d/S90dropbear": "S90dropbear",
}


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, mode in FILES:
        put_asset(tree, path, asset, mode, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, _mode in FILES:
        drop_asset(tree, path, asset, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """SSH включён, если на месте все наши файлы; отдаёт их хеши."""
    hashes = {}
    for path, _asset, _mode in FILES:
        digest = present_sha(tree, path)
        if digest is not None:
            hashes[LOGICAL[path]] = digest
    state = "on"
    for path, asset, _mode in FILES:
        if tree.kind(path) != "file" or tree.sha256(path) != asset_sha(asset):
            state = "off"
            break
    return state, hashes
