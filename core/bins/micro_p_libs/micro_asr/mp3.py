"""MP3-декодер: `ffi` на MicroPython, `ctypes` на CPython.

Библиотека `libc_mp3.so` лежит в `bins/` рядом с пакетом. В C-коде
состояние статическое: один декодер на загруженную библиотеку. Две
разные копии `.so` (разные файлы) дают независимые декодеры.
"""

from micro_asr.errors import AsrError

DEFAULT_RATE_HINT = 24000
READ_FRAMES = 4096


def _package_dir():
    path = __file__
    index = max(path.rfind("/"), path.rfind("\\"))
    return path[:index] if index >= 0 else "."


DEFAULT_LIB = _package_dir() + "/bins/libc_mp3.so"


class Mp3Decoder:
    """Обёртка над `libc_mp3.so`."""

    def __init__(self, path=None, lib=None):
        self.path = str(path or DEFAULT_LIB)
        self._lib = lib
        self._backend = None
        self._opened = False
        if lib is None:
            self._load()

    def _load(self):
        try:
            import ffi
        except ImportError:
            ffi = None
        if ffi is not None:
            self._load_ffi(ffi)
        else:
            self._load_ctypes()

    def _load_ffi(self, ffi):
        try:
            lib = ffi.open(self.path)
        except Exception as exc:
            raise AsrError("не открыть {}: {}".format(self.path, exc))
        self._ffi = ffi
        self._lib = lib
        self._open = lib.func("i", "mp3_open", "i")
        self._feed = lib.func("i", "mp3_feed", "pi")
        self._available = lib.func("i", "mp3_available", "")
        self._pcm = lib.func("p", "mp3_pcm", "")
        self._consume = lib.func("i", "mp3_consume", "i")
        self._rate = lib.func("i", "mp3_rate", "")
        self._channels = lib.func("i", "mp3_channels", "")
        self._error = lib.func("s", "mp3_error", "")
        self._close = lib.func("i", "mp3_close", "")
        self._backend = "ffi"

    def _load_ctypes(self):
        try:
            import ctypes
        except ImportError as exc:
            raise AsrError("нет ctypes/ffi для MP3: {}".format(exc))
        try:
            lib = ctypes.CDLL(self.path)
        except OSError as exc:
            raise AsrError("не открыть {}: {}".format(self.path, exc))
        lib.mp3_open.argtypes = [ctypes.c_int]
        lib.mp3_open.restype = ctypes.c_int
        lib.mp3_feed.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.mp3_feed.restype = ctypes.c_int
        lib.mp3_available.restype = ctypes.c_int
        lib.mp3_pcm.restype = ctypes.c_void_p
        lib.mp3_consume.argtypes = [ctypes.c_int]
        lib.mp3_consume.restype = ctypes.c_int
        lib.mp3_rate.restype = ctypes.c_int
        lib.mp3_channels.restype = ctypes.c_int
        lib.mp3_error.restype = ctypes.c_char_p
        lib.mp3_close.restype = None
        self._ctypes = ctypes
        self._lib = lib
        self._open = lib.mp3_open
        self._feed = lib.mp3_feed
        self._available = lib.mp3_available
        self._pcm = lib.mp3_pcm
        self._consume = lib.mp3_consume
        self._rate = lib.mp3_rate
        self._channels = lib.mp3_channels
        self._error = lib.mp3_error
        self._close = lib.mp3_close
        self._backend = "ctypes"

    def open(self, rate_hint=DEFAULT_RATE_HINT):
        if self._open(int(rate_hint)) != 0:
            raise AsrError("MP3: {}".format(self.error() or "open"))
        self._opened = True
        return self

    def feed(self, data):
        if not self._opened:
            raise AsrError("MP3: декодер не открыт")
        if not isinstance(data, (bytes, bytearray)):
            raise AsrError("MP3: нужны bytes")
        if self._feed(bytes(data), len(data)) != 0:
            raise AsrError("MP3: {}".format(self.error() or "feed"))

    def read(self, max_frames=READ_FRAMES):
        if not self._opened:
            raise AsrError("MP3: декодер не открыт")
        available = int(self._available())
        count = min(available, int(max_frames))
        if count <= 0:
            return b""
        pointer = self._pcm()
        if not pointer:
            return b""
        if self._backend == "ffi":
            data = bytes(self._ffi.as_bytearray(pointer, count * 2))
        else:
            data = self._ctypes.string_at(pointer, count * 2)
        self._consume(count)
        return data

    def rate(self):
        return int(self._rate())

    def channels(self):
        return int(self._channels())

    def error(self):
        try:
            value = self._error()
        except Exception:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return value or ""

    def close(self):
        if self._opened:
            try:
                self._close()
            except Exception:
                pass
            self._opened = False
        return True


def decode(data, rate_hint=DEFAULT_RATE_HINT, decoder=None):
    """MP3-байты → `(pcm, rate, channels)`; моно `s16le`."""
    if decoder is None:
        decoder = Mp3Decoder()
    try:
        decoder.open(rate_hint)
        decoder.feed(data)
        output = bytearray()
        while True:
            chunk = decoder.read(READ_FRAMES)
            if not chunk:
                break
            output.extend(chunk)
        rate = decoder.rate()
        channels = decoder.channels()
    finally:
        decoder.close()
    if not output:
        raise AsrError("MP3: нет аудио")
    return bytes(output), rate, channels


def decode_file(path, rate_hint=DEFAULT_RATE_HINT, decoder=None):
    """MP3-файл → `(pcm, rate, channels)`."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise AsrError("не прочитать {}: {}".format(path, exc))
    return decode(data, rate_hint, decoder)
