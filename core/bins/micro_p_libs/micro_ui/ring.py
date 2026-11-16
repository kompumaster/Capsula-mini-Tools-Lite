"""Кольцо: неблокирующие анимации по режимам.

`tick(now_ms)` рисует один кадр не чаще интервала режима. Цвета и
скорости — здесь; режимы и таймеры — в `core.py`.
"""

from micro_ui import effects
from micro_ui.errors import UiError

MODES = {
    "base": {
        "effect": "orbit", "color": (0, 170, 55),
        "color2": (40, 255, 150), "interval": 40,
        "period_ms": 7650, "base": 25, "width": 100,
    },
    "bt_mode": {
        "effect": "comet", "color": (0, 80, 255),
        "color2": (0, 160, 255), "interval": 40,
        "period_ms": 1200, "tail": 4,
    },
    "netlost": {
        "effect": "double_blink", "color": (255, 120, 0),
        "color2": (255, 30, 0), "interval": 80,
        "cycle_ms": 1920, "on_ms": ((0, 320), (480, 800)),
    },
    "apmode": {
        "effect": "theater", "color": (220, 230, 255),
        "color2": (0, 100, 255), "interval": 40,
        "period_ms": 240, "gap": 3,
    },
    "wake": {
        "effect": "triple_flash", "color": (180, 240, 255),
        "color2": (0, 180, 255), "interval": 40,
        "cycle_ms": 880,
        "on_ms": ((0, 40), (80, 120), (160, 200)),
    },
    "asr": {
        "effect": "pair_pulse", "color": (0, 200, 255),
        "color2": (0, 100, 255), "interval": 40,
        "period_ms": 2040, "width": 3,
    },
    "think": {
        "effect": "double_comet", "color": (130, 0, 255),
        "color2": (220, 0, 200), "interval": 40,
        "period_ms": 720, "tail": 3,
    },
    "speak": {
        "effect": "wave", "color": (0, 255, 140),
        "color2": (0, 160, 80), "interval": 40,
        "period_ms": 2240,
    },
    "muted": {
        "effect": "single", "color": (255, 60, 0),
        "interval": 40, "period_ms": 6000, "base": 50,
        "width": 4, "spread": 3,
    },
    "error": {
        "effect": "pulse", "color": (255, 0, 0),
        "interval": 40, "period_ms": 6000, "base": 10,
    },
}


def _int(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise UiError("{} должен быть целым числом".format(name))
    if value < low or (high is not None and value > high):
        raise UiError("{} вне допустимого диапазона".format(name))
    return value


class RingAnimator:
    """Анимация кольца без сна и без потоков."""

    def __init__(self, ring=None, lib=None, brightness=30):
        self._ring = ring
        self._lib = lib
        self.brightness = _int(brightness, "brightness", 0, 100)
        self.mode = "off"
        self.dither = False
        self._acc = None
        self.phase = 0
        self._next_ms = 0
        self._opened = False

    def open(self):
        if self._opened:
            return self
        if self._ring is None:
            try:
                from micro_hal import hal_ring
                ring = hal_ring.Ring()
            except Exception as exc:
                raise UiError("кольцо: {}".format(exc))
            self._ring = ring
        opener = getattr(self._ring, "open", None)
        if callable(opener):
            opener()
        try:
            self._apply_brightness()
        except Exception as exc:
            raise UiError("кольцо: {}".format(exc))
        if not hasattr(self._ring, "pixels") or self._ring.pixels <= 0:
            raise UiError("кольцо: нет пикселей")
        self._opened = True
        self._prepare_dither(int(self._ring.pixels))
        self.set_mode("base")
        return self

    def _require(self):
        if not self._opened:
            raise UiError("кольцо не открыто")

    def set_mode(self, mode):
        if mode != "off" and mode not in MODES:
            raise UiError("неизвестный режим кольца: {}".format(mode))
        self.mode = mode
        self.phase = 0
        self._next_ms = 0
        return mode

    def config(self):
        """Конфигурация текущего режима."""
        return MODES.get(self.mode)

    def set_brightness(self, percent):
        percent = _int(percent, "brightness", 0, 100)
        self.brightness = percent
        if not self._opened:
            return percent
        try:
            self._apply_brightness()
        except Exception as exc:
            raise UiError("кольцо: {}".format(exc))
        return percent

    def set_dither(self, enabled):
        """Включить/выключить временной дизеринг яркости."""
        if not isinstance(enabled, bool):
            raise UiError("dither должен быть True или False")
        if self.dither == enabled:
            return enabled
        self.dither = enabled
        self._prepare_dither(int(getattr(self._ring, "pixels", 0) or 0))
        if self._opened:
            self._apply_brightness()
        return enabled

    def _apply_brightness(self):
        """Аппаратная яркость: при дизеринге масштаб делает UI."""
        if self.dither:
            value = 255
        else:
            value = 255 * self.brightness // 100
        self._ring.brightness(value)

    def _prepare_dither(self, pixels):
        if pixels <= 0:
            self._acc = None
            return
        if self._acc is None or len(self._acc) != pixels:
            self._acc = [[0.0, 0.0, 0.0] for _ in range(pixels)]

    def _dither(self, index, color, hardware):
        """Разложить дробную яркость по кадрам (перенос ошибки)."""
        acc = self._acc[index]
        result = []
        for channel in range(3):
            exact = color[channel] * hardware / 255.0
            value = acc[channel] + exact
            byte = int(value)
            if byte > 255:
                byte = 255
            elif byte < 0:
                byte = 0
            acc[channel] = value - byte
            result.append(byte)
        return (result[0], result[1], result[2])

    def tick(self, now_ms):
        self._require()
        if self.mode == "off":
            return 0
        now_ms = _int(now_ms, "now_ms", 0, None)
        if now_ms < self._next_ms:
            return 0
        config = self.config()
        pixels = int(self._ring.pixels)
        colors = effects.frame(
            config["effect"], pixels, self.phase, config)
        if self.dither:
            self._prepare_dither(pixels)
            hardware = 255 * self.brightness // 100
            for index, color in enumerate(colors):
                self._ring.pixel(
                    index, self._dither(index, color, hardware))
        else:
            for index, color in enumerate(colors):
                self._ring.pixel(index, color)
        self._ring.show()
        self.phase += 1
        self._next_ms = now_ms + int(config["interval"])
        return pixels

    def off(self):
        if self._ring is not None and self._opened:
            try:
                self._ring.off()
            except Exception:
                pass
        self.mode = "off"
        self.phase = 0
        self._next_ms = 0

    def close(self):
        if not self._opened:
            return True
        try:
            self.off()
        finally:
            try:
                self._ring.close()
            except Exception:
                pass
            self._opened = False
        return True

    def info(self):
        config = self.config() or {}
        return {
            "mode": self.mode,
            "effect": config.get("effect"),
            "dither": self.dither,
            "phase": self.phase,
            "brightness": self.brightness,
            "opened": self._opened,
        }
