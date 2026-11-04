"""Действия TUI: вызовы core-скриптов, статусы, образы, поиск IP."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import backup_lite
import fw_patch_lite
import write_lite
from common import reboot as reboot_tool
from common.find_ip import find_capsula
from common.tar_ubi import TarFile, TarImage, list_images, list_tars
from common.tar_ubi import pack as pack_tar
from common.tar_ubi import unpack as unpack_ubi
from common.tar_ubi import unpack_details as unpack_ubi_details
from fwpatch import status as fwstatus
from fwpatch.errors import PatchError
from fwpatch.patches import KILLS, PATCHES, PART_ORDER

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "backup" / "parts"
PATCHED = ROOT / "patched" / "parts"
STATUS = BACKUP / "status.txt"
STATUS_NAME = "status.txt"

# Списки берутся из реестра патчей: порядок и состав задаются модулями.
FEATURES = tuple(PATCHES)
STUBS = tuple(KILLS)
KILL_FLAGS = {key: f"--{module.FLAG}-kill"
              for key, module in KILLS.items()}


def run_backup() -> int:
    return backup_lite.main([])


def display_state(part: str, key: str, value: str) -> str:
    """Состояние для TUI: у заглушек on/off показываем как work/kill."""
    module = KILLS.get(key)
    if module is not None and module.PART == part:
        if value == "on":
            return "work"
        if value == "off":
            return "kill"
    return value


def has_patch_source(folder: Path | None = None) -> bool:
    """Есть ли в источнике готовые образы для патча."""
    folder = Path(folder) if folder is not None else BACKUP
    return any(folder.glob("*.bin"))


def backup_status_text(path: Path | None = None) -> list[str]:
    default = path is None
    path = Path(path) if path is not None else STATUS
    if not path.is_file():
        if not default:
            return ["статус не снят: нет status.txt"]
        code, _data, error = patch_status()
        if code:
            return [f"статус не снят: {error or 'ошибка status'}"]
        path = BACKUP / STATUS_NAME
        if not path.is_file():
            return ["статус не снят: status.txt не создан"]
    try:
        data = fwstatus.read_status(path)
    except PatchError as exc:
        return [f"ошибка status.txt: {exc}"]

    lines = []
    for part in PART_ORDER:
        name = data.get(f"{part}.file")
        if not name:
            continue
        states = []
        for key in fwstatus.PART_KEYS[part]:
            value = data.get(f"{part}.{key}")
            if value is None:
                continue
            value = display_state(part, key, value)
            states.append(f"{key}={value}")
        lines.append(f"{name}: " + " ".join(states) if states else name)
    return lines or ["в status.txt нет данных system_b/data"]


def tar_images() -> list[TarImage]:
    """UBI-образы для «Сервис → Раздел → tar»."""
    return list_images((BACKUP, PATCHED))


def unpack_to_tar(image: TarImage, force: bool = False) -> Path:
    """Раздел -> tar рядом с образом."""
    return unpack_ubi(image.path, force=force)


def unpack_to_tar_details(image: TarImage,
                          force: bool = False) -> tuple[Path, list[str]]:
    """Раздел -> tar и краткая сводка по тому."""
    return unpack_ubi_details(image.path, force=force)


def tar_files() -> list[TarFile]:
    """tar-файлы для «Сервис → tar → раздел»."""
    return list_tars((BACKUP, PATCHED))


def pack_from_tar(item: TarFile,
                  force: bool = False) -> tuple[Path, str | None]:
    """tar -> образ рядом с tar."""
    return pack_tar(item.path, force=force)


def open_folder(path: Path | None = None) -> bool:
    path = Path(path) if path is not None else BACKUP
    if not path.is_dir():
        return False
    if os.name == "nt":
        command = ["explorer", str(path)]
    elif sys.platform == "darwin":
        command = ["open", str(path)]
    else:
        command = ["xdg-open", str(path)]
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True


def patch_status() -> tuple[int, dict, str]:
    """Запускает --status, возвращает (код, данные, ошибка)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = fw_patch_lite.main(["--src", str(BACKUP), "--status"])
    if code != 0:
        text = (err.getvalue() or out.getvalue()).strip()
        return code, {}, text or "статус не снят"
    path = BACKUP / STATUS_NAME
    if not path.is_file():
        return 1, {}, "status.txt не создан"
    try:
        return 0, fwstatus.read_status(path), ""
    except PatchError as exc:
        return 1, {}, str(exc)


