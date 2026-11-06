"""Детектор речи и тишины по энергии сигнала.

Порог фиксированный (по умолчанию −45 dBFS): простое и предсказуемое
поведение без калибровки по шуму. Порог можно задать параметром
`threshold_db`.

Работает с моно-PCM `s16le` кусками. Не трогает железо и время:
длительность считается по числу принятых сэмплов, поэтому поведение
детерминировано и проверяется на хосте.

Сценарий:

```text
waiting --речь--> speech --тишина N секунд--> silence
   |                 |
   +-- start_timeout +-- max_seconds
```

`feed()` возвращает `True`, пока нужно продолжать запись.
"""

import math
import struct

from micro_asr import audio
from micro_asr.errors import AsrError

DEFAULT_RATE = 16000
DEFAULT_WINDOW_MS = 20
DEFAULT_SILENCE = 0.8
DEFAULT_START_TIMEOUT = 5.0
DEFAULT_MAX_SECONDS = 25.0
DEFAULT_MIN_SPEECH = 0.3
DEFAULT_THRESHOLD_DB = -45.0

MIN_DB = -120.0

FULL_SCALE = 32768.0


def _number(value, name, low, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AsrError("{} должен быть числом".format(name))
    value = float(value)
    if value < low:
        raise AsrError("{} должен быть не меньше {}".format(name, low))
    if high is not None and value > high:
        raise AsrError("{} должен быть не больше {}".format(name, high))
    return value


def _integer(value, name, low, high=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AsrError("{} должен быть целым числом".format(name))
    if value < low:
        raise AsrError("{} должен быть не меньше {}".format(name, low))
    if high is not None and value > high:
        raise AsrError("{} должен быть не больше {}".format(name, high))
    return value


def rms(pcm):
    """Среднеквадратичное значение сэмплов `s16le`."""
    audio.validate_pcm(pcm)
    if not pcm:
        return 0.0
    count = len(pcm) // 2
    samples = struct.unpack("<{}h".format(count), bytes(pcm))
    total = 0
    for value in samples:
        total += value * value
    return math.sqrt(total / float(count))


def dbfs(pcm):
    """Уровень сигнала в dBFS (тишина — `MIN_DB`)."""
    value = rms(pcm)
    if value <= 0:
        return MIN_DB
    return 20.0 * math.log10(value / FULL_SCALE)


class SpeechDetector:
    """Определяет конец фразы по тишине."""

    def __init__(self, rate=DEFAULT_RATE, window_ms=DEFAULT_WINDOW_MS,
                 silence=DEFAULT_SILENCE,
                 start_timeout=DEFAULT_START_TIMEOUT,
                 max_seconds=DEFAULT_MAX_SECONDS,
                 min_speech=DEFAULT_MIN_SPEECH,
                 threshold_db=DEFAULT_THRESHOLD_DB):
        self.rate = _integer(rate, "rate", 1, 48000)
        window_ms = _integer(window_ms, "window_ms", 1, 1000)
        self._window_samples = int(self.rate * window_ms / 1000)
        if self._window_samples < 1:
            self._window_samples = 1
        self._window_bytes = self._window_samples * 2
        self._window_seconds = self._window_samples / float(self.rate)
        self.silence = _number(silence, "silence", 0.01)
        self.start_timeout = _number(start_timeout, "start_timeout", 0)
        self.max_seconds = _number(max_seconds, "max_seconds", 0.01)
        self.min_speech = _number(min_speech, "min_speech", 0.01)
        if threshold_db is None:
            threshold_db = DEFAULT_THRESHOLD_DB
        self._threshold = _number(threshold_db, "threshold_db", MIN_DB, 0)
        self.reset()

    def reset(self):
        """Начать новую фразу."""
        self._buffer = bytearray()
        self._elapsed = 0.0
        self._speech_seconds = 0.0
        self._silence_run = 0.0
        self._state = "waiting"
        self._finished = False

    @property
    def finished(self):
        return self._finished

    @property
    def state(self):
        return self._state

    @property
    def speech(self):
        return self._speech_seconds >= self.min_speech

    @property
    def elapsed(self):
        return self._elapsed

    @property
    def speech_seconds(self):
        return self._speech_seconds

    @property
    def threshold(self):
        return self._threshold

    def feed(self, pcm):
        """Добавить кусок PCM; `True` — запись продолжается."""
        if self._finished:
            return False
        audio.validate_pcm(pcm)
        self._buffer.extend(pcm)
        offset = 0
        while len(self._buffer) - offset >= self._window_bytes:
            window = self._buffer[offset:offset + self._window_bytes]
            offset += self._window_bytes
            self._step(window, self._window_seconds)
            if self._finished:
                break
        if offset:
            # MicroPython не умеет del у bytearray — берём остаток срезом.
            self._buffer = self._buffer[offset:]
        return not self._finished

    def finish(self):
        """Завершить запись: остаток буфера считается последним окном."""
        if self._finished:
            return self._state
        if self._buffer:
            window = bytes(self._buffer)
            self._buffer = bytearray()
            seconds = (len(window) // 2) / float(self.rate)
            self._step(window, seconds)
        self._finished = True
        return self._state

    def _step(self, window, seconds):
        level = dbfs(window)
        self._elapsed += seconds
        if self._state == "waiting":
            if level >= self._threshold:
                self._state = "speech"
                self._speech_seconds += seconds
                self._silence_run = 0.0
            elif self._elapsed >= self.start_timeout:
                self._finished = True
        elif self._state == "speech":
            if level >= self._threshold:
                self._speech_seconds += seconds
                self._silence_run = 0.0
            else:
                self._silence_run += seconds
                if self._silence_run >= self.silence:
                    self._state = "silence"
                    self._finished = True
        if self._elapsed >= self.max_seconds:
            self._finished = True
