"""Micro TTS: весь пакет в `/home/microp/micro_tts`.

Целевой путь в `data` — `permanent/home/microp/micro_tts`, после
симлинка `/home` это `/home/microp/micro_tts`. Каталог копируется
целиком: пакет и `bins/edge_token`, `bins/libc_edge.so`,
`bins/libc_mp3.so`.

`micro_tts` импортируется из `/home/microp`, а `bins/edge_token`
запускается оттуда же; `bins` сохраняется.
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_files, asset_sha, drop_asset_dir,
                     present_sha, put_asset_dir)

KEY = "mtts"
TITLE = "Micro TTS"
SUMMARY = "Синтез речи для колонки"
PART = "data"
KIND = "toggle"
FLAG = "mtts"
ORDER = 19

ASSET_DIR = "micro_p_libs/micro_tts"
TARGET = "permanent/home/microp/micro_tts"


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    put_asset_dir(tree, TARGET, ASSET_DIR, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    drop_asset_dir(tree, TARGET, ASSET_DIR, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — все файлы на месте и совпадают, иначе `off`.

    Ключи хешей — пути в комплекте (`tts.py`, `bins/edge_token`).
    """
    hashes = {}
    state = "on"
    for rel, asset, _mode in asset_files(ASSET_DIR):
        digest = present_sha(tree, "{}/{}".format(TARGET, rel))
        if digest is None:
            state = "off"
            continue
        hashes[rel] = digest
        if digest != asset_sha(asset):
            state = "off"
    return state, hashes
