"""VK-Voice: заменить voice-agent заглушкой `noop`.

Необратимый kill-патч: оригинал в образе заменяется, откат — только
перезаписью раздела из бэкапа. Watchdog после этого не запускается,
потому что `voice-agent` не открывает `/dev/watchdog`.
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import kill_stub, present_sha, stub_hashes

KEY = "vkkill"
TITLE = "Удалить VK-Voice"
SUMMARY = "заменить VK-Voice пустышкой, необратимо"
PART = "system_b"
KIND = "kill"
FLAG = "vk"
ORDER = 70
NAME = "voice-agent"
PATH = f"usr/bin/{NAME}"
STUB = "noop"


def kill(tree: TarTree) -> None:
    kill_stub(tree, PATH, STUB)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — оригинал, `off` — заглушка или файла нет."""
    digest = present_sha(tree, PATH)
    if digest is None:
        return "off", {}
    state = "off" if digest in stub_hashes() else "on"
    return state, {NAME: digest}
