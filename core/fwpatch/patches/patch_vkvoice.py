"""VK-Voice: отключить автозапуск, не удаляя файлы.

`S97voice-agent.sh` переименовывается в `x_S97voice-agent.sh.bak`:
`rcS` ищет только `S??*`, поэтому переименованный файл не запускается.
Сам `voice-agent` и обёртка `voice-agent.sh` остаются на месте.
"""

from __future__ import annotations

from fwpatch.errors import PatchError
from fwpatch.tar_tree import TarTree

from .common import Ask, present_sha

KEY = "vkvoice"
TITLE = "Откл. VK-Voice"
SUMMARY = "отключить автозапуск VK-Voice"
PART = "system_b"
KIND = "toggle"
FLAG = "vkvoice"
ORDER = 35

PATH = "etc/init.d/S97voice-agent.sh"
BACKUP = "etc/init.d/x_S97voice-agent.sh.bak"
ORIGINAL_NAME = "S97voice-agent.sh"
BACKUP_NAME = "x_S97voice-agent.sh.bak"


def _file(tree: TarTree, path: str) -> bytes:
    kind = tree.kind(path)
    if kind not in ("file", "hardlink"):
        raise PatchError(f"{path}: это {kind}, а не файл")
    return tree.read(path)


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    """Убрать автозапуск: S97 → x_S97...bak."""
    if not tree.exists(PATH):
        return
    data = _file(tree, PATH)
    mode = tree.mode(PATH) or 0o755
    tree.remove(PATH)
    if not tree.exists(BACKUP):
        tree.add(BACKUP, data, mode)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    """Вернуть автозапуск: x_S97...bak → S97."""
    if not tree.exists(BACKUP):
        return
    data = _file(tree, BACKUP)
    mode = tree.mode(BACKUP) or 0o755
    tree.remove(BACKUP)
    if not tree.exists(PATH):
        tree.add(PATH, data, mode)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — S97 убран, `off` — S97 на месте."""
    original = present_sha(tree, PATH)
    backup = present_sha(tree, BACKUP)
    if backup is not None and original is None:
        return "on", {BACKUP_NAME: backup}
    if original is not None:
        return "off", {ORIGINAL_NAME: original}
    return "off", {}
