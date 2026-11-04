"""Микрофоны: запуск `parec`, сырой PCM и PID фонового процесса.

Только железо: источник Pulse, команда, PID, остановка. WAV, уровни
и моно — в `lib_mic`. Важно: для `mics` нужен `--no-remap`, иначе
Pulse отдаёт нули (проверено на плате 03.11.2026).
"""

import os
import time

from micro_hal import hal_common
from micro_hal.hal_common import HalError

__all__ = [
    "SOURCE", "SOURCES", "RATE", "CHANNELS", "WIDTH",
    "PAREC", "PACTL", "PID_FILE", "RAW",
    "LIB", "WINDOW_MS", "SETTLE_MS", "Stream", "library",
    "sources", "available", "running", "start", "stop", "capture",
]

SOURCE = "mics"
SOURCES = ("mics", "mics_loopback")
RATE = 16000
CHANNELS = 4
WIDTH = 2

PAREC = "/usr/bin/parec"
PACTL = "/usr/bin/pactl"
# Файлы состояния — на процесс: два скрипта не мешают друг другу.
_PID = hal_common.self_pid()
PID_FILE = "/tmp/micro_hal_mic.{}.pid".format(_PID)
RAW = "/tmp/micro_hal_mic.{}.raw".format(_PID)

# C-хелпер непрерывного захвата: окно 20 мс, оседание DC — 300 мс.
LIB = "/home/microp/micro_hal/bins/libc_mic.so"
WINDOW_MS = 20
SETTLE_MS = 300

# Метка в cmdline: по ней находится осиротевший `parec` другого скрипта.
CLIENT = "micro_hal-mic"


def _quote(path):
    """Путь в одинарных кавычках; кавычки и переводы строк запрещены."""
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
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def _alive(pid):
    return hal_common.exists("/proc/{}".format(pid))


_lock = None


def _claim():
    """Замок: одна файловая запись на процесс."""
    global _lock
    if _lock is None:
        _lock = hal_common.lock("mic")
    return _lock


def _release():
    global _lock
    if _lock is not None:
        _lock.release()
        _lock = None


def sources():
    """Имена источников Pulse."""
    code, text = hal_common.capture(PACTL + " list short sources")
    if code != 0:
        raise HalError("pactl list short sources: код {}".format(code))
    names = []
    for line in text.split("\n"):
        parts = line.split()
        if len(parts) >= 2:
            names.append(parts[1])
    return names


def available(source=SOURCE):
    """Есть ли `parec` и указанный источник."""
    if not hal_common.exists(PAREC):
        return False
    try:
        return source in sources()
    except HalError:
        return False


def _scan():
    """PID осиротевшего `parec` micro_hal или None."""
    for pid, cmdline in hal_common.processes():
        if (CLIENT in cmdline and "parec" in cmdline
                and hal_common.stale_owner(pid, "micro_hal_mic.")):
            return pid
    return None


def running():
    """PID фонового `parec` или None (включая осиротевший)."""
    pid = _read_pid()
    if pid is not None:
        if _alive(pid):
            try:
                cmdline = hal_common.read_text(
                    "/proc/{}/cmdline".format(pid)).replace("\x00", " ")
            except OSError:
                cmdline = ""
            if "parec" in cmdline:
                return pid
        _forget_pid()
    return _scan()


def _check_source(source):
    source = str(source)
    if source not in SOURCES:
        raise HalError("неизвестный источник: {!r}".format(source))
    names = sources()
    if source not in names:
        raise HalError("нет источника {} (есть: {})".format(
            source, ", ".join(names)))
    return source


