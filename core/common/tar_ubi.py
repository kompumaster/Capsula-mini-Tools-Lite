"""UBI-образы и преобразование раздела в tar через UbiTar.

tar кладётся рядом с образом и называется по имени образа:
`system_b.adb.bin` -> `system_b.adb.tar`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

UBI_MAGIC = b"UBI#"

COMPR = {
    0: "none",
    1: "lzo",
    2: "zlib",
    3: "zstd",
}


@dataclass(frozen=True)
class TarImage:
    path: Path
    folder: Path
    part: str
    tar: Path


@dataclass(frozen=True)
class TarFile:
    path: Path
    folder: Path
    image: Path


def part_of(image: Path) -> str:
    """Имя раздела: часть имени до первой точки."""
    image = Path(image)
    part = image.name.split(".", 1)[0]
    if not part:
        raise ValueError(f"не удалось определить раздел: {image}")
    return part


def tar_for(image: Path) -> Path:
    """tar рядом с образом, по имени образа."""
    return Path(image).with_suffix(".tar")


def is_ubi(path: Path) -> bool:
    """Проверяет сигнатуру UBI# в начале файла."""
    try:
        with Path(path).open("rb") as stream:
            return stream.read(4) == UBI_MAGIC
    except OSError:
        return False


def list_images(folders) -> list[TarImage]:
    """UBI-образы из папок по порядку; внутри папки — по имени."""
    result = []
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.bin")):
            if not is_ubi(path):
                continue
            result.append(TarImage(
                path=path,
                folder=folder,
                part=part_of(path),
                tar=tar_for(path),
            ))
    return result


def unpack(image: Path, force: bool = False) -> Path:
    """Раздел -> tar через `fwpatch.build` (UbiTar)."""
    from fwpatch import build

    image = Path(image)
    return build.unpack(image, part_of(image), tar_for(image),
                        force=force)


_RECORDS = re.compile(
    r"записей: файлов (\d+), каталогов (\d+), "
    r"симлинков (\d+), hardlinks (\d+)")


def summary(image: Path, output: str) -> list[str]:
    """Краткая сводка по тому из образа и вывода UbiTar."""
    image = Path(image)
    lines = []
    try:
        from common.ubi_check import read_ubi_params

        params = read_ubi_params(image)
        sb = params.get("sb", {})
        compr = COMPR.get(sb.get("compr"), "?")
        lines.append(f"том: {params.get('vol_name')}")
        lines.append(f"размер: {image.stat().st_size} Б")
        lines.append(
            f"PEB: {params.get('peb')}, LEB: {sb.get('leb_size')}, "
            f"сжатие: {compr}")
    except Exception:
        pass
    match = _RECORDS.search(output or "")
    if match:
        lines.append(
            f"записей: файлов {match.group(1)}, каталогов "
            f"{match.group(2)}, симлинков {match.group(3)}, "
            f"hardlinks {match.group(4)}")
    return lines


def unpack_details(image: Path, force: bool = False) -> tuple[Path, list[str]]:
    """Раздел -> tar с краткой сводкой по тому."""
    from fwpatch import build

    image = Path(image)
    tar, output = build.unpack(
        image, part_of(image), tar_for(image), force=force, report=True)
    return tar, summary(image, output)


def image_for_tar(tar: Path) -> Path:
    """Образ рядом с tar, по имени tar."""
    return Path(tar).with_suffix(".bin")


def list_tars(folders) -> list[TarFile]:
    """tar-файлы из папок по порядку; внутри папки — по имени."""
    result = []
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.tar")):
            result.append(TarFile(
                path=path,
                folder=folder,
                image=image_for_tar(path),
            ))
    return result


def compression_for(tar: Path) -> tuple[str, str | None]:
    """Сжатие из tar; zstd заменяется на zlib с предупреждением."""
    from fwpatch.tar_tree import TarTree

    meta = TarTree(Path(tar)).meta()
    code = meta.get("compr")
    name = COMPR.get(code, code if isinstance(code, str) else "zlib")
    if name not in ("none", "lzo", "zlib"):
        return "zlib", "zstd заменён на zlib: ядро 4.9 не читает"
    return name, None


def pack(tar: Path, force: bool = False) -> tuple[Path, str | None]:
    """tar -> образ через `fwpatch.build` (UbiTar)."""
    from fwpatch import build

    tar = Path(tar)
    compr, warning = compression_for(tar)
    image = build.pack(tar, image_for_tar(tar), compr=compr, force=force)
    return image, warning
