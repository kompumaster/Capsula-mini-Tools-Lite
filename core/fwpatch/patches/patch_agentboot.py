"""Автозапуск своего агента: init-скрипты в `system_b`.

Скрипты кладутся в нижний `etc/init.d` раздела `system_b`, который на
плате виден как `/rom/etc/init.d`: `rcS` строит список `S??*` до
монтирования overlay, поэтому скрипты в overlay не стартуют.

`S98micro_ui.sh` поднимает дисплей и кольцо, `S99micro_agent.sh` —
агента. Оба скрипта наши, поэтому обновление перезаписывает их (с
подтверждением, если файл чужой).

Нужны `mpython`, `mplibs` и `home`: без них агент не запустится, и
скрипты останутся бесполезными.
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_sha, drop_asset, present_sha, put_asset)

KEY = "agentboot"
TITLE = "Старт MP агента"
SUMMARY = "Автозапуск своего агента"
PART = "system_b"
KIND = "toggle"
FLAG = "agentboot"
ORDER = 20

UI_PATH = "etc/init.d/S98micro_ui.sh"
UI_ASSET = "S98micro_ui.sh"
AGENT_PATH = "etc/init.d/S99micro_agent.sh"
AGENT_ASSET = "S99micro_agent.sh"

FILES = (
    (UI_PATH, UI_ASSET, 0o755),
    (AGENT_PATH, AGENT_ASSET, 0o755),
)

# Имена файлов в status.txt.
LOGICAL = {
    UI_PATH: "S98micro_ui",
    AGENT_PATH: "S99micro_agent",
}

def apply(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, mode in FILES:
        put_asset(tree, path, asset, mode, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, _mode in FILES:
        drop_asset(tree, path, asset, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
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
    return state, hashes
