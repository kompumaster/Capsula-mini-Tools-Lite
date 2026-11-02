"""Пути, которые нужны патчеру Lite.

Структура: `core/bins` и `core/stubs` — локальные копии,
`core/ubitar` — локальная копия проекта `UbiTar`.
"""

from __future__ import annotations

from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
ROOT = CORE.parent

BINS = CORE / "bins"
STUBS = CORE / "stubs"
UBITAR = CORE / "ubitar"
UBITAR_BINS = UBITAR / "bins"

__all__ = ["CORE", "ROOT", "BINS", "STUBS", "UBITAR", "UBITAR_BINS"]
