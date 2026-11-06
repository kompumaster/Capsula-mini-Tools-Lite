"""Динамик: тон, тишина и мелодии поверх `hal_speaker`.

Только логика: синус, огибающая, склейка нот и запись во временный
raw. Процесс, PID и остановка — в `hal_speaker`; громкость —
в `lib_volume`.
"""

import math
import os
import struct

from micro_hal import hal_common, hal_speaker, lib_volume, lib_wav
from micro_hal.hal_common import HalError

__all__ = [
    "RATE", "CHANNELS", "WIDTH", "AMPLITUDE", "FADE_MS", "RAW", "LIB",
    "PCM_RATE",
    "tone_pcm", "melody_pcm", "helper",
    "tone", "silence", "melody", "play_wav", "stop", "playing",
    "play_pcm", "play_raw", "stream", "write_wav",
    "get_volume", "set_volume", "mute", "toggle_mute",
    "pause", "resume", "paused", "wait",
]

RATE = 16000
PCM_RATE = 24000
CHANNELS = 1
WIDTH = 2
AMPLITUDE = 0.3
FADE_MS = 10

RAW = "/tmp/micro_hal_speaker.{}.raw".format(hal_common.self_pid())
LIB = "/home/microp/micro_hal/bins/libc_speaker.so"

_PACK = 512


