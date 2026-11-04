"""SSH: `dropbearmulti` и `S90dropbear` в разделе system_b.

Один бинарник `dropbearmulti` содержит `dropbear`, `dropbearkey`,
`scp` и `dbclient`; на плате они доступны как симлинки на него.

Ассет init-скрипта — `S90dropbear.sh` (для единообразия с
`S05home.sh` и `S91adbd.sh`); на плате он ставится как
`etc/init.d/S90dropbear`.
"""

from __future__ import annotations

from fwpatch.errors import PatchError
from fwpatch.tar_tree import TarTree

from .common import Ask, asset_sha, drop_asset, present_sha, put_asset

KEY = "ssh"
TITLE = "SSH(:22)"
SUMMARY = "SSH, порт 22, capsula/mini"
PART = "system_b"
KIND = "toggle"
FLAG = "ssh"
ORDER = 12

MULTI = "dropbearmulti"
TARGET = "usr/bin/dropbearmulti"
INIT_PATH = "etc/init.d/S90dropbear"
INIT_ASSET = "S90dropbear.sh"

FILES = (
    (TARGET, MULTI, 0o755),
    (INIT_PATH, INIT_ASSET, 0o755),
)

# Имена файлов в status.txt.
LOGICAL = {
    TARGET: "dropbearmulti",
    INIT_PATH: "S90dropbear",
}

# Имя на плате -> куда указывает симлинк.
LINKS = (
    ("usr/bin/dropbear", MULTI),
    ("usr/bin/dropbearkey", MULTI),
    ("usr/bin/scp", MULTI),
    ("usr/bin/dbclient", MULTI),
)


def _drop_path(tree: TarTree, path: str, ask: Ask | None) -> None:
    """Убрать файл или симлинк; обычный файл — с подтверждением."""
    if not tree.exists(path):
        return
    if tree.kind(path) == "link":
        tree.remove(path)
        return
    if ask is None or not ask(
            f"{path}: это файл, а не симлинк; заменить?", True):
        raise PatchError(f"{path}: отменено")
    tree.remove(path)


def _put_link(tree: TarTree, path: str, target: str,
              ask: Ask | None) -> None:
    if tree.kind(path) == "link" and tree.link_target(path) == target:
        return
    _drop_path(tree, path, ask)
    tree.symlink(path, target)


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, mode in FILES:
        put_asset(tree, path, asset, mode, ask)
    for path, target in LINKS:
        _put_link(tree, path, target, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    for path, _target in LINKS:
        _drop_path(tree, path, ask)
    for path, asset, _mode in FILES:
        drop_asset(tree, path, asset, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — multi, init и все симлинки на месте и совпадают."""
    hashes = {}
    state = "on"
    for path, asset, _mode in FILES:
        digest = present_sha(tree, path)
        if digest is None:
            state = "off"
            continue
        hashes[LOGICAL[path]] = digest
        if digest != asset_sha(asset):
            state = "off"
    for path, target in LINKS:
        if (tree.kind(path) != "link"
                or tree.link_target(path) != target):
            state = "off"
    return state, hashes