def start(path, source=SOURCE, channels=CHANNELS, rate=RATE,
          latency_msec=40):
    """Запустить `parec` в фоне; вернуть PID."""
    hal_common.require_va_stopped("микрофоны")
    source = _check_source(source)
    if running() is not None:
        raise HalError("запись уже идёт")

    channels = int(channels)
    rate = int(rate)
    if channels <= 0 or rate <= 0:
        raise HalError("channels и rate должны быть больше нуля")
    text = str(path)
    folder = text.rsplit("/", 1)[0] if "/" in text else "."
    if folder and not hal_common.exists(folder):
        raise HalError("нет каталога для записи: {}".format(folder))

    command = (
        "{parec} --device={source} --rate={rate} --channels={channels} "
        "--format=s16le --raw --no-remap{latency} "
        "--client-name={client} > {path} 2>/dev/null "
        "& echo $! > {pid}"
    ).format(
        parec=PAREC,
        source=_quote(source),
        rate=rate,
        channels=channels,
        latency="" if latency_msec is None else
        " --latency-msec={}".format(int(latency_msec)),
        client=CLIENT,
        path=_quote(text),
        pid=_quote(PID_FILE),
    )
    _claim()
    try:
        hal_common.run(command)
        time.sleep(0.05)
        pid = running()
        if pid is None:
            raise HalError("parec не запустился: {}".format(source))
    except Exception:
        _release()
        raise
    return pid


def stop():
    """Остановить `parec`; True, если процесс был."""
    pid = running()
    if pid is None:
        _forget_pid()
        _release()
        return False
    hal_common.run("kill {}".format(pid))
    for _ in range(10):
        if not _alive(pid):
            break
        time.sleep(0.05)
    if _alive(pid):
        hal_common.run("kill -9 {}".format(pid))
        time.sleep(0.05)
    _forget_pid()
    _release()
    return True


def capture(path, seconds, source=SOURCE, channels=CHANNELS, rate=RATE,
            latency_msec=40):
    """Писать `seconds` секунд в `path`; вернуть размер файла."""
    seconds = float(seconds)
    if seconds <= 0:
        raise HalError("длительность должна быть больше нуля")
    start(path, source=source, channels=channels, rate=rate,
          latency_msec=latency_msec)
    try:
        time.sleep(seconds)
    finally:
        stop()
    try:
        size = os.stat(str(path))[6]
    except OSError as exc:
        raise HalError("нет файла записи {}: {}".format(path, exc))
    if size <= 0:
        raise HalError("пустая запись: {}".format(path))
    return size


class _Library:
    """Тонкая обёртка над `libc_mic.so`; в тестах подменяется."""

    def __init__(self, path=LIB):
        import ffi

        self._ffi = ffi
        self._lib = ffi.open(str(path))
        self._open = self._lib.func("i", "mic_open", "siiii")
        self._read = self._lib.func("i", "mic_read", "")
        self._buffer = self._lib.func("p", "mic_buffer", "")
        self._mono = self._lib.func("i", "mic_mono", "")
        self._mono_buffer = self._lib.func("p", "mic_mono_buffer", "")
        self._rms = self._lib.func("i", "mic_rms", "i")
        self._peak = self._lib.func("i", "mic_peak", "i")
        self._window = self._lib.func("i", "mic_window", "")
        self._window_bytes = self._lib.func("i", "mic_window_bytes", "")
        self._channels = self._lib.func("i", "mic_channels", "")
        self._rate = self._lib.func("i", "mic_rate", "")
        self._frames = self._lib.func("i", "mic_frames", "")
        self._latency = self._lib.func("i", "mic_latency", "")
        self._close = self._lib.func("i", "mic_close", "")
        self._error = self._lib.func("s", "mic_error", "")

    def open(self, source, rate, channels, window_ms, settle_ms):
        return self._open(str(source), int(rate), int(channels),
                          int(window_ms), int(settle_ms))

    def read(self):
        return self._read()

    def mono(self):
        return self._mono()

    def view(self, size):
        return self._ffi.as_bytearray(self._buffer(), int(size))

    def mono_view(self, size):
        return self._ffi.as_bytearray(self._mono_buffer(), int(size))

    def rms(self, channel):
        return self._rms(int(channel))

    def peak(self, channel):
        return self._peak(int(channel))

    def window(self):
        return self._window()

    def window_bytes(self):
        return self._window_bytes()

    def channels(self):
        return self._channels()

    def rate(self):
        return self._rate()

    def frames(self):
        return self._frames()

    def latency(self):
        return self._latency()

    def close(self):
        return self._close()

    def error(self):
        return self._error()


