"""Правка tar-представления дерева без распаковки на диск.

Сохраняются `mode`, `uid`, `gid`, `mtime`, симлинки и hardlinks.
Служебный каталог `.ubitar/` (параметры образа) менять нельзя.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import tarfile
from pathlib import Path

from .errors import PatchError

META_DIR = ".ubitar"
META_NAME = f"{META_DIR}/ubi.json"
LINK_LIMIT = 8


def _norm(name: str) -> str:
    while name.startswith("./"):
        name = name[2:]
    return name.rstrip("/") or "."


def _check_path(path: str) -> str:
    key = _norm(path)
    if key == ".":
        raise PatchError("нельзя менять корень tar")
    if ".." in key.split("/"):
        raise PatchError(f"{path}: путь с '..' запрещён")
    if key.split("/", 1)[0] == META_DIR:
        raise PatchError(f"{path}: служебный каталог {META_DIR}/ менять нельзя")
    return key


def diff(before: dict, after: dict) -> tuple[set, set, set]:
    """Разница снимков: добавленные, удалённые, изменённые пути."""
    added = set(after) - set(before)
    removed = set(before) - set(after)
    changed = {path for path in set(before) & set(after)
               if before[path] != after[path]}
    return added, removed, changed


class TarTree:
    """Tar-дерево: чтение, правка в памяти, запись нового tar."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise PatchError(f"нет tar: {self.path}")

        self._members: list[tarfile.TarInfo] = []
        self._by_path: dict[str, tarfile.TarInfo] = {}
        with tarfile.open(self.path, "r") as archive:
            for info in archive:
                key = _norm(info.name)
                if key in self._by_path:
                    raise PatchError(f"tar: дубликат пути {key!r}")
                self._by_path[key] = info
                self._members.append(info)

        self._replace: dict[str, tuple[bytes, int | None]] = {}
        self._add: dict[str, tuple[bytes, int]] = {}
        self._remove: set[str] = set()
        self._dirs: dict[str, int] = {}

    # ------------------------------------------------------------ чтение

    @staticmethod
    def _kind(info: tarfile.TarInfo) -> str:
        if info.isdir():
            return "dir"
        if info.issym():
            return "link"
        if info.islnk():
            return "hardlink"
        if info.isreg():
            return "file"
        raise PatchError(f"{info.name}: неподдерживаемый тип tar")

    def exists(self, path: str) -> bool:
        key = _norm(path)
        if key in self._remove:
            return False
        if key in self._add or key in self._replace or key in self._dirs:
            return True
        return key in self._by_path

    def kind(self, path: str) -> str | None:
        key = _norm(path)
        if not self.exists(key):
            return None
        if key in self._dirs:
            return "dir"
        if key in self._add or key in self._replace:
            return "file"
        return self._kind(self._by_path[key])

    def mode(self, path: str) -> int | None:
        """Права записи с учётом запланированных правок."""
        key = _norm(path)
        if not self.exists(key):
            return None
        if key in self._dirs:
            return self._dirs[key]
        if key in self._add:
            return self._add[key][1]
        if key in self._replace:
            mode = self._replace[key][1]
            return self._by_path[key].mode if mode is None else mode
        return self._by_path[key].mode

    def read(self, path: str) -> bytes:
        return self._read(_norm(path), 0)

    def _read(self, key: str, depth: int) -> bytes:
        if depth > LINK_LIMIT:
            raise PatchError(f"{key}: цепочка hardlink слишком длинная")
        if key in self._remove:
            raise PatchError(f"{key}: удалён")
        if key in self._add:
            if key in self._dirs:
                raise PatchError(f"{key}: это каталог")
            return self._add[key][0]
        if key in self._replace:
            return self._replace[key][0]

        info = self._by_path.get(key)
        if info is None:
            raise PatchError(f"{key}: нет в tar")
        kind = self._kind(info)
        if kind == "hardlink":
            return self._read(_norm(info.linkname), depth + 1)
        if kind != "file":
            raise PatchError(f"{key}: это {kind}, а не файл")
        with tarfile.open(self.path, "r") as archive:
            handle = archive.extractfile(info)
            if handle is None:
                raise PatchError(f"{key}: нет данных в tar")
            return handle.read()

    def sha256(self, path: str) -> str:
        return hashlib.sha256(self.read(path)).hexdigest()

    def meta(self) -> dict:
        try:
            data = json.loads(self.read(META_NAME).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise PatchError(f"{META_NAME}: не читается: {exc}") from exc
        if not isinstance(data, dict):
            raise PatchError(f"{META_NAME}: ожидался объект")
        return data

    # ------------------------------------------------------------ правка

    def ensure_dir(self, path: str) -> None:
        key = _check_path(path)
        kind = self.kind(key)
        if kind == "dir":
            return
        if kind is not None:
            raise PatchError(f"{path}: уже существует как {kind}")
        if "/" in key:
            self.ensure_dir(key.rsplit("/", 1)[0])
        self._dirs[key] = 0o755

    def add(self, path: str, data: bytes, mode: int = 0o644) -> None:
        key = _check_path(path)
        if self.exists(key):
            raise PatchError(f"{path}: уже существует")
        if "/" in key:
            self.ensure_dir(key.rsplit("/", 1)[0])
        self._remove.discard(key)
        self._add[key] = (bytes(data), mode)

    def replace(self, path: str, data: bytes,
                mode: int | None = None) -> None:
        key = _check_path(path)
        if not self.exists(key):
            raise PatchError(f"{path}: нет в tar")
        if self.kind(key) == "dir":
            raise PatchError(f"{path}: это каталог")
        self._remove.discard(key)
        if key in self._add:
            old_mode = self._add[key][1]
            self._add[key] = (bytes(data), old_mode if mode is None else mode)
        else:
            self._replace[key] = (bytes(data), mode)

    def remove(self, path: str) -> None:
        key = _check_path(path)
        if not self.exists(key):
            raise PatchError(f"{path}: нет в tar")
        if key in self._add:
            del self._add[key]
            self._dirs.pop(key, None)
            return
        self._replace.pop(key, None)
        self._remove.add(key)

    # ------------------------------------------------------------ снимок

    def snapshot(self) -> dict:
        """Состояние дерева: путь -> (тип, права, sha256|цель).

        У неизменённых файлов sha256 = None: сравнение идёт по факту
        правки, а не по пересчёту всех данных.
        """
        result: dict[str, tuple] = {}
        for key, info in self._by_path.items():
            if key in self._remove:
                continue
            if key in self._replace:
                data, mode = self._replace[key]
                result[key] = ("file",
                               info.mode if mode is None else mode,
                               hashlib.sha256(data).hexdigest())
                continue
            if key in self._add:
                data, mode = self._add[key]
                result[key] = ("file", mode, hashlib.sha256(data).hexdigest())
                continue
            kind = self._kind(info)
            if kind == "file":
                result[key] = (kind, info.mode, None)
            elif kind in ("link", "hardlink"):
                result[key] = (kind, info.mode, info.linkname)
            else:
                result[key] = (kind, info.mode, None)

        for key, mode in self._dirs.items():
            result.setdefault(key, ("dir", mode, None))
        for key, (data, mode) in self._add.items():
            if key in self._dirs:
                continue
            result.setdefault(key, ("file", mode,
                                    hashlib.sha256(data).hexdigest()))
        return result

    # ------------------------------------------------------------ запись

    def write(self, out: Path) -> None:
        out = Path(out)
        if out.resolve() == self.path.resolve():
            raise PatchError("нельзя писать tar поверх исходного")
        out.parent.mkdir(parents=True, exist_ok=True)
        written: set[str] = set()

        with tarfile.open(self.path, "r") as src, \
                tarfile.open(out, "w", format=tarfile.GNU_FORMAT) as dst:
            for info in self._members:
                key = _norm(info.name)
                if key in self._remove:
                    continue
                if key in self._add:
                    data, mode = self._add[key]
                    dst.addfile(self._new_file(key, data, mode),
                                io.BytesIO(data))
                elif key in self._replace:
                    data, mode = self._replace[key]
                    dst.addfile(self._replacement(info, data, mode),
                                io.BytesIO(data))
                elif info.isreg():
                    handle = src.extractfile(info)
                    if handle is None:
                        raise PatchError(f"{key}: нет данных в tar")
                    dst.addfile(copy.copy(info), handle)
                else:
                    dst.addfile(copy.copy(info))
                written.add(key)

            for key in sorted(self._dirs, key=lambda p: (p.count("/"), p)):
                if key in written or key in self._by_path:
                    continue
                dst.addfile(self._new_dir(key))

            for key in sorted(self._add, key=lambda p: (p.count("/"), p)):
                if key in written or key in self._dirs:
                    continue
                data, mode = self._add[key]
                dst.addfile(self._new_file(key, data, mode), io.BytesIO(data))

    @staticmethod
    def _replacement(info: tarfile.TarInfo, data: bytes,
                     mode: int | None) -> tarfile.TarInfo:
        new = copy.copy(info)
        new.type = tarfile.REGTYPE
        new.size = len(data)
        new.linkname = ""
        if mode is not None:
            new.mode = mode
        return new

    @staticmethod
    def _new_file(key: str, data: bytes, mode: int) -> tarfile.TarInfo:
        info = tarfile.TarInfo(key)
        info.type = tarfile.REGTYPE
        info.mode = mode
        info.uid = 0
        info.gid = 0
        info.mtime = 0
        info.size = len(data)
        return info

    @staticmethod
    def _new_dir(key: str) -> tarfile.TarInfo:
        info = tarfile.TarInfo(key)
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        info.uid = 0
        info.gid = 0
        info.mtime = 0
        info.size = 0
        return info


__all__ = ["META_DIR", "META_NAME", "TarTree", "diff"]
