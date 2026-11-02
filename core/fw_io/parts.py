"""Размеры разделов VK Капсулы Мини (Amlogic A113X, 256 МиБ NAND)."""

from __future__ import annotations

PEB = 131072

# Размеры логического образа раздела.
PART_SIZES = {
    "bootloader": 2 * 1024 * 1024,
    "tpl": 8 * 1024 * 1024,
    "misc": 2 * 1024 * 1024,
    "boot_a": 16 * 1024 * 1024,
    "boot_b": 16 * 1024 * 1024,
    "system_a": 64 * 1024 * 1024,
    "system_b": 64 * 1024 * 1024,
    "data": 81_264_640,          # 620 PEB; 622 адресных, 2 бэда
}


def size_for(part: str, override: int | None = None) -> int:
    if override is not None:
        if override <= 0 or override % PEB:
            raise ValueError(f"неверный размер {override}")
        return override
    try:
        return PART_SIZES[part]
    except KeyError as exc:
        raise ValueError(
            f"неизвестный раздел {part!r}; укажите --size"
        ) from exc