def patch_flags(overrides: dict[str, str]) -> list[str]:
    args = []
    for key in FEATURES:
        if key in overrides:
            args.append(f"--{PATCHES[key].FLAG}-{overrides[key]}")
    for key in STUBS:
        if overrides.get(key) == "kill":
            args.append(KILL_FLAGS[key])
    return args


def run_patch(overrides: dict[str, str]) -> int:
    args = ["--src", str(BACKUP), "--out", str(PATCHED)]
    args.extend(patch_flags(overrides))
    return fw_patch_lite.main(args)


def current_patch_state(data: dict[str, str], key: str) -> str | None:
    module = PATCHES.get(key) or KILLS.get(key)
    if module is None:
        return None
    value = data.get(f"{module.PART}.{key}")
    if module.KIND == "kill":
        if value == "on":
            return "work"
        if value == "off":
            return "kill"
        return None
    return value if value in ("on", "off") else None


def patch_label(data: dict[str, str], overrides: dict[str, str],
                key: str) -> str:
    value = overrides.get(key, current_patch_state(data, key))
    if value is None:
        return "[?]"
    mark = "*" if key in overrides else ""
    return f"[{value}]{mark}"


def toggle_patch(overrides: dict[str, str], data: dict[str, str],
                 key: str) -> None:
    current = current_patch_state(data, key)
    if key in STUBS:
        if key in overrides:
            del overrides[key]
        elif current != "kill":
            overrides[key] = "kill"
        return

    effective = overrides.get(key, current)
    if current is None:
        # Неизвестное состояние: on -> off -> снять выбор.
        new = {"on": "off", "off": None}.get(effective, "on")
        if new is None:
            overrides.pop(key, None)
        else:
            overrides[key] = new
        return

    new = "off" if effective == "on" else "on"
    if new == current:
        overrides.pop(key, None)
    else:
        overrides[key] = new


IMAGE_PARTS = PART_ORDER


@dataclass
class ImageInfo:
    path: Path
    part: str
    states: str


def image_states(data: dict[str, str], part: str) -> str:
    states = []
    for key in fwstatus.PART_KEYS.get(part, ()):
        value = data.get(f"{part}.{key}")
        if value is None:
            continue
        value = display_state(part, key, value)
        states.append(f"{key}={value}")
    return " ".join(states) or "нет данных"


def load_images(folder: Path) -> list[ImageInfo]:
    folder = Path(folder)
    data: dict[str, str] = {}
    status_path = folder / STATUS_NAME
    if status_path.is_file():
        try:
            data = fwstatus.read_status(status_path)
        except PatchError:
            data = {}

    result = []
    for path in sorted(folder.glob("*.bin")):
        part = path.name.split(".", 1)[0]
        if part not in IMAGE_PARTS:
            continue
        if data.get(f"{part}.file") != path.name:
            states = "нет данных"
        else:
            states = image_states(data, part)
        result.append(ImageInfo(path, part, states))
    return result


def write_image(image: ImageInfo) -> int:
    return write_lite.main([
        "--part", image.part,
        "--file", str(image.path),
        "--no-confirm",
    ])


def find_column_ip() -> str | None:
    return find_capsula()


def reboot_column() -> tuple[int, list[str]]:
    """Перезагрузить колонку; возвращает код и строки вывода."""
    lines: list[str] = []
    code = reboot_tool.reboot(log=lines.append)
    return code, lines
