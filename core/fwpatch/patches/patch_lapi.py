"""LAPI: файл `permanent/lapi` = `on` в разделе data."""

from __future__ import annotations

from fwpatch.errors import PatchError
from fwpatch.tar_tree import TarTree

from .common import Ask, drop, present_sha, put

KEY = "lapi"
TITLE = "LAPI(:80)"
SUMMARY = "локальный API, порт 80"
PART = "data"
KIND = "toggle"
FLAG = "lapi"
ORDER = 10
PATH = "permanent/lapi"


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    if tree.kind(PATH) == "file" and tree.read(PATH).strip() == b"on":
        return
    if tree.exists(PATH) and tree.kind(PATH) != "file":
        raise PatchError(f"{PATH}: это не файл")
    put(tree, PATH, b"on", 0o644, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    if not tree.exists(PATH):
        return
    if tree.kind(PATH) == "file" and tree.read(PATH).strip() == b"on":
        tree.remove(PATH)
        return
    drop(tree, PATH, b"on", ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """Состояние LAPI и хеш файла, если он есть."""
    digest = present_sha(tree, PATH)
    if digest is None:
        return "off", {}
    state = "on" if tree.read(PATH).strip() == b"on" else "off"
    return state, {PATH: digest}
