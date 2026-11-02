"""Selfcheck: отключить автозапуск S98, не удаляя файлы.

`S98selfcheck.sh` переименовывается в `x_S98selfcheck.sh.bak`:
`rcS` ищет только `S??*`, поэтому переименованный файл не запускается.
Сам `self-check.sh` остаётся на месте.
"""

from __future__ import annotations

from fwpatch.errors import PatchError
from fwpatch.tar_tree import TarTree

from .common import Ask, present_sha

KEY = "slfchk"
TITLE = "Откл. Selfcheck"
SUMMARY = "отключить S98 self-check"
PART = "system_b"
KIND = "toggle"
FLAG = "slfchk"
ORDER = 36

PATH = "etc/init.d/S98selfcheck.sh"
BACKUP = "etc/init.d/x_S98selfcheck.sh.bak"
ORIGINAL_NAME = "S98selfcheck.sh"
BACKUP_NAME = "x_S98selfcheck.sh.bak"


def _file(tree: TarTree, path: str) -> bytes:
    kind = tree.kind(path)
    if kind not in ("file", "hardlink"):
        raise PatchError(f"{path}: это {kind}, а не файл")
    return tree.read(path)


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    """Убрать автозапуск: S98 → x_S98...bak."""
    if not tree.exists(PATH):
        return
    data = _file(tree, PATH)
    mode = tree.mode(PATH) or 0o755
    tree.remove(PATH)
    if not tree.exists(BACKUP):
        tree.add(BACKUP, data, mode)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    """Вернуть автозапуск: x_S98...bak → S98."""
    if not tree.exists(BACKUP):
        return
    data = _file(tree, BACKUP)
    mode = tree.mode(BACKUP) or 0o755
    tree.remove(BACKUP)
    if not tree.exists(PATH):
        tree.add(PATH, data, mode)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — S98 убран, `off` — S98 на месте."""
    original = present_sha(tree, PATH)
    backup = present_sha(tree, BACKUP)
    if backup is not None and original is None:
        return "on", {BACKUP_NAME: backup}
    if original is not None:
        return "off", {ORIGINAL_NAME: original}
    return "off", {}
