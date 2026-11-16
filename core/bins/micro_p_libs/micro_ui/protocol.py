"""Разбор команд UDP-шины micro_ui.

Одна датаграмма — одна строка. Формат описан в `docs/PLAN.md` и
`micro_agent/docs/PLAN_UI_CLIENT.md`.
"""

from micro_ui.core import MODES
from micro_ui.errors import UiError
from micro_ui.faces import face_glyphs

MAX_BYTES = 256


def _int(value, name, low, high=None):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise UiError("{}: не целое число".format(name))
    if value < low or (high is not None and value > high):
        raise UiError("{} вне допустимого диапазона".format(name))
    return value


def _mode(value):
    value = str(value).lower()
    if value not in MODES:
        raise UiError("неизвестный режим: {}".format(value))
    return value


def parse(text):
    """Разобрать строку в команду; ошибка — `UiError`."""
    if not isinstance(text, str):
        raise UiError("команда должна быть строкой")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise UiError("команда длиннее {} байт".format(MAX_BYTES))
    parts = text.strip().split()
    if not parts:
        raise UiError("пустая команда")
    command = parts[0].lower()

    if command in ("mode", "sync"):
        if len(parts) not in (2, 3):
            raise UiError("формат: {} <режим> [lease_ms]".format(command))
        mode = _mode(parts[1])
        lease = None
        if len(parts) == 3:
            lease = _int(parts[2], "lease_ms", 0, None)
        return {"type": command, "name": mode, "lease_ms": lease}

    if command == "overlay":
        if len(parts) < 2:
            raise UiError("формат: overlay <имя> ...")
        name = parts[1].lower()
        if name == "volume":
            if len(parts) not in (3, 4):
                raise UiError(
                    "формат: overlay volume <0…100> [ttl_ms]")
            value = _int(parts[2], "volume", 0, 100)
            ttl = None
            if len(parts) == 4:
                ttl = _int(parts[3], "ttl_ms", 1, None)
            return {"type": "overlay", "name": "volume",
                    "value": value, "ttl_ms": ttl}
        if name == "date":
            if len(parts) not in (2, 3):
                raise UiError("формат: overlay date [ttl_ms]")
            ttl = None
            if len(parts) == 3:
                ttl = _int(parts[2], "ttl_ms", 1, None)
            return {"type": "overlay", "name": "date",
                    "value": None, "ttl_ms": ttl}
        raise UiError("неизвестный оверлей: {}".format(name))

    if command == "global":
        if len(parts) != 2:
            raise UiError("формат: global <0…100>")
        return {"type": "global",
                "value": _int(parts[1], "global", 0, 100)}

    if command == "auto":
        if len(parts) != 2 or parts[1].lower() not in ("on", "off"):
            raise UiError("формат: auto on|off")
        return {"type": "auto",
                "enabled": parts[1].lower() == "on"}

    if command == "face":
        if len(parts) not in (2, 3):
            raise UiError("формат: face <имя> [ttl_ms]")
        name = parts[1].lower()
        face_glyphs(name)
        ttl = None
        if len(parts) == 3:
            ttl = _int(parts[2], "ttl_ms", 1, None)
        return {"type": "face", "name": name, "ttl_ms": ttl}

    if command == "bright":
        if len(parts) != 3:
            raise UiError("формат: bright <дисплей> <кольцо>")
        return {
            "type": "bright",
            "display": _int(parts[1], "дисплей", 0, 100),
            "ring": _int(parts[2], "кольцо", 0, 100),
        }

    if command == "status":
        if len(parts) != 1:
            raise UiError("формат: status")
        return {"type": "status"}

    if command == "dither":
        if len(parts) != 2 or parts[1].lower() not in ("on", "off"):
            raise UiError("формат: dither on|off")
        return {"type": "dither",
                "enabled": parts[1].lower() == "on"}

    raise UiError("неизвестная команда: {}".format(command))
