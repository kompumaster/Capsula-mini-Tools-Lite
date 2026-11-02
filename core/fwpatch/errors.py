"""Ошибки патчера Lite."""

from __future__ import annotations


class PatchError(RuntimeError):
    """Проверка, конфликт или отказ пользователя."""
