"""PulseAudio: поиск сокета и окружение для клиентов.

Только стек: где сейчас Pulse (`PULSE_SERVER`) и как передать это
`pactl`, `pacat`/`paplay` и `parec`. Команды запускают `hal_volume`,
`hal_speaker`, `hal_mic` и `hal_bt`; здесь — один поиск на процесс.

Порядок: `PULSE_SERVER` из окружения → `$XDG_RUNTIME_DIR/pulse/native`
→ `/run/user/*/pulse/native` → самый свежий `/tmp/pulse-*/native`.
Путь проверяется: это должен быть сокет; если MicroPython не отдаёт
тип, достаточно существования.
"""

import os

from micro_hal import hal_common

__all__ = ["ENV", "server", "prefix", "forget"]

ENV = "PULSE_SERVER"

# Тип файла в `os.stat()`: старшие биты режима.
_MASK = 0o170000
_SOCKET = 0o140000

# Найденный путь без префикса `unix:`; кэш на процесс.
_CACHE = None


def _socket(path):
    """Похож ли путь на сокет Pulse."""
    try:
        info = os.stat(path)
    except OSError:
        return False
    try:
        mode = info[0]
    except (IndexError, TypeError):
        mode = getattr(info, "st_mode", 0)
    if not mode:
        # Тип не прочитать — доверяем существованию.
        return True
    return (mode & _MASK) == _SOCKET


def _proc_env(name):
    """Значение переменной из `/proc/self/environ` (в MicroPython нет
    `os.environ`, но окружение процесса есть)."""
    try:
        text = hal_common.read_text("/proc/self/environ")
    except OSError:
        return None
    prefix = name + "="
    for item in text.split("\x00"):
        if item.startswith(prefix):
            value = item[len(prefix):]
            return value or None
    return None


def _env(name):
    """Значение переменной окружения или `None`."""
    try:
        env = os.environ
    except AttributeError:
        return _proc_env(name)
    value = env.get(name)
    if value:
        return str(value)
    return None


def _from_env():
    """Значение `PULSE_SERVER`, если оно задано."""
    return _env(ENV)


def _from_xdg():
    """`$XDG_RUNTIME_DIR/pulse/native`."""
    base = _env("XDG_RUNTIME_DIR")
    if not base:
        return None
    path = "{}/pulse/native".format(base.rstrip("/"))
    if _socket(path):
        return path
    return None


def _from_run_user():
    """`/run/user/<uid>/pulse/native` для любого uid."""
    try:
        names = os.listdir("/run/user")
    except OSError:
        return None
    for name in names:
        if not name.isdigit():
            continue
        path = "/run/user/{}/pulse/native".format(name)
        if _socket(path):
            return path
    return None


def _from_tmp():
    """Самый свежий `/tmp/pulse-*/native`."""
    try:
        names = os.listdir("/tmp")
    except OSError:
        return None
    best = None
    best_time = None
    for name in names:
        if not name.startswith("pulse-"):
            continue
        path = "/tmp/{}/native".format(name)
        if not _socket(path):
            continue
        try:
            moment = os.stat(path)[8]
        except (OSError, IndexError, TypeError):
            moment = 0
        if best_time is None or moment > best_time:
            best = path
            best_time = moment
    return best


def server():
    """Адрес сокета Pulse (`unix:...`) или `None`, если не найден."""
    global _CACHE
    value = _from_env()
    if value:
        return value
    if _CACHE is not None and _socket(_CACHE):
        return "unix:" + _CACHE
    for find in (_from_xdg, _from_run_user, _from_tmp):
        path = find()
        if path:
            _CACHE = path
            return "unix:" + path
    _CACHE = None
    return None


def prefix():
    """Приставка для shell-команды или пустая строка."""
    value = server()
    if not value:
        return ""
    return "{}={} ".format(ENV, hal_common.quote(value))


def forget():
    """Сбросить кэш поиска (перезапуск Pulse, тесты)."""
    global _CACHE
    _CACHE = None
