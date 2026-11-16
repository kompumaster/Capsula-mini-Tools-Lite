"""Настройки своего агента: `.env` (шаблон `example.env`) и системный
промпт в `/home`.

`/home` - симлинк на `/data/permanent/home`, поэтому в образе пути
начинаются с `permanent/home`.

Файлы кладутся только если их нет: ключи в `.env` и правки промпта не
перезаписываются, даже если шаблон в комплекте изменился. `remove`
удаляет только те файлы, что побайтово совпадают с шаблоном, - то есть
поставленные нами и никем не тронутые.

`a_settings.ini` не копируется: агент создаёт его сам при первом старте
из умолчаний (`micro_agent/settings.py`).

Нужен патч `home` (симлинк `/home` на `/data/permanent/home`) и `mplibs`
(сам агент).
"""

from __future__ import annotations

from fwpatch.tar_tree import TarTree

from .common import Ask, asset_bytes, asset_sha, present_sha

KEY = "agentcfg"
TITLE = "Настр. MP агента"
SUMMARY = "Подготовить настройки агента на micropython"
PART = "data"
KIND = "toggle"
FLAG = "agentcfg"
ORDER = 19

ENV_PATH = "permanent/home/.env"
ENV_ASSET = "config/example.env"
PROMPT_PATH = "permanent/home/system.txt"
PROMPT_ASSET = "config/system.txt"

FILES = (
    (ENV_PATH, ENV_ASSET, 0o600),
    (PROMPT_PATH, PROMPT_ASSET, 0o644),
)


def apply(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, mode in FILES:
        if tree.exists(path):
            continue
        tree.add(path, asset_bytes(asset), mode)


def remove(tree: TarTree, ask: Ask | None = None) -> None:
    for path, asset, _mode in FILES:
        if not tree.exists(path):
            continue
        if (tree.kind(path) == "file"
                and tree.sha256(path) == asset_sha(asset)):
            tree.remove(path)


def detect(tree: TarTree) -> tuple[str, dict[str, str]]:
    """`on` - оба файла на месте, даже если содержимое правленое."""
    hashes = {}
    state = "on"
    for path, _asset, _mode in FILES:
        digest = present_sha(tree, path)
        if digest is None:
            state = "off"
            continue
        hashes[path] = digest
    return state, hashes
