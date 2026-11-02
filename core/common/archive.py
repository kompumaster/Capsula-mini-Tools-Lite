"""Архивация папки в zip рядом с ней.

Используется `backup_lite` для `backup/parts` и `fw_patch_lite` для
папки вывода: старые файлы пакуются в `<имя>_<время>.zip`, затем
исходная папка очищается.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def archive_folder(folder: Path, *, prefix: str | None = None,
                   remove: bool = True) -> Path | None:
    """Пакует содержимое папки в zip на уровень выше.

    Возвращает путь к архиву или `None`, если папка пуста.
    При `remove=True` после успешной упаковки содержимое удаляется.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return None
    entries = sorted(folder.iterdir())
    if not entries:
        return None

    name = prefix or folder.name
    stamp = _stamp()
    archive = folder.parent / f"{name}_{stamp}.zip"
    index = 1
    while archive.exists():
        archive = folder.parent / f"{name}_{stamp}-{index}.zip"
        index += 1

    tmp = archive.with_name(archive.name + ".tmp")
    tmp.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(folder.rglob("*")):
                if not (path.is_file() or path.is_symlink()):
                    continue
                bundle.write(path, arcname=path.relative_to(folder).as_posix())
        os.replace(tmp, archive)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise

    if remove:
        for entry in entries:
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    return archive
