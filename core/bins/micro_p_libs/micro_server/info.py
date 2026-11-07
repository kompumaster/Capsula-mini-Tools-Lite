"""Снимок состояния колонки для страницы и API.

Системная часть (Python, память, время, uptime) собирается всегда.
Аппаратная (Wi-Fi, громкость) — через `micro_hal`, лениво и с
запасным вариантом: если модуля нет, поля просто пустые.
"""

import gc
import os
import sys
import time

import micro_server


def _uptime():
    try:
        handle = open("/proc/uptime", "r")
        try:
            return float(handle.read().split()[0])
        finally:
            handle.close()
    except Exception:
        return None


def _format_seconds(seconds):
    seconds = int(seconds)
    return "{}:{:02d}:{:02d}".format(
        seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def _now():
    value = time.localtime()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        value[0], value[1], value[2], value[3], value[4], value[5])


def _read(path):
    try:
        handle = open(path, "r")
    except Exception:
        return ""
    try:
        return handle.read()
    finally:
        handle.close()


def _cpu_arch():
    for line in _read("/proc/cpuinfo").splitlines():
        if line.startswith("CPU architecture"):
            value = line.split(":", 1)[1].strip()
            if value == "8":
                return "aarch64"
            if value == "7":
                return "armv7"
            return "armv" + value
    return ""


def _system():
    data = {"python": getattr(sys, "version", "")}

    data["hostname"] = _read("/proc/sys/kernel/hostname").strip()
    data["release"] = _read("/proc/sys/kernel/osrelease").strip()
    board = _read("/proc/device-tree/model").replace("\x00", "").strip()
    if board:
        data["board"] = board
    machine = _cpu_arch()
    if machine:
        data["machine"] = machine

    try:
        uname = os.uname()
        data["hostname"] = data.get("hostname") or uname[1]
        data["release"] = data.get("release") or uname[2]
        data["machine"] = data.get("machine") or uname[-1]
    except Exception:
        pass

    for key in ("hostname", "release", "machine", "board"):
        if not data.get(key):
            data.pop(key, None)

    uptime = _uptime()
    if uptime is not None:
        data["uptime"] = _format_seconds(uptime)
    return data


def _memory():
    data = {}
    try:
        data["free"] = gc.mem_free()
    except Exception:
        pass
    try:
        data["alloc"] = gc.mem_alloc()
    except Exception:
        pass
    return data


def _hardware():
    """Данные из micro_hal; любая ошибка не ломает снимок."""
    result = {"network": {}, "sound": {}, "versions": {}, "time": {}}
    try:
        import micro_hal
    except Exception:
        return result
    result["versions"]["micro_hal"] = getattr(
        micro_hal, "__version__", None)
    try:
        from micro_hal import lib_wifi
        state = lib_wifi.status()
        result["network"] = {
            "ssid": state.get("ssid"),
            "state": state.get("state"),
            "ip": state.get("ip"),
            "saved": lib_wifi.saved(),
        }
    except Exception as exc:
        result["network"] = {"error": str(exc)[:120]}
    try:
        from micro_hal import lib_speaker
        result["sound"] = {"volume": lib_speaker.get_volume()}
    except Exception as exc:
        result["sound"] = {"error": str(exc)[:120]}
    try:
        from micro_hal import lib_ntp
        result["time"]["timezone"] = lib_ntp.get_timezone()
    except Exception:
        pass
    for name in ("micro_tts", "micro_asr"):
        try:
            module = __import__(name)
            result["versions"][name] = getattr(
                module, "__version__", None)
        except Exception:
            pass
    return result


def collect(server=None, hardware=True):
    """Собрать снимок состояния."""
    data = {
        "ok": True,
        "server": {
            "version": micro_server.__version__,
            "port": getattr(server, "port", None),
        },
        "system": _system(),
        "time": {"now": _now()},
        "memory": _memory(),
        "versions": {"micro_server": micro_server.__version__},
        "network": {},
        "sound": {},
    }
    if hardware:
        extra = _hardware()
        data["network"] = extra.get("network", {})
        data["sound"] = extra.get("sound", {})
        data["time"].update(extra.get("time", {}))
        data["versions"].update(extra.get("versions", {}))
    return data
