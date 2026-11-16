"""Ротация логов: один файл 128 КБ, весь каталог 2048 КБ.

Запускается отдельным процессом, читает stdout/stderr агента из stdin.
Каждый файл называется `ГГГГММДД-ЧЧММСС-agent.log`; при ротации
создаётся новый файл с новым временем. Суффикс `-N` добавляется только
если несколько файлов попали в одну секунду.
"""

import os
import sys

MAX_FILE = 128 * 1024
MAX_TOTAL = 2048 * 1024


def _exists(path):
    try:
        os.stat(path)
    except OSError:
        return False
    return True


def _stamp():
    import time
    now = time.localtime()
    return "%04d%02d%02d-%02d%02d%02d-agent.log" % (
        now[0], now[1], now[2], now[3], now[4], now[5])


class LogWriter:
    """Пишет поток в файлы с ограничением размера."""

    def __init__(self, folder, base=None, max_file=MAX_FILE,
                 max_total=MAX_TOTAL):
        self.folder = str(folder)
        self.base = str(base) if base is not None else None
        if isinstance(max_file, bool) or not isinstance(max_file, int) \
                or max_file <= 0:
            raise ValueError("max_file должен быть положительным")
        if isinstance(max_total, bool) or not isinstance(max_total, int) \
                or max_total <= 0:
            raise ValueError("max_total должен быть положительным")
        self.max_file = max_file
        self.max_total = max_total
        self._path = None
        self._handle = None
        self._size = 0
        self._opened = False

    def open(self):
        if self._opened:
            return self
        if not _exists(self.folder):
            os.mkdir(self.folder)
        self._cleanup()
        self._path = self._unique(self.base or _stamp())
        self._open_handle()
        self._opened = True
        self._cleanup()
        return self

    def _unique(self, name):
        path = self.folder + "/" + name
        if not _exists(path):
            return path
        index = 1
        while _exists(path + "-" + str(index)):
            index += 1
        return path + "-" + str(index)

    def _open_handle(self):
        self._handle = open(self._path, "ab")
        try:
            self._size = os.stat(self._path)[6]
        except OSError:
            self._size = 0

    def write(self, data):
        if not self._opened:
            raise ValueError("лог не открыт")
        if isinstance(data, str):
            data = data.encode()
        if not isinstance(data, (bytes, bytearray)) or not data:
            return 0
        data = bytes(data)
        if self._size and self._size + len(data) > self.max_file:
            self._rotate()
        self._handle.write(data)
        self._handle.flush()
        self._size += len(data)
        self._cleanup()
        return len(data)

    def _rotate(self):
        self._handle.close()
        self._handle = None
        self._path = self._unique(_stamp())
        self._open_handle()
        self._cleanup()

    def _cleanup(self):
        try:
            names = os.listdir(self.folder)
        except OSError:
            return
        files = []
        for name in names:
            if "-agent.log" not in name:
                continue
            path = self.folder + "/" + name
            try:
                size = os.stat(path)[6]
            except OSError:
                continue
            files.append((name, path, size))
        files.sort(key=lambda item: item[0])
        total = sum(item[2] for item in files)
        for name, path, size in files:
            if total <= self.max_total:
                break
            if path == self._path:
                continue
            try:
                os.remove(path)
                total -= size
            except OSError:
                pass

    def close(self):
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:
                pass
        self._handle = None
        self._opened = False
        return True

    def files(self):
        try:
            names = sorted(os.listdir(self.folder))
        except OSError:
            return []
        return [name for name in names if "-agent.log" in name]

    def info(self):
        return {
            "folder": self.folder,
            "path": self._path,
            "size": self._size,
            "max_file": self.max_file,
            "max_total": self.max_total,
            "files": self.files(),
        }


def _read_stdin(size=4096):
    """Прочитать stdin: `os.read` на CPython, строка из `sys.stdin` в MicroPython."""
    reader = getattr(os, "read", None)
    if reader is not None:
        return reader(0, size)
    import sys
    stream = getattr(sys, "stdin", None)
    if stream is None:
        return b""
    line = stream.readline()
    if not line:
        return b""
    return line


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "/home/microp/logs"
    writer = LogWriter(folder)
    writer.open()
    try:
        while True:
            data = _read_stdin(4096)
            if not data:
                break
            writer.write(data)
    finally:
        writer.close()


if __name__ == "__main__":
    main()
