"""Sec-MS-GEC для Edge TTS через `libc_edge.so` (`ffi`).

Основной путь — вызов C-функции из `libc_edge.so` через MicroPython
`ffi`. Раньше тяжёлая функция падала из-за `snprintf("%llu%s", …)`;
теперь форматирование в C ручное, без `printf`.

Если `ffi` или библиотека недоступны, используется C-бинарник
`bins/edge_token` (запасной путь). Результат кэшируется на
5-минутное окно.
"""

import os
import time

from micro_tts.errors import TtsError

BIN = "/home/microp/micro_tts/bins/edge_token"
LIB = "/home/microp/micro_tts/bins/libc_edge.so"
TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
TOKEN_SIZE = 81


def _pid():
    try:
        return os.getpid()
    except AttributeError:
        return id(os) & 0xFFFF


class EdgeDrm:
    def __init__(self, path=BIN, lib=LIB,
                 trusted_token=TRUSTED_CLIENT_TOKEN):
        self.path = path
        self.lib = lib
        self.trusted_token = trusted_token
        self._bucket = None
        self._value = None
        self._ffi = None
        self._call = None
        self._call_default = None
        for char in trusted_token:
            if char not in "0123456789abcdefABCDEF":
                raise TtsError("неверный TrustedClientToken")

        try:
            import ffi
        except Exception:
            ffi = None
        if ffi is not None:
            try:
                library = ffi.open(str(lib))
                self._call = library.func(
                    "p", "edge_token_text", "ss")
                self._call_default = library.func(
                    "p", "edge_token_text1", "s")
                self._error = library.func("s", "edge_error", "")
                self._ffi = ffi
            except Exception:
                self._ffi = None
                self._call = None
                self._call_default = None

        if self._ffi is None:
            try:
                os.stat(self.path)
            except OSError:
                raise TtsError(
                    "нет C-токена Edge: {}".format(self.path))

    def token(self, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        timestamp = float(timestamp)
        bucket = int(timestamp) // 300
        if self._bucket == bucket and self._value is not None:
            return self._value

        if self._ffi is not None:
            value = self._token_ffi(timestamp)
        else:
            value = self._token_binary(timestamp)
        self._bucket = bucket
        self._value = value
        return value

    def _token_ffi(self, timestamp):
        text = "{:.6f}".format(timestamp)
        if self.trusted_token == TRUSTED_CLIENT_TOKEN:
            pointer = self._call_default(text)
        else:
            pointer = self._call(text, self.trusted_token)
        if not pointer:
            try:
                message = self._error()
            except Exception:
                message = ""
            raise TtsError("Edge DRM: не получить токен{}".format(
                ": " + message if message else ""))
        data = bytes(self._ffi.as_bytearray(pointer, TOKEN_SIZE))
        try:
            value = data.decode("ascii")
        except Exception:
            raise TtsError("Edge DRM: токен не ASCII")
        if len(value) != TOKEN_SIZE or value[16] != "-":
            raise TtsError("Edge DRM: неверный формат токена")
        return value

    def _token_binary(self, timestamp):
        output = "/tmp/micro_tts_edge_token.{}".format(_pid())
        command = "{} {:.6f}".format(self.path, timestamp)
        if self.trusted_token != TRUSTED_CLIENT_TOKEN:
            command += " '{}'".format(self.trusted_token)
        command += " > {} 2>/dev/null".format(output)
        code = os.system(command)
        if code > 255:
            code >>= 8
        try:
            handle = open(output, "r")
            try:
                value = handle.read().strip()
            finally:
                handle.close()
        except OSError:
            value = ""
        try:
            os.remove(output)
        except OSError:
            pass
        if code != 0 or not value:
            raise TtsError("Edge DRM: не получить токен (код {})".format(
                code))
        return value
