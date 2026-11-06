"""Динамик: воспроизведение через PulseAudio (`pacat`/`paplay`).

Только железо/звуковой стек: sink, команда, фоновый процесс, PID,
остановка. Тон, мелодии и WAV — в `lib_speaker`. `voice-agent`
владеет звуком, его останавливаем отдельно.

`paplay` на плате — симлинк на `pacat`: WAV играет по имени
`paplay`, сырой поток — `pacat --raw`.
"""

import os
import time

from micro_hal import hal_common, hal_pulse, hal_volume
from micro_hal.hal_common import HalError

__all__ = [
    "PACAT", "PAPLAY", "PID_FILE", "ERR", "RAW", "FIFO", "SINK",
    "available", "sinks", "default_sink", "running", "play", "stop",
    "wait", "pause", "resume", "paused", "Stream",
]

PACAT = "/usr/bin/pacat"
PAPLAY = "/usr/bin/paplay"
PCTL = "/usr/bin/pactl"
# Файлы состояния — на процесс: два скрипта не мешают друг другу.
_PID = hal_common.self_pid()
PID_FILE = "/tmp/micro_hal_spk.{}.pid".format(_PID)
ERR = "/tmp/micro_hal_spk.{}.err".format(_PID)
RAW = "/tmp/micro_hal_spk.{}.raw".format(_PID)
FIFO = "/tmp/micro_hal_spk.{}.fifo".format(_PID)
SINK = "master"

# Метка в cmdline: по ней находится осиротевший `pacat`/`paplay`.
CLIENT = "micro_hal-spk"

# Текущий sink и признак паузы: пауза — `pactl suspend-sink`
# (в pactl 16.1 нет `suspend-sink-input`).
_ACTIVE_SINK = SINK
_PAUSED = False


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


def _cmdline(pid):
    try:
        return hal_common.read_text(
            "/proc/{}/cmdline".format(pid)).replace("\x00", " ")
    except OSError:
        return ""


def _is_player(pid):
    """`pacat`/`paplay` ли это; пустой cmdline — окно exec."""
    cmdline = _cmdline(pid)
    if cmdline:
        return "pacat" in cmdline or "paplay" in cmdline
    for _attempt in range(5):
        time.sleep(0.02)
        cmdline = _cmdline(pid)
        if cmdline:
            return "pacat" in cmdline or "paplay" in cmdline
    return False


def running():
    """PID фонового `pacat`/`paplay` или None (включая осиротевший)."""
    pid = _read_pid()
    if pid is not None:
        if _alive(pid) and _is_player(pid):
            return pid
        _forget_pid()
    return _scan()


def _options(sink, raw=False, rate=16000, channels=1, latency_msec=100):
    """Аргументы `pacat`/`paplay`."""
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
    return options


def _command(player, options, source):
    """Команда фонового процесса с источником (`файл` или FIFO)."""
    return hal_pulse.prefix() + "{} {} < {} 2>{} & echo $! > {}".format(
        player, " ".join(options), _quote(source), _quote(ERR),
        _quote(PID_FILE))


def _error_text():
    try:
        return hal_common.read_text(ERR).strip()
    except OSError:
        return ""


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
    global _ACTIVE_SINK, _PAUSED
    _ACTIVE_SINK = sink
    _PAUSED = False

    player = PACAT if raw else PAPLAY
    if not hal_common.exists(player):
        raise HalError("нет {}".format(player))
    options = _options(sink, raw, rate, channels, latency_msec)

    hal_common.run(_command(player, options, text))
    time.sleep(0.05)

    pid = running()
    if pid is None:
        message = _error_text()
        if message:
            raise HalError("pacat: {}".format(message))
        # Короткий клип мог закончиться до проверки — это не ошибка.
        pid = _read_pid()
        if pid is None:
            raise HalError("pacat не запустился")
    return pid


def _halt():
    """Оборвать текущий процесс; True, если он был."""
    global _PAUSED
    _PAUSED = False
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


def stop():
    """Остановить воспроизведение; True, если процесс был."""
    return _halt()


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


# --- пауза ----------------------------------------------------------

def _suspend_sink(sink, suspend):
    """Приостановить/продолжить sink; True при успехе."""
    code, _text = hal_common.capture(
        "{} suspend-sink {} {}".format(
            hal_pulse.prefix() + PCTL, _quote(sink),
            1 if suspend else 0))
    return code == 0


def pause():
    """Приостановить воспроизведение; True при успехе.

    Пауза — на уровне sink (`pactl suspend-sink`): в pactl 16.1 нет
    `suspend-sink-input`. Sink запоминается при `play()` и
    `Stream.open()`.
    """
    global _PAUSED
    if running() is None or _PAUSED:
        return False
    if not _suspend_sink(_ACTIVE_SINK, True):
        return False
    _PAUSED = True
    return True


