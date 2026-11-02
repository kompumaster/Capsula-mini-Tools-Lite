"""Реестр патчей Lite.

`REGISTRY` — единственный список модулей; порядок задаёт `ORDER`
в каждом модуле. `PATCHES` и `KILLS` — представления по типу,
`BY_PART` — по разделу, в порядке `PART_ORDER`.
"""

from __future__ import annotations

from fwpatch.errors import PatchError

from . import (patch_adb, patch_fwupdate, patch_lapi, patch_mpython,
               patch_ssh, patch_swupdate, patch_telemetryd,
               patch_vkkill, patch_vkvoice)

# Порядок применения разделов; не зависит от ORDER патчей.
PART_ORDER = ("system_b", "data")

def validate_registry(modules) -> None:
    """Проверяет метаданные и функции модулей патчей.

    Ошибка — `PatchError` с именем модуля: тихий пропуск недопустим.
    """
    keys: set = set()
    flags: set = set()
    orders: set = set()

    for module in modules:
        name = getattr(module, "__name__",
                       getattr(module, "KEY", repr(module)))

        def field(attr: str):
            if not hasattr(module, attr):
                raise PatchError(f"патч {name}: нет {attr}")
            return getattr(module, attr)

        key = field("KEY")
        title = field("TITLE")
        part = field("PART")
        kind = field("KIND")
        flag = field("FLAG")
        order = field("ORDER")

        if not isinstance(key, str) or not key:
            raise PatchError(f"патч {name}: KEY должен быть строкой")
        if not isinstance(title, str) or not title:
            raise PatchError(f"патч {name}: TITLE должен быть строкой")
        if not isinstance(flag, str) or not flag:
            raise PatchError(f"патч {name}: FLAG должен быть строкой")
        if not isinstance(order, int):
            raise PatchError(f"патч {name}: ORDER должен быть числом")
        if kind not in ("toggle", "kill"):
            raise PatchError(f"патч {name}: неизвестный KIND={kind!r}")
        if part not in PART_ORDER:
            raise PatchError(
                f"патч {name}: PART={part!r} нет в PART_ORDER {PART_ORDER}")
        if not callable(getattr(module, "detect", None)):
            raise PatchError(f"патч {name}: нет detect()")

        if kind == "toggle":
            for attr in ("apply", "remove"):
                if not callable(getattr(module, attr, None)):
                    raise PatchError(f"патч {name}: нет {attr}()")
        elif not callable(getattr(module, "kill", None)):
            raise PatchError(f"патч {name}: нет kill()")

        for value, seen, label in ((key, keys, "KEY"),
                                   (flag, flags, "FLAG"),
                                   (order, orders, "ORDER")):
            if value in seen:
                raise PatchError(
                    f"патч {name}: повтор {label}={value!r}")
            seen.add(value)


MODULES = (patch_lapi, patch_mpython, patch_adb, patch_ssh,
           patch_vkvoice, patch_telemetryd, patch_fwupdate,
           patch_swupdate, patch_vkkill)
validate_registry(MODULES)
REGISTRY = tuple(sorted(MODULES, key=lambda module: module.ORDER))

PATCHES = {module.KEY: module for module in REGISTRY
           if module.KIND == "toggle"}

KILLS = {module.KEY: module for module in REGISTRY
         if module.KIND == "kill"}

BY_PART = {
    part: tuple(module for module in REGISTRY if module.PART == part)
    for part in PART_ORDER
}

__all__ = [
    "PART_ORDER", "REGISTRY", "PATCHES", "KILLS", "BY_PART",
    "validate_registry",
    "patch_adb", "patch_fwupdate", "patch_lapi", "patch_mpython",
    "patch_ssh", "patch_swupdate", "patch_telemetryd",
    "patch_vkkill", "patch_vkvoice",
]