def _check(freq, seconds, amplitude):
    freq = float(freq)
    seconds = float(seconds)
    amplitude = float(amplitude)
    if freq < 0 or freq >= RATE / 2.0:
        raise HalError("частота вне 0…{} Гц: {}".format(RATE // 2, freq))
    if seconds <= 0:
        raise HalError("длительность должна быть больше нуля")
    if amplitude < 0 or amplitude > 1:
        raise HalError("амплитуда должна быть в 0…1")
    return freq, seconds, amplitude


def _fade(frames, fade_frames):
    """Длина линейной огибающей в кадрах или None, если она не нужна."""
    if fade_frames <= 0 or frames <= 0:
        return None
    fade_frames = min(int(fade_frames), frames // 2)
    if fade_frames <= 0:
        return None
    return fade_frames


class _SpeakerLibrary:
    """Обёртка над `libc_speaker.so`; в тестах подменяется."""

    def __init__(self, path=LIB):
        import ffi

        self._ffi = ffi
        lib = ffi.open(str(path))
        self._tone = lib.func("i", "spk_tone", "iiiii")
        self._zero = lib.func("i", "spk_zero", "i")
        self._buffer = lib.func("p", "spk_buffer", "")
        self._frames = lib.func("i", "spk_frames", "")
        self._errno = lib.func("i", "spk_errno", "")

    def tone(self, rate, freq_millihz, frames, amplitude, fade_frames):
        return self._tone(int(rate), int(freq_millihz), int(frames),
                          int(amplitude), int(fade_frames))

    def zero(self, frames):
        return self._zero(int(frames))

    def view(self, size):
        return self._ffi.as_bytearray(self._buffer(), int(size))

    def frames(self):
        return self._frames()

    def error(self):
        return "spk errno {}".format(self._errno())


_HELPER = False


def helper(path=LIB):
    """Загрузить C-генератор; `None`, если библиотеки нет.

    Неудачу не кэшируем: если библиотеку поставили позже, следующий
    вызов попробует снова (повторная попытка — только при ошибке).
    """
    global _HELPER
    if _HELPER is False:
        try:
            _HELPER = _SpeakerLibrary(path)
        except (OSError, ImportError):
            return None
    return _HELPER


def _tone_python(freq, seconds, amplitude=AMPLITUDE, fade_ms=FADE_MS,
                 rate=RATE):
    """Синус на чистом Python — запасной путь и эталон."""
    freq, seconds, amplitude = _check(freq, seconds, amplitude)
    rate = int(rate)
    frames = int(rate * seconds)
    if frames <= 0:
        raise HalError("слишком короткий тон")
    fade = _fade(frames, int(rate * float(fade_ms) / 1000.0))
    level = float(int(amplitude * 32767.0))
    step = 2.0 * math.pi * freq / rate
    out = bytearray()
    buffer = []
    for index in range(frames):
        value = level * math.sin(step * index)
        if fade:
            if index < fade:
                value *= index / fade
            elif index >= frames - fade:
                value *= (frames - 1 - index) / fade
        buffer.append(int(value))
        if len(buffer) == _PACK:
            out += struct.pack("<%dh" % _PACK, *buffer)
            buffer = []
    if buffer:
        out += struct.pack("<%dh" % len(buffer), *buffer)
    return bytes(out)


def tone_pcm(freq, seconds, amplitude=AMPLITUDE, fade_ms=FADE_MS,
             rate=RATE):
    """Синус в `s16le`; `freq=0` — тишина. На краях — огибающая."""
    freq, seconds, amplitude = _check(freq, seconds, amplitude)
    rate = int(rate)
    frames = int(rate * seconds)
    if frames <= 0:
        raise HalError("слишком короткий тон")
    lib = helper()
    if lib is None:
        return _tone_python(freq, seconds, amplitude, fade_ms, rate)
    fade = int(rate * float(fade_ms) / 1000.0)
    level = int(amplitude * 32767.0)
    if freq == 0:
        count = lib.zero(frames)
    else:
        count = lib.tone(rate, int(freq * 1000), frames, level, fade)
    if count < 0:
        raise HalError("генератор тона: {}".format(lib.error()))
    return bytes(lib.view(count * 2))


def melody_pcm(notes, amplitude=AMPLITUDE, fade_ms=FADE_MS, rate=RATE):
    """Мелодия `[(freq, ms), …]`; `freq=0` — пауза."""
    out = bytearray()
    if not notes:
        raise HalError("пустая мелодия")
    for freq, milliseconds in notes:
        milliseconds = float(milliseconds)
        if milliseconds <= 0:
            raise HalError("длительность ноты должна быть больше нуля")
        out += tone_pcm(freq, milliseconds / 1000.0, amplitude,
                        fade_ms, rate)
    return bytes(out)


def _write(path, data):
    handle = open(path, "wb")
    try:
        handle.write(data)
    finally:
        handle.close()
    return path


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _play_raw(data, path, sink, wait_seconds, wait, rate=RATE,
              channels=CHANNELS):
    """Записать raw, проиграть и убрать временный файл.

    При ошибке `play`/`wait` временный raw тоже удаляется, чтобы не
    оставлять мусор в `/tmp`.
    """
    _write(path, data)
    try:
        hal_speaker.play(path, sink=sink, raw=True, rate=rate,
                         channels=channels)
        if wait:
            hal_speaker.wait(wait_seconds)
    except Exception:
        if path == RAW:
            _remove(path)
        raise
    if wait and path == RAW:
        _remove(path)
    return path


def tone(freq, seconds, sink=hal_speaker.SINK, amplitude=AMPLITUDE,
         fade_ms=FADE_MS, wait=True, path=None):
    """Сыграть тон; вернуть путь к raw-файлу."""
    data = tone_pcm(freq, seconds, amplitude, fade_ms)
    path = RAW if path is None else str(path)
    return _play_raw(data, path, sink, float(seconds) + 3.0, wait)


def silence(seconds, sink=hal_speaker.SINK, wait=True, path=None):
    """Сыграть тишину (пауза); вернуть путь к raw-файлу."""
    return tone(0, seconds, sink=sink, amplitude=0, wait=wait,
                path=path)


def melody(notes, sink=hal_speaker.SINK, amplitude=AMPLITUDE,
           fade_ms=FADE_MS, wait=True, path=None):
    """Сыграть мелодию; вернуть путь к raw-файлу."""
    data = melody_pcm(notes, amplitude, fade_ms)
    path = RAW if path is None else str(path)
    seconds = sum(float(milliseconds) for _freq, milliseconds in notes) / 1000.0
    return _play_raw(data, path, sink, seconds + 3.0, wait)


def play_wav(path, sink=hal_speaker.SINK, wait=False):
    """Сыграть готовый WAV через `paplay`.

    `wait=True` — блокироваться до конца воспроизведения (любая
    длительность, без таймаута).
    """
    pid = hal_speaker.play(str(path), sink=sink, raw=False)
    if wait:
        hal_speaker.wait(None)
    return pid


def stop():
    """Остановить воспроизведение; True, если что-то играло.

    Заодно убирает временный raw процесса (`tone(wait=False)` и
    `play_pcm(wait=False)` его оставляют).
    """
    result = hal_speaker.stop()
    _remove(RAW)
    return result


def playing():
    """PID текущего воспроизведения или None."""
    return hal_speaker.running()


def wait(timeout=10.0):
    """Дождаться конца воспроизведения; True, если процесс ушёл."""
    return hal_speaker.wait(timeout)


# --- PCM из памяти, файлы и поток -----------------------------------

def _sink_value(sink):
    return hal_speaker.SINK if sink is None else sink


def play_pcm(pcm, rate=PCM_RATE, channels=CHANNELS, sink=None,
             wait=False):
    """Сыграть PCM `s16le` из памяти; вернуть путь к raw-файлу.

    Данные пишутся во временный файл процесса; при `wait=False` он
    остаётся до следующего вызова или `stop()`.
    """
    if not isinstance(pcm, (bytes, bytearray)):
        raise HalError("нужны bytes")
    if len(pcm) % 2 != 0:
        raise HalError("PCM должен быть кратен 2 байтам")
    rate = int(rate)
    channels = int(channels)
    if rate <= 0 or channels <= 0:
        raise HalError("rate и channels должны быть больше нуля")
    seconds = len(pcm) / float(rate * channels * WIDTH)
    return _play_raw(bytes(pcm), RAW, _sink_value(sink),
                     seconds + 3.0, wait, rate, channels)


def play_raw(path, rate=PCM_RATE, channels=CHANNELS, sink=None,
             wait=False):
    """Сыграть готовый файл `s16le`; вернуть PID."""
    pid = hal_speaker.play(str(path), sink=_sink_value(sink), raw=True,
                           rate=int(rate), channels=int(channels))
    if wait:
        hal_speaker.wait(None)
    return pid


def stream(sink=None, rate=PCM_RATE, channels=CHANNELS,
           latency_msec=100):
    """Поток PCM: объект `hal_speaker.Stream` (открывается вызывающим)."""
    return hal_speaker.Stream(sink=_sink_value(sink), rate=int(rate),
                              channels=int(channels),
                              latency_msec=latency_msec)


def write_wav(path, pcm, rate=PCM_RATE, channels=CHANNELS):
    """Записать PCM в WAV; вернуть путь."""
    data = bytes(pcm)
    channels = int(channels)
    rate = int(rate)
    if len(data) % (WIDTH * channels) != 0:
        raise HalError("PCM не делится на кадры")
    header = lib_wav.wav_header(len(data), channels, rate, WIDTH)
    handle = open(path, "wb")
    try:
        handle.write(header + data)
    finally:
        handle.close()
    return path


# --- громкость и пауза ----------------------------------------------

def get_volume(sink=hal_speaker.SINK):
    """Громкость sink в процентах."""
    return lib_volume.Volume(_sink_value(sink)).get()


def set_volume(value, sink=hal_speaker.SINK):
    """Поставить громкость 0…100; вернуть значение."""
    return lib_volume.Volume(_sink_value(sink)).set(value)


def mute(on=True, sink=hal_speaker.SINK):
    """Заглушить (`on=True`) или включить звук."""
    volume = lib_volume.Volume(_sink_value(sink))
    return volume.mute() if on else volume.unmute()


def toggle_mute(sink=hal_speaker.SINK):
    """Переключить mute; вернуть новое состояние."""
    return lib_volume.Volume(_sink_value(sink)).toggle()


def pause():
    """Пауза текущего воспроизведения (весь sink)."""
    return hal_speaker.pause()


def resume():
    """Продолжить воспроизведение."""
    return hal_speaker.resume()


def paused():
    """Стоит ли воспроизведение на паузе."""
    return hal_speaker.paused()
