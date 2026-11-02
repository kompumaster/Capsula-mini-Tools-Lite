"""Приблизительные размеры разделов.

Нужны для процентов при чтении и для проверки отклонения при записи.
Это не эталон разметки: на другой версии прошивки размеры могут
отличаться.
"""

from __future__ import annotations

PEB = 131072

APPROX = {
    "system_a": 512 * PEB,   # 64.0 МиБ
    "system_b": 512 * PEB,   # 64.0 МиБ
    "data": 620 * PEB,       # 77.5 МиБ
    "boot_a": 128 * PEB,     # 16.0 МиБ
    "boot_b": 128 * PEB,     # 16.0 МиБ
    "misc": 16 * PEB,        # 2.0 МиБ
}


def deviation(part: str, size: int) -> float | None:
    """Относительное отклонение размера от таблицы, или None."""
    base = APPROX.get(part)
    if not base:
        return None
    return abs(size - base) / base
