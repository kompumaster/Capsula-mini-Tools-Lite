"""Датчик света BH1730FVC: чтение освещённости из sysfs.

Только железо: один файл IIO, драйвер отдаёт уже готовые люксы
(дробное число). Логики поверх нет, отдельный `lib_light` не нужен.
При импорте ничего не читается.
"""

from micro_hal import hal_common
from micro_hal.hal_common import HalError

__all__ = ["SYSFS", "available", "read", "lux"]

SYSFS = hal_common.SYSFS_LIGHT


def available(path=None):
    """Есть ли файл датчика света."""
    return hal_common.exists(SYSFS if path is None else path)


def read(path=None):
    """Освещённость в люксах, как её отдаёт sysfs (float)."""
    path = SYSFS if path is None else path
    try:
        text = hal_common.read_text(path)
    except OSError as exc:
        raise HalError(
            "датчик света: не прочитать {}: {}".format(path, exc))
    text = text.strip()
    if not text:
        raise HalError("датчик света: пустое значение")
    try:
        return float(text)
    except ValueError:
        raise HalError("датчик света: не число: {!r}".format(text))


def lux(path=None):
    """Освещённость в люксах (то же, что `read`)."""
    return read(path)
