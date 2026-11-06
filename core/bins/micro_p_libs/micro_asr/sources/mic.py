"""Микрофон через `micro_hal`.

`micro_hal` импортируется только в `open()`, чтобы импорт пакета не
трогал железо. `read()` возвращает одно окно моно-PCM (`s16le`,
16 кГц, 20 мс) — ровно то, что ждёт VAD.
"""

from micro_asr.errors import AsrError

DEFAULT_WINDOW_MS = 20
DEFAULT_RATE = 16000


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AsrError("{} должен быть положительным целым".format(name))
    return value


class MicroHalMic:
    """Источник звука с микрофонов колонки."""

    name = "micro_hal"

    def __init__(self, source=None, window_ms=DEFAULT_WINDOW_MS,
                 settle_ms=None, stream=None):
        self.source = source
        self.window_ms = _positive_int(window_ms, "window_ms")
        if settle_ms is not None:
            if (isinstance(settle_ms, bool)
                    or not isinstance(settle_ms, int) or settle_ms < 0):
                raise AsrError(
                    "settle_ms должен быть целым неотрицательным")
        self.settle_ms = settle_ms
        self._stream = stream
        self._opened = False

    def _ensure_pulse(self):
        """C-клиенту нужен PULSE_SERVER: берём сокет у `hal_pulse`."""
        try:
            import os
        except ImportError:
            return
        try:
            if os.getenv("PULSE_SERVER"):
                return
            from micro_hal import hal_pulse
            server = hal_pulse.server()
            if server:
                os.putenv("PULSE_SERVER", server)
        except Exception:
            return

    def open(self, rate=DEFAULT_RATE, channels=1):
        rate = _positive_int(rate, "rate")
        channels = _positive_int(channels, "channels")
        if channels > 4:
            raise AsrError("channels не может быть больше 4")
        if self._stream is None:
            self._ensure_pulse()
            try:
                from micro_hal import lib_mic
            except Exception as exc:
                raise AsrError("micro_hal недоступен: {}".format(exc))
            options = {
                "channels": channels,
                "rate": rate,
                "window_ms": self.window_ms,
            }
            if self.source is not None:
                options["source"] = self.source
            if self.settle_ms is not None:
                options["settle_ms"] = self.settle_ms
            try:
                self._stream = lib_mic.MicStream(**options)
            except Exception as exc:
                raise AsrError("микрофон: {}".format(exc))
        try:
            self._stream.open()
        except AsrError:
            self._stream = None
            raise
        except Exception as exc:
            self._stream = None
            raise AsrError("микрофон: {}".format(exc))
        self._opened = True
        return self

    def read(self, size=None):
        """Одно окно моно-PCM; `size` — подсказка, окно фиксировано."""
        if not self._opened or self._stream is None:
            raise AsrError("микрофон не открыт")
        try:
            data = self._stream.read()
        except AsrError:
            raise
        except Exception as exc:
            raise AsrError("микрофон: {}".format(exc))
        if not isinstance(data, (bytes, bytearray)):
            raise AsrError("микрофон вернул не bytes")
        return bytes(data)

    def close(self):
        stream = self._stream
        self._stream = None
        self._opened = False
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
        return True
