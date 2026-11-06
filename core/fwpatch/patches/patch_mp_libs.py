"""MicroPython libs: весь `micro_p_libs` в `/home/microp`.

Целевой путь в `data` — `permanent/home/microp`, после симлинка `/home`
это `/home/microp`. Содержимое комплекта раскладывается как есть:
`micro_hal/`, `micro_tts/`, `micro_asr/` и общий `README.md`.

У каждого пакета свои `bins/`; `micro_hal` ищет библиотеки по путям
`/home/microp/micro_hal/bins/libc_*.so`, `micro_tts` — по
`/home/microp/micro_tts/bins/...`.
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_files, asset_sha, drop_asset_dir,
                     present_sha, put_asset_dir)

KEY = "mplibs"
TITLE = "MP Libs"
SUMMARY = "Библиотеки Micropython для работы с колонкой"
PART = "data"
KIND = "toggle"
FLAG = "mplibs"
ORDER = 18

ASSET_DIR = "micro_p_libs"
TARGET = "permanent/home/microp"


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    put_asset_dir(tree, TARGET, ASSET_DIR, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    drop_asset_dir(tree, TARGET, ASSET_DIR, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — все файлы комплекта на месте и совпадают, иначе `off`.

    Ключи хешей — пути в комплекте (`micro_hal/...`, `micro_tts/...`,
    `micro_asr/...`).
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
