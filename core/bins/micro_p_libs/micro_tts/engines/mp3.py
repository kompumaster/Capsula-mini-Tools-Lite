"""Обёртка над libc_mp3.so для MicroPython `ffi`."""

from micro_tts.errors import TtsError

LIB = "/home/microp/micro_tts/bins/libc_mp3.so"


class Mp3Decoder:
    def __init__(self, path=LIB):
        try:
            import ffi
        except ImportError as exc:
            raise TtsError("нет ffi для MP3: {}".format(exc))
        self._ffi = ffi
        try:
            lib = ffi.open(str(path))
        except Exception as exc:
            raise TtsError("не открыть {}: {}".format(path, exc))
        self._open = lib.func("i", "mp3_open", "i")
        self._feed = lib.func("i", "mp3_feed", "pi")
        self._available = lib.func("i", "mp3_available", "")
        self._pcm = lib.func("p", "mp3_pcm", "")
        self._consume = lib.func("i", "mp3_consume", "i")
        self._rate = lib.func("i", "mp3_rate", "")
        self._channels = lib.func("i", "mp3_channels", "")
        self._error = lib.func("s", "mp3_error", "")
        self._close = lib.func("i", "mp3_close", "")
        self._opened = False

    def open(self, rate_hint=24000):
        if self._open(int(rate_hint)) != 0:
            raise TtsError("MP3: {}".format(self.error() or "open"))
        self._opened = True
        return self

    def feed(self, data):
        if not self._opened:
            raise TtsError("MP3: декодер не открыт")
        if not isinstance(data, (bytes, bytearray)):
            raise TtsError("MP3: нужны bytes")
        if self._feed(data, len(data)) != 0:
            raise TtsError("MP3: {}".format(self.error() or "feed"))

    def read(self, max_frames=4096):
        if not self._opened:
            raise TtsError("MP3: декодер не открыт")
        available = int(self._available())
        count = min(available, int(max_frames))
        if count <= 0:
            return b""
        pointer = self._pcm()
        if not pointer:
            return b""
        data = bytes(self._ffi.as_bytearray(pointer, count * 2))
        self._consume(count)
        return data

    def rate(self):
        return int(self._rate())

    def channels(self):
        return int(self._channels())

    def error(self):
        try:
            return self._error()
        except Exception:
            return ""

    def close(self):
        if self._opened:
            self._close()
            self._opened = False
