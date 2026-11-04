"""Кнопки CSK05T: чтение `/dev/input/event0`.

Только железо: найти устройство, открыть, отдать 24-байтные
`input_event` и закрыть. Имена клавиш, тайминги и сочетания — в
`lib_keys`.
"""

import os
import select
import struct

from micro_hal import hal_common
from micro_hal.hal_common import HalError

__all__ = [
    "EVENT_SIZE", "EV_SYN", "EV_KEY", "SYSFS_INPUT",
    "find_device", "device_name", "KeysDevice",
]

EVENT_SIZE = 24
EV_SYN = 0
EV_KEY = 1
SYSFS_INPUT = "/sys/class/input"


def device_name(path):
    """Имя устройства из sysfs; пустая строка, если нет."""
    entry = path.rsplit("/", 1)[-1]
    try:
        return hal_common.read_text(
            "{}/{}/device/name".format(SYSFS_INPUT, entry)).strip()
    except OSError:
        return ""


def find_device(name="csk05t"):
    """Путь к eventN с указанным именем; иначе `DEV_INPUT`."""
    try:
        entries = os.listdir(SYSFS_INPUT)
    except OSError:
        entries = []
    for entry in entries:
        if not entry.startswith("event"):
            continue
        path = "{}/{}".format(SYSFS_INPUT, entry)
        try:
            current = hal_common.read_text(path + "/device/name").strip()
        except OSError:
            continue
        if current == name:
            return "/dev/input/{}".format(entry)
    if hal_common.exists(hal_common.DEV_INPUT):
        return hal_common.DEV_INPUT
    raise HalError("не найдено устройство ввода: {}".format(name))


class KeysDevice:
    """Одно evdev-устройство: `poll`, `read`, `close`."""

    def __init__(self, path=None, name="csk05t"):
        hal_common.require_root()
        self._lock = hal_common.lock("keys")
        self._file = None
        try:
            self.path = path if path is not None else find_device(name)
            self.name = device_name(self.path)
            try:
                self._file = open(self.path, "rb")
            except OSError as exc:
                raise HalError(
                    "не открыть {}: {}".format(self.path, exc))
            self._poller = select.poll()
            self._poller.register(self._file, select.POLLIN)
        except Exception:
            if self._file is not None:
                try:
                    self._file.close()
                except OSError:
                    pass
                self._file = None
            if self._lock is not None:
                self._lock.release()
                self._lock = None
            raise

    def poll(self, timeout_ms=0):
        """Список событий `(sec, usec, type, code, value)`."""
        if self._file is None:
            raise HalError("устройство ввода закрыто")
        timeout_ms = max(0, int(timeout_ms))
        try:
            ready = self._poller.poll(timeout_ms)
        except OSError as exc:
            raise HalError("ошибка poll: {}".format(exc))
        events = []
        for _obj, mask in ready:
            if not (mask & select.POLLIN):
                continue
            data = self._file.read(EVENT_SIZE)
            if not data:
                continue
            if len(data) != EVENT_SIZE:
                raise HalError(
                    "короткое событие: {} байт".format(len(data)))
            sec, usec, kind, code, value = struct.unpack(
                "<qqHHi", data)
            events.append((sec, usec, kind, code, value))
        return events

    def read(self):
        """Одно событие или None."""
        events = self.poll(0)
        return events[0] if events else None

    def close(self):
        if self._file is None:
            return
        try:
            self._poller.unregister(self._file)
        except Exception:
            pass
        try:
            self._file.close()
        finally:
            self._file = None
            if self._lock is not None:
                self._lock.release()
                self._lock = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
