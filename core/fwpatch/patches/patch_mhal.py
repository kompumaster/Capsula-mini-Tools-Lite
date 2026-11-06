"""Micro HAL: весь пакет в `/home/microp/micro_hal`.

Целевой путь в `data` — `permanent/home/microp/micro_hal`, после
симлинка `/home` это `/home/microp/micro_hal`. Каталог копируется
целиком (без тестов), вместе с `bins/libc_*.so`: `hal_*` ищут библиотеки по путям
`/home/microp/micro_hal/bins/libc_*.so`.
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import (Ask, asset_files, asset_sha, drop_asset_dir,
                     present_sha, put_asset_dir)

KEY = "mhal"
TITLE = "Micro HAL"
SUMMARY = "Набор библиотек для работы с железом колонки"
PART = "data"
KIND = "toggle"
FLAG = "mhal"
ORDER = 18

ASSET_DIR = "micro_p_libs/micro_hal"
TARGET = "permanent/home/microp/micro_hal"


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    put_asset_dir(tree, TARGET, ASSET_DIR, ask)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    drop_asset_dir(tree, TARGET, ASSET_DIR, ask)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` — все файлы на месте и совпадают, иначе `off`.

    Ключи хешей — пути в комплекте (`hal_*.py`, `bins/libc_*.so`).
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
