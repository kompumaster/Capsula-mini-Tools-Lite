"""Кольцо WS2812B: 12 RGB через /dev/topleds и libc_ring.so."""

from micro_hal import hal_common
from micro_hal.hal_common import HalError

__all__ = [
    "STOCK_MAP", "LIB", "CHANNELS", "PIXELS",
    "parse_color", "scale_color", "build_frame", "Ring",
]

LIB = "/home/microp/micro_hal/bins/libc_ring.so"
CHANNELS = 36
PIXELS = 12

# Логический канал -> физический (из voice-agent, 0x00b089d0).
STOCK_MAP = (
    1, 0, 2,
    34, 33, 35,
    31, 30, 32,
    28, 27, 29,
    25, 24, 26,
    22, 21, 23,
    19, 18, 20,
    16, 15, 17,
    13, 12, 14,
    10, 9, 11,
    7, 6, 8,
    4, 3, 5,
)


def clamp(value):
    value = int(value)
    if value < 0:
        return 0
    if value > 255:
        return 255
    return value


def parse_color(color):
    """(r, g, b) или 0xRRGGBB -> кортеж 0…255."""
    if isinstance(color, (tuple, list)):
        if len(color) != 3:
            raise HalError("цвет: нужен кортеж из 3 значений")
        return (clamp(color[0]), clamp(color[1]), clamp(color[2]))
    if isinstance(color, int):
        if color < 0 or color > 0xFFFFFF:
            raise HalError("цвет: ожидается 0xRRGGBB")
        return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)
    raise HalError("цвет: кортеж (r, g, b) или 0xRRGGBB")


def scale_color(color, brightness):
    red, green, blue = parse_color(color)
    level = clamp(brightness)
    return (red * level // 255, green * level // 255, blue * level // 255)


def build_frame(colors, brightness=255):
    """12 логических цветов -> 36 физических байт."""
    if len(colors) != PIXELS:
        raise HalError("кадр: нужно {} пикселей".format(PIXELS))
    frame = [0] * CHANNELS
    for pixel, color in enumerate(colors):
        red, green, blue = scale_color(color, brightness)
        base = 3 * pixel
        frame[STOCK_MAP[base]] = red
        frame[STOCK_MAP[base + 1]] = green
        frame[STOCK_MAP[base + 2]] = blue
    return frame


class Ring:
    """NeoPixel-подобное управление кольцом."""

    def __init__(self, path="/dev/topleds", library=LIB):
        hal_common.require_root()
        hal_common.require_va_stopped("кольцо")
        self._lock = hal_common.lock("ring")
        self._fd = None
        try:
            import ffi

            self._ffi = ffi
            self._lib = ffi.open(library)
            self._open = self._lib.func("i", "ring_open", "s")
            self._count = self._lib.func("i", "ring_count", "i")
            self._frame_ptr = self._lib.func("p", "ring_frame", "")
            self._write = self._lib.func("i", "ring_write_frame", "ii")
            self._close = self._lib.func("i", "ring_close", "i")
            self._errno = self._lib.func("i", "ring_errno", "")

            self._fd = self._open(path)
            if self._fd < 0:
                raise HalError(
                    "не открыть {}: errno {}".format(path, self._errno()))

            channels = self._count(self._fd)
            if channels != CHANNELS:
                raise HalError(
                    "кольцо: {} каналов, ожидается {}".format(
                        channels, CHANNELS))

            pointer = self._frame_ptr()
            if not pointer:
                raise HalError("кольцо: нет буфера кадра")

            self.channels = channels
            self.pixels = channels // 3
            self._frame = self._ffi.as_bytearray(pointer, channels)
            self._colors = [(0, 0, 0)] * self.pixels
            self._brightness = 255
        except Exception as exc:
            self._release()
            if isinstance(exc, HalError):
                raise
            raise HalError(
                "кольцо: не открыть {}: {}".format(library, exc))

    def _release(self):
        """Закрыть дескриптор и снять замок, в том числе после ошибки."""
        fd = getattr(self, "_fd", None)
        close = getattr(self, "_close", None)
        if fd is not None and fd >= 0 and close is not None:
            try:
                close(fd)
            except Exception:
                pass
        self._fd = None
        lock = getattr(self, "_lock", None)
        if lock is not None:
            lock.release()
            self._lock = None

    def _index(self, index):
        index = int(index)
        if index < 0 or index >= self.pixels:
            raise HalError(
                "пиксель {} вне 0…{}".format(index, self.pixels - 1))
        return index

    def pixel(self, index, color):
        self._colors[self._index(index)] = parse_color(color)

    def fill(self, color):
        value = parse_color(color)
        self._colors = [value] * self.pixels

    def brightness(self, value=None):
        if value is not None:
            self._brightness = clamp(value)
        return self._brightness

    def show(self):
        if self._fd is None:
            raise HalError("кольцо закрыто")
        frame = build_frame(self._colors, self._brightness)
        for index in range(self.channels):
            self._frame[index] = frame[index]
        result = self._write(self._fd, self.channels)
        if result != 0:
            raise HalError("ring_write_frame: errno {}".format(self._errno()))
        return result

    def clear(self):
        self._colors = [(0, 0, 0)] * self.pixels

    def off(self):
        self.clear()
        return self.show()

    def close(self):
        try:
            if self._fd is not None and self._fd >= 0:
                self._close(self._fd)
        finally:
            self._fd = None
            if self._lock is not None:
                self._lock.release()
                self._lock = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
