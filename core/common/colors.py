"""Цветной вывод: ANSI только когда поток — терминал.

На Windows включает VT-режим у консоли; при перенаправлении вывода
или в тестах цвет не добавляется.
"""

from __future__ import annotations

import os
import sys

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
GREY = "\033[90m"

_prepared = False


def _enable_windows_vt() -> None:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        for handle_id in (-11, -12):        # stdout, stderr
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def paint(text: str, color: str, stream=None) -> str:
    """Красит текст, если поток — терминал; иначе возвращает как есть."""
    global _prepared
    stream = stream if stream is not None else sys.stdout
    if not getattr(stream, "isatty", lambda: False)():
        return text
    if os.name == "nt" and not _prepared:
        _prepared = True
        _enable_windows_vt()
    return f"{color}{text}{RESET}"


__all__ = ["RESET", "RED", "GREEN", "YELLOW", "GREY", "paint"]