def library(path=LIB):
    """Загрузить C-хелпер; ошибка — `HalError`."""
    try:
        return _Library(path)
    except (OSError, ImportError) as exc:
        raise HalError("нет {}: {}".format(path, exc))


class Stream:
    """Непрерывный захват через `libc_mic.so`.

    `read()` отдаёт одно окно (20 мс) сырого PCM, `mono()` — то же
    окно, сведённое в моно, `stats()` — уровни за последнее окно.
    Один поток на процесс: второй `open()` даёт `HalError`.
    """

    def __init__(self, source=SOURCE, rate=RATE, channels=CHANNELS,
                 window_ms=WINDOW_MS, settle_ms=SETTLE_MS,
                 lib=None):
        self.source = str(source)
        self.rate = int(rate)
        self.channels = int(channels)
        self.window_ms = int(window_ms)
        self.settle_ms = int(settle_ms)
        self._lib = lib
        self._opened = False
        self._buffer = None
        self._mono = None
        self._window = 0

    def _helper(self):
        if self._lib is None:
            self._lib = library()
        return self._lib

    def open(self):
        """Открыть поток; вернуть себя."""
        hal_common.require_va_stopped("микрофоны")
        if self._opened:
            raise HalError("поток уже открыт")
        lib = self._helper()
        code = lib.open(self.source, self.rate, self.channels,
                        self.window_ms, self.settle_ms)
        if code != 0:
            raise HalError("микрофоны: {}".format(
                lib.error() or "не удалось открыть поток"))
        self._opened = True
        self._window = int(lib.window())
        self.channels = int(lib.channels())
        self.rate = int(lib.rate())
        self._buffer = lib.view(self._window * self.channels * 2)
        self._mono = lib.mono_view(self._window * 2)
        return self

    def running(self):
        return self._opened

    def read(self):
        """Одно окно сырого PCM (`bytes`)."""
        if not self._opened:
            raise HalError("поток не открыт")
        frames = self._helper().read()
        if frames < 0:
            raise HalError("микрофоны: {}".format(
                self._helper().error() or "ошибка чтения"))
        size = frames * self.channels * 2
        return bytes(self._buffer[:size])

    def mono(self):
        """То же окно, сведённое в моно (`bytes`, 2 байта на кадр)."""
        if not self._opened:
            raise HalError("поток не открыт")
        frames = self._helper().mono()
        if frames < 0:
            raise HalError("микрофоны: {}".format(
                self._helper().error() or "ошибка микширования"))
        return bytes(self._mono[:frames * 2])

    def stats(self):
        """Уровни за последнее окно: кадры, RMS и пик по каналам."""
        if not self._opened:
            raise HalError("поток не открыт")
        lib = self._helper()
        return {
            "frames": int(lib.frames()),
            "rms": [int(lib.rms(channel)) for channel in range(self.channels)],
            "peak": [int(lib.peak(channel))
                     for channel in range(self.channels)],
        }

    def frames(self):
        """Сколько кадров прочитано с момента открытия."""
        if not self._opened:
            return 0
        return int(self._helper().frames())

    def window(self):
        return self._window

    def window_bytes(self):
        return self._window * self.channels * 2

    def latency(self):
        """Задержка потока в микросекундах или -1."""
        if not self._opened:
            raise HalError("поток не открыт")
        return int(self._helper().latency())

    def close(self):
        """Закрыть поток; повторный вызов безопасен."""
        if not self._opened:
            return False
        self._opened = False
        self._buffer = None
        self._mono = None
        self._helper().close()
        return True

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
