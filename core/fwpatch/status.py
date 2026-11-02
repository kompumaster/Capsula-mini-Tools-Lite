"""Состояние патчей и `status.txt`.

Статус означает наличие функции:

- `on`  — файл/функция есть: оригинал (tele/fwu/swu) или наш
  добавленный файл (adb/ssh/lapi);
- `off` — файла нет или он заменён заглушкой.

Состояния и хеши собираются из реестра патчей: каждый модуль сам
знает, что искать в дереве. Формат `status.txt` — плоский `KEY=VALUE`.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import PatchError
from .patches import BY_PART, PART_ORDER
from .tar_tree import TarTree

# Ключи раздела в порядке реестра.
PART_KEYS = {
    part: tuple(module.KEY for module in modules)
    for part, modules in BY_PART.items()
}

COMPR = {
    0: "none",
    1: "lzo",
    2: "zlib",
    3: "zstd",
}


@dataclass
class Status:
    part: str
    file: str
    size: int
    sha256: str
    compr: str
    states: dict[str, str] = field(default_factory=dict)
    hashes: dict[str, dict[str, str]] = field(default_factory=dict)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compr_name(code) -> str:
    if code is None:
        return "unknown"
    return COMPR.get(code, f"unknown({code})")


def detect(tree: TarTree, part: str) -> tuple[dict[str, str],
                                              dict[str, dict[str, str]]]:
    """Возвращает (состояния, хеши) для раздела.

    Хеши добавляются только для найденных файлов; пустые записи
    не создаются.
    """
    try:
        modules = BY_PART[part]
    except KeyError:
        raise PatchError(f"неизвестный раздел {part!r}") from None

    states: dict[str, str] = {}
    hashes: dict[str, dict[str, str]] = {}
    for module in modules:
        state, module_hashes = module.detect(tree)
        states[module.KEY] = state
        if module_hashes:
            hashes[module.KEY] = module_hashes
    return states, hashes


def make_status(part: str, file: str, image: Path, tree: TarTree,
                params: dict) -> Status:
    states, hashes = detect(tree, part)
    return Status(
        part=part,
        file=file,
        size=image.stat().st_size,
        sha256=sha256_file(image),
        compr=compr_name(params.get("sb", {}).get("compr")),
        states=states,
        hashes=hashes,
    )


def render(statuses: list[Status]) -> str:
    lines = ["# fw_patch_lite status 1"]
    for status in statuses:
        lines.extend([
            f"{status.part}.file={status.file}",
            f"{status.part}.size={status.size}",
            f"{status.part}.sha256={status.sha256}",
            f"{status.part}.compr={status.compr}",
        ])
        for key in PART_KEYS.get(status.part, ()):
            lines.append(f"{status.part}.{key}={status.states.get(key, 'off')}")
            for logical, digest in status.hashes.get(key, {}).items():
                lines.append(
                    f"{status.part}.{key}.{logical}.sha256={digest}")
    return "\n".join(lines) + "\n"


def parse_status(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise PatchError(f"status: строка {number}: нет '='")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise PatchError(f"status: строка {number}: пустой ключ")
        result[key] = value.strip()
    return result


def _decode_status(data: bytes, path: Path) -> str:
    """UTF-8 (с BOM) или cp1251; иначе — понятная ошибка."""
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise PatchError(
        f"status: не читается {path}: нужен UTF-8 или cp1251")


def read_status(path: Path) -> dict[str, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PatchError(f"status: не читается {path}: {exc}") from exc
    return parse_status(_decode_status(raw, path))


def write_status(path: Path, statuses: list[Status]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(render(statuses), encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def file_map(data: dict[str, str]) -> dict[str, str]:
    """part -> имя файла из status.txt."""
    result = {}
    for part in PART_ORDER:
        value = data.get(f"{part}.file")
        if value:
            result[part] = value
    return result


__all__ = [
    "PART_KEYS", "Status", "detect", "make_status", "render",
    "parse_status", "read_status", "write_status", "file_map",
    "compr_name", "sha256_file",
]
