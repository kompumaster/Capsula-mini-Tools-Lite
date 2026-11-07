"""MicroPython libs: весь `micro_p_libs` в `/home/microp`.

Целевой путь в `data` — `permanent/home/microp`, после симлинка `/home`
это `/home/microp`. Содержимое комплекта раскладывается как есть:
`micro_hal/`, `micro_tts/`, `micro_asr/`, `micro_server/` и общий
`README.md`; служебный `SHA256SUMS` не копируется.

У каждого пакета свои `bins/`; `micro_hal` ищет библиотеки по путям
`/home/microp/micro_hal/bins/libc_*.so`, `micro_tts` — по
`/home/microp/micro_tts/bins/...`.
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_files, asset_sha, drop_asset,
                     present_sha, put_asset)

KEY = "mplibs"
TITLE = "MP Libs"
SUMMARY = "Библиотеки Micropython для работы с колонкой"
PART = "data"
KIND = "toggle"
FLAG = "mplibs"
ORDER = 18

ASSET_DIR = "micro_p_libs"
TARGET = "permanent/home/microp"


def _files() -> tuple[tuple[str, str, int], ...]:
    """`(относительный путь, ассет, mode)` без служебного SHA256SUMS."""
    return tuple(item for item in asset_files(ASSET_DIR)
                 if item[0] != "SHA256SUMS")


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    for rel, asset, mode in _files():
        put_asset(tree, "{}/{}".format(TARGET, rel), asset, mode, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    for rel, asset, _mode in _files():
        drop_asset(tree, "{}/{}".format(TARGET, rel), asset, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — все файлы комплекта на месте и совпадают, иначе `off`.

    Ключи хешей — пути в комплекте (`micro_hal/...`, `micro_tts/...`,
    `micro_asr/...`, `micro_server/...`).
    """
    hashes = {}
    state = "on"
    for rel, asset, _mode in _files():
        digest = present_sha(tree, "{}/{}".format(TARGET, rel))
        if digest is None:
            state = "off"
            continue
        hashes[rel] = digest
        if digest != asset_sha(asset):
            state = "off"
    return state, hashes
