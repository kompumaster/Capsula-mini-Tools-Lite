"""ADB: `adbd-tcp` и `S91adbd.sh` в разделе system_b."""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_sha, drop_asset, present_sha,
                     put_asset)

KEY = "adb"
TITLE = "ADB(:5555)"
SUMMARY = "ADB :5555 без ключа"
PART = "system_b"
KIND = "toggle"
FLAG = "adb"
ORDER = 20

FILES = (
    ("usr/bin/adbd-tcp", "adbd", 0o755),
    ("etc/init.d/S91adbd.sh", "S91adbd.sh", 0o755),
)

# Имена файлов в status.txt.
LOGICAL = {
    "usr/bin/adbd-tcp": "adbd-tcp",
    "etc/init.d/S91adbd.sh": "S91adbd.sh",
}


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, mode in FILES:
        put_asset(tree, path, asset, mode, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, _mode in FILES:
        drop_asset(tree, path, asset, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """ADB включён, если на месте оба наших файла; отдаёт их хеши."""
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
