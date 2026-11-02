"""swupdate: заменить на `noop`."""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import kill_stub, present_sha, stub_hashes

KEY = "swu"
TITLE = "Обновление SW"
PART = "system_b"
KIND = "kill"
FLAG = "swupdate"
ORDER = 60
NAME = "swupdate"
PATH = f"usr/bin/{NAME}"
STUB = "noop"


def kill(tree: TarTree) -> None:
    kill_stub(tree, PATH, STUB)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — оригинал, `off` — файла нет или стоит заглушка."""
    digest = present_sha(tree, PATH)
    if digest is None:
        return "off", {}
    state = "off" if digest in stub_hashes() else "on"
    return state, {NAME: digest}
