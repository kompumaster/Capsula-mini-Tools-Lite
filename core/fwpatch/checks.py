"""Проверки входного UBI-образа перед патчем.

- размер кратен PEB;
- образ читается как UBI, индекс не битый (`check_ubi`);
- имя тома соответствует разделу;
- отклонение размера от `common.sizes.APPROX` больше 10 % требует
  подтверждения (по умолчанию N).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from common.sizes import APPROX, PEB, deviation
from common.ubi_check import VOLUMES, check_ubi, read_ubi_params

from .errors import PatchError

# Имя оставлено для совместимости с тестами и внешним кодом.
read_params = read_ubi_params

SIZE_TOLERANCE = 0.10

# Раздел -> имя тома в образе; патчер работает только с этими двумя.
EXPECTED_VOLUME = {
    part: VOLUMES[part] for part in ("system_b", "data")
}

Ask = Callable[[str, bool], bool]


def expected_volume(part: str) -> str:
    """Имя тома, которое должно быть в образе раздела."""
    try:
        return EXPECTED_VOLUME[part]
    except KeyError as exc:
        raise PatchError(f"неизвестный раздел {part!r}") from exc


def validate_image(path: Path, part: str, *,
                   no_check_size: bool = False,
                   ask: Ask | None = None) -> dict:
    """Проверяет образ и возвращает параметры тома.

    `ask(вопрос, default)` вызывается только при отклонении размера
    больше 10 %. Без `ask` такое отклонение считается отказом.
    """
    if not path.is_file():
        raise PatchError(f"нет файла {path}")
    size = path.stat().st_size
    if size == 0 or size % PEB:
        raise PatchError(
            f"{path}: размер {size} Б не кратен PEB {PEB}")

    try:
        params = dict(read_params(path))
    except Exception as exc:
        raise PatchError(
            f"{path}: не читаются параметры UBI: {exc}") from exc

    expected = expected_volume(part)
    actual = params.get("vol_name")
    if actual != expected:
        raise PatchError(
            f"{path}: том {actual!r}, ожидался {expected!r} для {part}")

    try:
        records = check_ubi(path, params)
    except Exception as exc:
        raise PatchError(
            f"{path}: проверка UBI не прошла: {exc}") from exc

    if not no_check_size:
        delta = deviation(part, size)
        if delta is not None and delta > SIZE_TOLERANCE:
            question = (
                f"{path}: размер {size} Б отличается от типичного "
                f"({APPROX[part]} Б) на {delta * 100:.0f}%. Продолжить?"
            )
            if ask is None or not ask(question, False):
                raise PatchError(f"{path}: размер не подтверждён")

    params["records"] = records
    params["size"] = size
    return params


__all__ = [
    "SIZE_TOLERANCE", "EXPECTED_VOLUME", "Ask",
    "expected_volume", "validate_image",
]
