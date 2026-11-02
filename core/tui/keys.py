"""Ввод одной клавиши: Linux — termios, Windows — msvcrt."""

from __future__ import annotations

import os
import sys


def read_key() -> str:
    """Одна клавиша без Enter; EOF в неинтерактивном режиме — 'q'."""
    if os.name == "nt":
        try:
            import msvcrt
            return msvcrt.getwch()
        except ImportError:
            pass

    if sys.stdin.isatty():
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    line = sys.stdin.readline()
    if line == "":
        return "q"
    return line.strip()[:1]
