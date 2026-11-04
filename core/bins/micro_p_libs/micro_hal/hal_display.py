"""Дисплей/часы: 30 физических каналов.

Запись кадра — один ioctl к `/dev/is31fl32xx` через
`libc_display.so`; чтение — sysfs `clock-led1…30`. Библиотека и
пакет `micro_hal` ставятся вместе: отдельного sysfs-пути записи нет.
"""

import os
import time

from micro_hal import hal_common
from micro_hal.hal_common import HalError

__all__ = [
    "COUNT", "MAX", "STOCK_MAX", "SYSFS_DIR", "LIB", "DEVICE",
    "clamp", "scale_values", "parse_channels", "channel_name",
    "available", "channels", "path", "set", "get", "raw", "clear",
    "scale", "probe", "forget",
]

COUNT = 30
MAX = 255
STOCK_MAX = 153
SYSFS_DIR = hal_common.SYSFS_LEDS
LIB = "/home/microp/micro_hal/bins/libc_display.so"
DEVICE = "/dev/is31fl32xx"

_channels = None
_values = None
_ready_done = False
_c = None


def clamp(value):
    value = int(value)
    if value < 0:
        return 0
    if value > MAX:
        return MAX
    return value


def scale_values(values, percent):
    percent = max(0, min(100, int(percent)))
    return [clamp(value) * percent // 100 for value in values]


def parse_channels(names):
    found = []
    for name in names:
        if not name.startswith("clock-led"):
            continue
        suffix = name[len("clock-led"):]
        if suffix.isdigit():
            found.append((int(suffix), name))
    found.sort()
    return [name for _number, name in found]


def channel_name(index):
    return "clock-led{}".format(index + 1)


def available():
    return len(channels()) > 0


def channels():
    global _channels
    if _channels is None:
        try:
            names = os.listdir(SYSFS_DIR)
        except OSError:
            names = []
        _channels = parse_channels(names)
    return _channels


def forget():
    """Закрыть C-дескриптор и забыть кэши."""
    global _channels, _values, _ready_done, _lock
    _close_c()
    if _lock is not None:
        _lock.release()
        _lock = None
    _channels = None
    _values = None
    _ready_done = False


def _check_index(index):
    index = int(index)
    if index < 0 or index >= COUNT:
        raise HalError("канал {} вне 0…{}".format(index, COUNT - 1))
    return index


_lock = None


def _open_c():
    global _c, _lock
    if _c is not None:
        return
    if _lock is None:
        _lock = hal_common.lock("display")
    fd = -1
    close = None
    try:
        try:
            import ffi

            library = ffi.open(LIB)
            open_ = library.func("i", "display_open", "s")
            count = library.func("i", "display_count", "i")
            frame = library.func("p", "display_frame", "")
            write = library.func("i", "display_write_frame", "i")
            close = library.func("i", "display_close", "i")
            get_errno = library.func("i", "display_errno", "")
        except Exception as exc:
            raise HalError("дисплей: не открыть {}: {}".format(LIB, exc))

        fd = open_(DEVICE)
        if fd < 0:
            raise HalError(
                "не открыть {}: errno {}".format(DEVICE, get_errno()))

        found = count(fd)
        if found != COUNT:
            raise HalError(
                "дисплей: {} каналов, ожидается {}".format(found, COUNT))

        pointer = frame()
        if not pointer:
            raise HalError("дисплей: нет буфера кадра")

        try:
            values = ffi.as_bytearray(pointer, COUNT)
        except Exception as exc:
            raise HalError("дисплей: нет доступа к буферу: {}".format(exc))

        _c = {
            "fd": fd,
            "library": library,
            "write": write,
            "close": close,
            "errno": get_errno,
            "values": values,
        }
    except Exception:
        if fd >= 0 and close is not None:
            try:
                close(fd)
            except Exception:
                pass
        if _lock is not None:
            _lock.release()
            _lock = None
        raise


def _close_c():
    global _c
    if _c is None:
        return
    try:
        _c["close"](_c["fd"])
    finally:
        _c = None


def _ready():
    global _ready_done
    if _ready_done:
        return
    hal_common.require_root()
    hal_common.require_va_stopped("дисплей")
    names = channels()
    if len(names) != COUNT:
        raise HalError(
            "дисплей: найдено {} каналов, ожидается {}".format(
                len(names), COUNT))
    _open_c()
    _ready_done = True


def path(index):
    index = _check_index(index)
    names = channels()
    if index >= len(names):
        raise HalError("нет канала {}".format(channel_name(index)))
    return "{}/{}/brightness".format(SYSFS_DIR, names[index])


def raw(values):
    """Записать 30 физических значений одним ioctl."""
    _ready()
    if len(values) != COUNT:
        raise HalError(
            "кадр: {} значений, ожидается {}".format(len(values), COUNT))
    new = [clamp(value) for value in values]
    buffer = _c["values"]
    for index in range(COUNT):
        buffer[index] = new[index]
    result = _c["write"](_c["fd"])
    if result != 0:
        raise HalError(
            "дисплей: ioctl errno {}".format(_c["errno"]()))
    global _values
    _values = new


def get(index):
    """Прочитать физический канал из sysfs."""
    _ready()
    index = _check_index(index)
    text = hal_common.read_text(path(index)).strip()
    return int(text) if text else 0


def set(index, value):
    """Изменить один канал, не трогая остальные."""
    _ready()
    index = _check_index(index)
    if _values is None:
        current = [get(number) for number in range(COUNT)]
    else:
        current = list(_values)
    current[index] = clamp(value)
    raw(current)


def clear():
    raw([0] * COUNT)


def scale(percent):
    _ready()
    if _values is None:
        current = [get(index) for index in range(COUNT)]
    else:
        current = list(_values)
    raw(scale_values(current, percent))


def probe(index=None, delay=1.0, value=STOCK_MAX):
    _ready()
    if index is None:
        indices = list(range(COUNT))
    else:
        indices = [_check_index(index)]
    for number in indices:
        print("канал {}/{}: {}".format(
            number + 1, COUNT, channels()[number]))
        set(number, value)
        time.sleep(delay)
        set(number, 0)
