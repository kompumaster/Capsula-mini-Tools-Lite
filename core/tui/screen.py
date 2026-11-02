"""Отрисовка экрана TUI."""

from __future__ import annotations

import os
import sys

TITLE = "Capsula-mini Tools Lite"


class Screen:
    def __init__(self):
        self.tty = sys.stdin.isatty() and sys.stdout.isatty()
        self._set_title()

    def _set_title(self) -> None:
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleTitleW(TITLE)
            except Exception:
                pass
            return
        if self.tty and os.environ.get("TERM") != "dumb":
            sys.stdout.write(f"\033]0;{TITLE}\007")
            sys.stdout.flush()

    def clear(self) -> None:
        if not self.tty:
            return
        if os.name == "nt":
            os.system("cls")
        else:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

    def title(self, text: str) -> None:
        print(text)
        print("=" * len(text))
        print()

    def menu(self, items) -> None:
        for key, label in items:
            print(f"{key}) {label}")
        print()

    def message(self, text: str = "") -> None:
        print(text)

    def prompt(self, text: str = "Выбор: ") -> None:
        print(text, end="", flush=True)

    def pause(self, text: str = "Enter — вернуться...") -> None:
        if not self.tty:
            return
        try:
            input(text)
        except EOFError:
            pass
