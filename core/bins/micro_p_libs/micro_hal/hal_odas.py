"""ODAS: запуск и остановка `odaslive`, PID и лог.

Только процесс: путь к демону, библиотека, конфиг, `kill`. JSON и
направление — в `lib_odas`. `voice-agent` должен быть остановлен.
"""

import os
import time

from micro_hal import hal_common
from micro_hal.hal_common import HalError

__all__ = [
    "ODASLIVE", "LIBDIR", "LIB", "CONFIG", "SSS_CONFIG", "LOG",
    "PID_FILE", "STARTED",
    "available", "running", "start", "stop", "restart", "status",
    "started", "uptime", "log_tail",
]

# Бинарник лежит в overlay и виден как /usr/bin/odaslive.
ODASLIVE = "/data/overlay/upper/usr/bin/odaslive"
LIBDIR = "/home/microp"
LIB = "/home/microp/libodas.so"
CONFIG = "/home/microp/odas/capsula_4_mic.cfg"
SSS_CONFIG = "/home/microp/odas/capsula_4_mic_sss.cfg"
# Файлы состояния — на процесс: два скрипта не мешают друг другу.
_PID = hal_common.self_pid()
LOG = "/tmp/micro_hal_odas.{}.log".format(_PID)
PID_FILE = "/tmp/micro_hal_odas.{}.pid".format(_PID)
STARTED = "/tmp/micro_hal_odas.{}.started".format(_PID)


def _quote(path):
    text = str(path)
    if "'" in text or "\n" in text or "\r" in text:
        raise HalError("недопустимый путь: {!r}".format(text))
    return "'{}'".format(text)


def _read_pid():
    try:
        text = hal_common.read_text(PID_FILE).strip()
    except OSError:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _forget_pid():
    for path in (PID_FILE, STARTED):
        try:
            os.remove(path)
        except OSError:
            pass


def _alive(pid):
    return hal_common.exists("/proc/{}".format(pid))


_lock = None


def _claim():
    """Замок: один `odaslive` и один набор портов на систему."""
    global _lock
    if _lock is None:
        _lock = hal_common.lock("odas")
    return _lock


def _release():
    global _lock
    if _lock is not None:
        _lock.release()
        _lock = None


def _is_exec(path):
    try:
        info = os.stat(str(path))
    except OSError:
        return False
    mode = info.st_mode if hasattr(info, "st_mode") else info[0]
    return bool(mode & 0o111)


def _scan():
    """PID осиротевшего `odaslive` micro_hal или None."""
    for pid, cmdline in hal_common.processes():
        if ("odaslive" in cmdline and " -c " in cmdline
                and hal_common.stale_owner(pid, "micro_hal_odas.")):
            return pid
    return None


def running():
    """PID `odaslive` или None (включая осиротевший)."""
    pid = _read_pid()
    if pid is not None:
        if _alive(pid):
            try:
                cmdline = hal_common.read_text(
                    "/proc/{}/cmdline".format(pid)).replace("\x00", " ")
            except OSError:
                cmdline = ""
            if "odaslive" in cmdline:
                return pid
        _forget_pid()
    return _scan()


def available(config=CONFIG):
    """Есть ли бинарник, библиотека и конфиг."""
    return (_is_exec(ODASLIVE) and
            hal_common.exists(LIB) and
            hal_common.exists(config))


def started():
    """Время запуска (Unix) или None."""
    try:
        text = hal_common.read_text(STARTED).strip()
    except OSError:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def uptime():
    """Сколько секунд работает ODAS, или None."""
    if running() is None:
        return None
    value = started()
    if value is None:
        return None
    return max(0.0, time.time() - value)


def log_tail(lines=10):
    """Последние строки лога (для диагностики)."""
    try:
        text = hal_common.read_text(LOG)
    except OSError:
        return ""
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    if lines > 0:
        parts = parts[-lines:]
    return "\n".join(parts).strip()


def start(config=CONFIG, single=False, verbose=False):
    """Запустить `odaslive` в фоне; вернуть PID."""
    hal_common.require_va_stopped("ODAS")
    if running() is not None:
        raise HalError("ODAS уже запущен")
    if not _is_exec(ODASLIVE):
        raise HalError("нет исполняемого {}".format(ODASLIVE))
    if not hal_common.exists(LIB):
        raise HalError("нет библиотеки {}".format(LIB))
    if not hal_common.exists(config):
        raise HalError("нет конфига {}".format(config))

    flags = ""
    if single:
        flags += " -s"
    if verbose:
        flags += " -v"
    # Лог пишем только в отладочном режиме: без -v он не нужен,
    # а /tmp — это RAM. При ошибке без лога подскажем включить verbose.
    log_path = LOG if verbose else "/dev/null"
    command = (
        "LD_LIBRARY_PATH={libdir} {binary} -c {config}{flags} "
        "> {log} 2>&1 & echo $! > {pid}"
    ).format(
        libdir=_quote(LIBDIR),
        binary=_quote(ODASLIVE),
        config=_quote(config),
        flags=flags,
        log=_quote(log_path),
        pid=_quote(PID_FILE),
    )

    _claim()
    try:
        hal_common.write_text(STARTED, str(time.time()))
        hal_common.run(command)
        time.sleep(0.1)
        pid = running()
        if pid is None:
            if verbose:
                raise HalError(
                    "ODAS не запустился: {}".format(log_tail(5)))
            raise HalError(
                "ODAS не запустился (подробности — verbose=True)")
    except Exception:
        _forget_pid()
        _release()
        raise
    return pid


def stop(timeout=3.0):
    """Остановить `odaslive`; True, если процесс был."""
    pid = running()
    if pid is None:
        _forget_pid()
        _release()
        return False
    hal_common.run("kill {}".format(pid))
    for _ in range(max(1, int(float(timeout) * 20))):
        if not _alive(pid):
            break
        time.sleep(0.05)
    if _alive(pid):
        hal_common.run("kill -9 {}".format(pid))
        time.sleep(0.1)
    _forget_pid()
    _release()
    return True


def restart(config=CONFIG, single=False, verbose=False):
    """Остановить и снова запустить ODAS."""
    stop()
    return start(config=config, single=single, verbose=verbose)


def status(config=CONFIG):
    """Краткое состояние процесса."""
    pid = running()
    return {
        "available": available(config),
        "running": pid,
        "pid": pid,
        "config": config,
        "sss_config": SSS_CONFIG,
        "log": LOG,
        "started": started(),
        "uptime": uptime(),
    }
