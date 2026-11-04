"""Динамик: воспроизведение через PulseAudio (`pacat`/`paplay`).

Только железо/звуковой стек: sink, команда, фоновый процесс, PID,
остановка. Тон, мелодии и WAV — в `lib_speaker`. `voice-agent`
владеет звуком, его останавливаем отдельно.

`paplay` на плате — симлинк на `pacat`: WAV играет по имени
`paplay`, сырой поток — `pacat --raw`.
"""

import os
import time

from micro_hal import hal_common, hal_volume
from micro_hal.hal_common import HalError

__all__ = [
    "PACAT", "PAPLAY", "PID_FILE", "ERR", "RAW", "SINK",
    "available", "sinks", "default_sink", "running", "play", "stop",
    "wait",
]

PACAT = "/usr/bin/pacat"
PAPLAY = "/usr/bin/paplay"
PCTL = "/usr/bin/pactl"
# Файлы состояния — на процесс: два скрипта не мешают друг другу.
_PID = hal_common.self_pid()
PID_FILE = "/tmp/micro_hal_spk.{}.pid".format(_PID)
ERR = "/tmp/micro_hal_spk.{}.err".format(_PID)
RAW = "/tmp/micro_hal_spk.{}.raw".format(_PID)
SINK = "master"

# Метка в cmdline: по ней находится осиротевший `pacat`/`paplay`.
CLIENT = "micro_hal-spk"


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


def _check_sink(sink):
    """Проверить имя sink и что он есть в Pulse."""
    sink = str(sink)
    if not sink:
        raise HalError("пустое имя sink")
    allowed = ("abcdefghijklmnopqrstuvwxyz"
               "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "0123456789_.-")
    for char in sink:
        if char not in allowed:
            raise HalError("неверное имя sink: {!r}".format(sink))
    names = sinks()
    if sink not in names:
        raise HalError("нет sink {} (есть: {})".format(
            sink, ", ".join(names)))
    return sink


def sinks():
    """Имена доступных sink'ов."""
    return hal_volume.sinks()


def default_sink():
    """Sink по умолчанию (обычно `master`)."""
    return hal_volume.default_sink()


def available(sink=SINK):
    """Есть ли `pacat` и указанный sink."""
    if not hal_common.exists(PACAT):
        return False
    try:
        _check_sink(sink)
    except HalError:
        return False
    return True


def _scan():
    """PID осиротевшего `pacat`/`paplay` micro_hal или None."""
    for pid, cmdline in hal_common.processes():
        if (CLIENT in cmdline
                and ("pacat" in cmdline or "paplay" in cmdline)
                and hal_common.stale_owner(pid, "micro_hal_spk.")):
            return pid
    return None


def running():
    """PID фонового `pacat`/`paplay` или None (включая осиротевший)."""
    pid = _read_pid()
    if pid is not None:
        if _alive(pid):
            try:
                cmdline = hal_common.read_text(
                    "/proc/{}/cmdline".format(pid)).replace("\x00", " ")
            except OSError:
                cmdline = ""
            if "pacat" in cmdline or "paplay" in cmdline:
                return pid
        _forget_pid()
    return _scan()


def play(path, sink=SINK, raw=False, rate=16000, channels=1,
         latency_msec=100):
    """Запустить воспроизведение в фоне; вернуть PID.

    `raw=True` — сырой поток `s16le` (`rate`/`channels`), иначе файл
    WAV. `path` не удаляется. Один процесс на всё: пока играет
    предыдущий, новый не запускается.
    """
    hal_common.require_va_stopped("динамик")
    sink = _check_sink(sink)
    text = str(path)
    if not hal_common.exists(text):
        raise HalError("нет файла {}".format(text))
    if running() is not None:
        raise HalError("уже играет")

    player = PACAT if raw else PAPLAY
    if not hal_common.exists(player):
        raise HalError("нет {}".format(player))
    options = ["--playback", "--device={}".format(_quote(sink))]
    options.append("--client-name={}".format(CLIENT))
    if raw:
        if int(rate) <= 0 or int(channels) <= 0:
            raise HalError("rate и channels должны быть больше нуля")
        options.append("--raw")
        options.append("--rate={}".format(int(rate)))
        options.append("--channels={}".format(int(channels)))
        options.append("--format=s16le")
    if latency_msec is not None:
        options.append("--latency-msec={}".format(int(latency_msec)))

    command = "{} {} < {} 2>{} & echo $! > {}".format(
        player, " ".join(options), _quote(text), _quote(ERR),
        _quote(PID_FILE))
    hal_common.run(command)
    time.sleep(0.05)

    pid = running()
    if pid is None:
        try:
            message = hal_common.read_text(ERR).strip()
        except OSError:
            message = ""
        if message:
            raise HalError("pacat: {}".format(message))
        # Короткий клип мог закончиться до проверки — это не ошибка.
        pid = _read_pid()
        if pid is None:
            raise HalError("pacat не запустился")
    return pid


def stop():
    """Остановить воспроизведение; True, если процесс был."""
    pid = running()
    if pid is None:
        _forget_pid()
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
    return True


def wait(timeout=10.0):
    """Ждать конца воспроизведения; True, если процесс ушёл.

    `timeout=None` — ждать без ограничения (для `wait=True`
    в `lib_speaker.play_wav`).
    """
    deadline = None if timeout is None else time.time() + float(timeout)
    while running() is not None:
        if deadline is not None and time.time() >= deadline:
            return False
        time.sleep(0.02)
    _forget_pid()
    return True