def resume():
    """Продолжить воспроизведение; True при успехе."""
    global _PAUSED
    if running() is None or not _PAUSED:
        return False
    if not _suspend_sink(_ACTIVE_SINK, False):
        return False
    _PAUSED = False
    return True


def paused():
    """Стоит ли воспроизведение на паузе."""
    return _PAUSED and running() is not None


# --- поток PCM ------------------------------------------------------

def _remove_fifo():
    try:
        os.remove(FIFO)
    except OSError:
        pass


def _open_fifo():
    """Открыть FIFO на чтение и запись, чтобы `open()` не блокировался."""
    return open(FIFO, "r+b")


class Stream:
    """Поток PCM `s16le` в `pacat` через FIFO.

    `write()` блокируется, когда Pulse не успевает: память ограничена
    буфером FIFO, длительность значения не имеет. Один поток на
    процесс: пока играет файл или другой поток, `open()` даёт
    `HalError`. Пауза — общая, `hal_speaker.pause()`.
    """

    def __init__(self, sink=SINK, rate=24000, channels=1,
                 latency_msec=100):
        self.sink = str(sink)
        self.rate = int(rate)
        self.channels = int(channels)
        self.latency_msec = latency_msec
        self._handle = None
        self._pid = None
        self._opened = False

    def open(self):
        """Создать FIFO и запустить `pacat`; вернуть себя."""
        global _ACTIVE_SINK, _PAUSED
        hal_common.require_va_stopped("динамик")
        sink = _check_sink(self.sink)
        if running() is not None:
            raise HalError("уже играет")
        if not hal_common.exists(PACAT):
            raise HalError("нет {}".format(PACAT))
        if self.rate <= 0 or self.channels <= 0:
            raise HalError("rate и channels должны быть больше нуля")

        _ACTIVE_SINK = sink
        _PAUSED = False

        _remove_fifo()
        if hal_common.run("mkfifo {}".format(_quote(FIFO))) != 0:
            raise HalError("не создать FIFO {}".format(FIFO))

        options = _options(sink, True, self.rate, self.channels,
                           self.latency_msec)
        try:
            # Сначала процесс, потом FIFO: иначе `pacat` наследует
            # наш дескриптор и сам держит FIFO открытым на запись,
            # поэтому EOF не приходит и процесс не завершается.
            self._start_process(options)
            self._attach_fifo()
            if running() is None:
                message = _error_text()
                raise HalError(
                    "pacat: {}".format(message) if message
                    else "pacat завершился")
        except Exception:
            self._shutdown()
            raise
        self._opened = True
        return self

    def _start_process(self, options):
        """Запустить `pacat`; он ждёт открытия FIFO на запись."""
        hal_common.run(_command(PACAT, options, FIFO))
        time.sleep(0.05)
        pid = running()
        if pid is None:
            message = _error_text()
            raise HalError(
                "pacat: {}".format(message) if message
                else "pacat не запустился")
        self._pid = pid

    def _attach_fifo(self):
        """Открыть FIFO: это разблокирует `pacat`."""
        try:
            self._handle = _open_fifo()
        except OSError as exc:
            raise HalError("не открыть FIFO: {}".format(exc))

    def write(self, pcm):
        """Записать кусок PCM; вернуть число байт."""
        if not self._opened:
            raise HalError("поток не открыт")
        if not isinstance(pcm, (bytes, bytearray)):
            raise HalError("нужны bytes")
        if len(pcm) % 2 != 0:
            raise HalError("PCM должен быть кратен 2 байтам")
        if running() is None:
            raise HalError("поток закрыт: pacat завершился")
        try:
            written = self._handle.write(bytes(pcm))
        except OSError as exc:
            raise HalError("поток: {}".format(exc))
        return len(pcm) if written is None else written

    def running(self):
        return self._opened and running() is not None

    def pid(self):
        return self._pid

    def _shutdown(self):
        handle = self._handle
        self._handle = None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if running() is not None:
            _halt()
        _remove_fifo()
        self._pid = None

    def close(self):
        """Закрыть FIFO и дождаться слива; повторный вызов безопасен."""
        if not self._opened:
            return False
        self._opened = False
        handle = self._handle
        self._handle = None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if not wait(5.0):
            _halt()
        _remove_fifo()
        self._pid = None
        global _PAUSED
        _PAUSED = False
        return True

    def stop(self):
        """Оборвать поток; True, если он был открыт."""
        if not self._opened:
            return False
        self._opened = False
        self._shutdown()
        global _PAUSED
        _PAUSED = False
        return True

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
