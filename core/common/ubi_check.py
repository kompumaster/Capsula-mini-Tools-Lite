"""Проверка UBI/UBIFS через ubi_reader.

Битые узлы индекса - ошибка. Пустой том допустим: число записей
возвращается, решение принимает вызывающий код.
"""

from __future__ import annotations

import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]

# Раздел -> имя тома внутри UBI.
VOLUMES = {
    "system_a": "rootfs",
    "system_b": "rootfs",
    "data": "data",
}


def _add_ubitar_path() -> None:
    ubitar_root = CORE / "ubitar"
    if str(ubitar_root) not in sys.path:
        sys.path.insert(0, str(ubitar_root))


def read_ubi_params(path: Path) -> dict:
    """Параметры UBI/UBIFS без обхода индекса."""
    _add_ubitar_path()
    from ubitar.ubi_params import read_params
    return read_params(path)


def check_ubi(path: Path, params: dict | None = None) -> int:
    """Проверяет образ и возвращает число записей в томе."""
    _add_ubitar_path()
    from ubitar.ubifs_read import iter_entries

    if params is None:
        params = read_ubi_params(path)
    return sum(1 for _ in iter_entries(path, params["vol_name"]))
