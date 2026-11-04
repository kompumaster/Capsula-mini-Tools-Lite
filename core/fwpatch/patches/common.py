"""Общие операции патчей: положить/удалить файл с подтверждением."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from fwpatch.assets import BINS, STUBS
from fwpatch.errors import PatchError
from fwpatch.tar_tree import TarTree

Ask = Callable[[str, bool], bool]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def asset_bytes(name: str, base: Path = BINS) -> bytes:
    path = base / name
    if not path.is_file():
        raise PatchError(f"нет ассета {path}")
    return path.read_bytes()


@lru_cache(maxsize=None)
def asset_sha(name: str) -> str:
    """SHA-256 ассета из `core/bins`."""
    return sha(asset_bytes(name))


def present_sha(tree: TarTree, path: str) -> str | None:
    """SHA-256 файла или hardlink; `None`, если пути нет."""
    if tree.kind(path) in ("file", "hardlink"):
        return tree.sha256(path)
    return None


@lru_cache(maxsize=None)
def stub_hashes() -> frozenset[str]:
    result = set()
    for name in ("noop", "noop1"):
        path = STUBS / name
        if path.is_file():
            result.add(sha(path.read_bytes()))
    if not result:
        raise PatchError(f"нет заглушек в {STUBS}")
    return frozenset(result)


def _confirm(ask: Ask | None, path: str) -> bool:
    if ask is None:
        raise PatchError(
            f"{path}: не совпадает с нашим патчем, нужно подтверждение")
    return ask(f"{path}: не совпадает с нашим патчем, продолжить?", True)


def put(tree: TarTree, path: str, data: bytes, mode: int,
        ask: Ask | None = None) -> None:
    """Добавить файл; чужой файл заменить только после подтверждения."""
    if not tree.exists(path):
        tree.add(path, data, mode)
        return
    if tree.kind(path) == "file" and tree.sha256(path) == sha(data):
        return
    if not _confirm(ask, path):
        raise PatchError(f"{path}: отменено")
    tree.replace(path, data, mode)


def drop(tree: TarTree, path: str, expected: bytes | None = None,
         ask: Ask | None = None) -> None:
    """Удалить файл; чужой — только после подтверждения."""
    if not tree.exists(path):
        return
    if expected is not None:
        ours = (tree.kind(path) == "file"
                and tree.sha256(path) == sha(expected))
        if not ours and not _confirm(ask, path):
            raise PatchError(f"{path}: отменено")
    tree.remove(path)


def asset_files(asset_dir: str, base: Path = BINS):
    """Файлы каталога ассетов: `(путь от каталога, ассет, mode)`.

    `.so` получают 0755, остальные — 0644; `__pycache__` и `.pyc`
    пропускаются.
    """
    root = base / asset_dir
    if not root.is_dir():
        raise PatchError(f"нет каталога ассетов {root}")
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = path.relative_to(root).as_posix()
        mode = 0o755 if path.suffix == ".so" else 0o644
        files.append((rel, (Path(asset_dir) / rel).as_posix(), mode))
    if not files:
        raise PatchError(f"пустой каталог ассетов {root}")
    return tuple(files)


def put_asset_dir(tree: TarTree, target: str, asset_dir: str,
                  ask: Ask | None = None) -> None:
    """Положить весь каталог ассетов в `target/<относительный путь>`."""
    for rel, asset, mode in asset_files(asset_dir):
        put_asset(tree, f"{target}/{rel}", asset, mode, ask)


def drop_asset_dir(tree: TarTree, target: str, asset_dir: str,
                   ask: Ask | None = None) -> None:
    """Удалить весь каталог ассетов из `target/...`."""
    for rel, asset, _mode in asset_files(asset_dir):
        drop_asset(tree, f"{target}/{rel}", asset, ask)


def put_asset(tree: TarTree, path: str, asset: str, mode: int,
              ask: Ask | None = None) -> None:
    put(tree, path, asset_bytes(asset), mode, ask)


def drop_asset(tree: TarTree, path: str, asset: str,
               ask: Ask | None = None) -> None:
    drop(tree, path, asset_bytes(asset), ask)


def kill_stub(tree: TarTree, path: str, stub: str) -> None:
    """Заменить оригинал заглушкой; отсутствующий или уже заглушка — no-op."""
    if not tree.exists(path):
        return
    if tree.kind(path) == "file" and tree.sha256(path) in stub_hashes():
        return
    tree.replace(path, asset_bytes(stub, STUBS), 0o755)
