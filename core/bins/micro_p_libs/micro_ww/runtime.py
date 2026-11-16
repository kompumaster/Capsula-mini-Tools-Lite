"""Обёртка над `libc_ww.so`: `ffi` на колонке, `ctypes` на хосте.

Библиотека возвращает вероятности 0…255; здесь они приводятся к
0.0…1.0. Состояние потока и препроцессор живут внутри C-рантайма.
"""

from micro_ww.errors import WwError

MAX_PROBS = 16


def _package_dir():
    path = __file__
    index = max(path.rfind("/"), path.rfind("\\"))
    return path[:index] if index >= 0 else "."


def _exists(path):
    import os
    try:
        os.stat(path)
    except OSError:
        return False
    return True


def default_library():
    """`bins/libc_ww.so`; на хосте - `_tmp/libc_ww_host.so`, если есть."""
    base = _package_dir()
    host = base + "/_tmp/libc_ww_host.so"
    try:
        import ctypes  # noqa: F401
    except ImportError:
        return base + "/bins/libc_ww.so"
    return host if _exists(host) else base + "/bins/libc_ww.so"


class Runtime:
    """Один открытый экземпляр C-рантайма."""

    def __init__(self, path=None):
        self.path = str(path or default_library())
        self._lib = None
        self._backend = None
        self._opened = False
        self._load()

    def _load(self):
        try:
            import ffi  # noqa: F401
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
            raise WwError("не открыть {}: {}".format(self.path, exc))
        self._ffi = ffi
        self._lib = lib
        self._open = lib.func("i", "ww_open", "sii")
        self._push = lib.func("i", "ww_push", "pi")
        self._read = lib.func("i", "ww_read_probs", "pi")
        self._reset = lib.func("i", "ww_reset", "")
        self._close = lib.func("i", "ww_close", "")
        self._arena = lib.func("i", "ww_arena_used", "")
        self._error = lib.func("s", "ww_error", "")
        self._backend = "ffi"

    def _load_ctypes(self):
        try:
            import ctypes
        except ImportError as exc:
            raise WwError("нет ffi/ctypes для C-рантайма: {}".format(exc))
        try:
            lib = ctypes.CDLL(self.path)
        except OSError as exc:
            raise WwError("не открыть {}: {}".format(self.path, exc))
        self._ctypes = ctypes
        self._lib = lib
        lib.ww_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        lib.ww_open.restype = ctypes.c_int
        lib.ww_push.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.ww_push.restype = ctypes.c_int
        lib.ww_read_probs.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
        lib.ww_read_probs.restype = ctypes.c_int
        lib.ww_reset.restype = ctypes.c_int
        lib.ww_close.restype = ctypes.c_int
        lib.ww_arena_used.restype = ctypes.c_int
        lib.ww_error.restype = ctypes.c_char_p
        self._open = lib.ww_open
        self._push = lib.ww_push
        self._read = lib.ww_read_probs
        self._reset = lib.ww_reset
        self._close = lib.ww_close
        self._arena = lib.ww_arena_used
        self._error = lib.ww_error
        self._backend = "ctypes"

    def _error_text(self):
        value = self._error()
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return str(value or "")

    def open(self, model_path, arena_size=0, step_ms=10):
        if self._opened:
            raise WwError("рантайм уже открыт")
        path = str(model_path)
        if self._backend == "ctypes":
            path = path.encode()
        code = self._open(path, int(arena_size), int(step_ms))
        if code != 0:
            raise WwError(self._error_text() or "не открыть модель")
        self._opened = True
        return self

    def push(self, pcm):
        """PCM `s16le` моно 16 кГц → список вероятностей 0.0…1.0."""
        if not self._opened:
            raise WwError("рантайм не открыт")
        if not isinstance(pcm, (bytes, bytearray)):
            raise WwError("PCM должен быть bytes или bytearray")
        if len(pcm) % 2:
            raise WwError("PCM должен содержать целые 16-битные сэмплы")
        if not pcm:
            return []
        samples = len(pcm) // 2
        code = self._push(pcm, samples)
        if code < 0:
            raise WwError(self._error_text() or "ошибка обработки")
        buffer = bytearray(MAX_PROBS)
        if self._backend == "ctypes":
            ctypes = self._ctypes
            array = (ctypes.c_ubyte * MAX_PROBS).from_buffer(buffer)
            count = self._read(array, MAX_PROBS)
        else:
            count = self._read(buffer, MAX_PROBS)
        if count < 0:
            raise WwError(self._error_text() or "ошибка чтения вероятностей")
        return [buffer[index] / 255.0 for index in range(count)]

    def reset(self):
        if not self._opened:
            raise WwError("рантайм не открыт")
        if self._reset() != 0:
            raise WwError(self._error_text() or "не сбросить рантайм")
        return True

    def close(self):
        if self._opened:
            self._close()
            self._opened = False
        return True

    def arena_used(self):
        if not self._opened:
            return 0
        return int(self._arena())

    @property
    def backend(self):
        return self._backend

    @property
    def opened(self):
        return self._opened
