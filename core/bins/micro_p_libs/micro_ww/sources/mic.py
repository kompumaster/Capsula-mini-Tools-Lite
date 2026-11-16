"""Микрофон через `micro_hal`.

`micro_hal` импортируется только в `open()`. Источник отдаёт одно окно
моно-PCM (`s16le`, 16 кГц, 20 мс), как `micro_asr`:

- `mics` — захват `channels=1`, моно сводит Pulse;
- `speex` — готовый моно-поток после beamforming и AGC.
"""

from micro_ww.errors import WwError
from micro_ww.sources.base import Source

DEFAULT_SOURCE = "mics"
DEFAULT_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_WINDOW_MS = 20


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WwError("{} должен быть положительным целым".format(name))
    return value


def _source(value):
    if not isinstance(value, str) or not value.strip():
        raise WwError("source должен быть непустой строкой")
    return value.strip()


def _settle(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WwError("settle_ms должен быть целым неотрицательным")
    return value


class MicroHalMic(Source):
    """Звук с микрофонов колонки."""

    name = "micro_hal"

    def __init__(self, source=DEFAULT_SOURCE, window_ms=DEFAULT_WINDOW_MS,
                 settle_ms=None, stream=None, rate=DEFAULT_RATE,
                 channels=DEFAULT_CHANNELS):
        self.source = _source(source)
        self.window_ms = _positive_int(window_ms, "window_ms")
        self.settle_ms = _settle(settle_ms)
        self.rate = _positive_int(rate, "rate")
        if self.rate != DEFAULT_RATE:
            raise WwError("micro_ww работает только на 16 кГц")
        self.channels = _positive_int(channels, "channels")
        if self.channels > 4:
            raise WwError("channels не может быть больше 4")
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

    def open(self):
        if self._opened:
            raise WwError("микрофон уже открыт")
        if self._stream is None:
            self._ensure_pulse()
            try:
                from micro_hal import lib_mic
            except Exception as exc:
                raise WwError("micro_hal недоступен: {}".format(exc))
            options = {
                "source": self.source,
                "channels": self.channels,
                "rate": self.rate,
                "window_ms": self.window_ms,
            }
            if self.settle_ms is not None:
                options["settle_ms"] = self.settle_ms
            try:
                self._stream = lib_mic.MicStream(**options)
            except Exception as exc:
                raise WwError("микрофон: {}".format(exc))
        try:
            self._stream.open()
        except WwError:
            self._stream = None
            raise
        except Exception as exc:
            self._stream = None
            raise WwError("микрофон: {}".format(exc))
        self._opened = True
        return self

    def read(self):
        if not self._opened or self._stream is None:
            raise WwError("микрофон не открыт")
        try:
            data = self._stream.read()
        except WwError:
            raise
        except Exception as exc:
            raise WwError("микрофон: {}".format(exc))
        if not isinstance(data, (bytes, bytearray)):
            raise WwError("микрофон вернул не bytes")
        return bytes(data)

    def info(self):
        return {
            "name": self.name,
            "source": self.source,
            "rate": self.rate,
            "channels": self.channels,
            "window_ms": self.window_ms,
        }

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
