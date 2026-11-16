"""Ядро UI: режимы, часы, оверлеи, TTL и lease.

Здесь нет сокетов и железа: дисплей и кольцо передаются снаружи,
поэтому поведение проверяется на хосте.
"""

from micro_ui.display import Display
from micro_ui.errors import UiError
from micro_ui.faces import MODE_FACES, face_masks
from micro_ui.ring import RingAnimator

PERSISTENT_MODES = ("base", "bt_mode", "netlost", "apmode", "muted")
TRANSIENT_MODES = ("wake", "asr", "think", "speak", "error")
MODES = PERSISTENT_MODES + TRANSIENT_MODES
CLOCK_MODES = PERSISTENT_MODES

# ASR/TTS блокируют цикл агента, поэтому lease заведомо больше.
MODE_LEASE_MS = {
    "wake": 60000,
    "asr": 60000,
    "think": 60000,
    "speak": 180000,
    "error": 15000,
}

DEFAULT_DATE_MS = 20000
DEFAULT_VOLUME_MS = 5000
DEFAULT_FACE_MS = 5000

# Переход между смайлами — как смена минуты: 5 шагов за 200 мс.
FACE_TRANSITION_MS = 200
FACE_TRANSITION_STEPS = 5

# lux -> доля диапазона auto_min…auto_max
AUTO_POINTS = (
    (0.0, 0.0),
    (2.0, 0.12),
    (10.0, 0.30),
    (50.0, 0.50),
    (200.0, 0.68),
    (800.0, 0.85),
    (3000.0, 1.0),
)
# Выше этого — выброс датчика, а не свет: не меняем яркость.
MAX_LUX = 5000.0
DEFAULT_AUTO_MIN = 20
DEFAULT_AUTO_MAX = 100
DEFAULT_AUTO_INTERVAL_MS = 1000


def auto_target(lux, minimum=DEFAULT_AUTO_MIN, maximum=DEFAULT_AUTO_MAX):
    """Освещённость -> глобальная яркость."""
    if lux != lux:  # NaN
        lux = 0.0
    if lux < 0:
        lux = 0.0
    minimum = _int(minimum, "auto_min", 0, 100)
    maximum = _int(maximum, "auto_max", 0, 100)
    if minimum > maximum:
        raise UiError("auto_min больше auto_max")
    if lux <= AUTO_POINTS[0][0]:
        fraction = AUTO_POINTS[0][1]
    elif lux >= AUTO_POINTS[-1][0]:
        fraction = AUTO_POINTS[-1][1]
    else:
        fraction = AUTO_POINTS[-1][1]
        for index in range(1, len(AUTO_POINTS)):
            high = AUTO_POINTS[index]
            if lux <= high[0]:
                low = AUTO_POINTS[index - 1]
                span = high[0] - low[0]
                fraction = low[1]
                if span:
                    fraction += ((lux - low[0]) / span
                                 * (high[1] - low[1]))
                break
    value = minimum + (maximum - minimum) * fraction
    return int(value + 0.5)


def _int(value, name, low, high=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise UiError("{} должен быть целым числом".format(name))
    if value < low or (high is not None and value > high):
        raise UiError("{} вне допустимого диапазона".format(name))
    return value


def _local(now):
    if now is not None:
        return now
    try:
        import time
        return time.localtime()
    except ImportError:
        return (0, 0, 0, 0, 0, 0, 0, 0)


class UiCore:
    """Режимы дисплея и кольца, часы и временные оверлеи."""

    def __init__(self, display=None, ring=None,
                 date_ms=DEFAULT_DATE_MS, volume_ms=DEFAULT_VOLUME_MS,
                 face_ms=DEFAULT_FACE_MS,
                 display_brightness=80, ring_brightness=30,
                 global_brightness=100,
                 auto=False, auto_min=DEFAULT_AUTO_MIN,
                 auto_max=DEFAULT_AUTO_MAX,
                 auto_interval_ms=DEFAULT_AUTO_INTERVAL_MS,
                 sensor=None):
        self.display = display if display is not None else Display()
        self.ring = ring if ring is not None else RingAnimator()
        self.date_ms = _int(date_ms, "date_ms", 1, None)
        self.volume_ms = _int(volume_ms, "volume_ms", 1, None)
        self.face_ms = _int(face_ms, "face_ms", 1, None)
        self.display_base = _int(
            display_brightness, "display_brightness", 0, 100)
        self.ring_base = _int(
            ring_brightness, "ring_brightness", 0, 100)
        self.global_brightness = _int(
            global_brightness, "global_brightness", 0, 100)
        self.manual_global = self.global_brightness
        self.auto_min = _int(auto_min, "auto_min", 0, 100)
        self.auto_max = _int(auto_max, "auto_max", 0, 100)
        if self.auto_min > self.auto_max:
            raise UiError("auto_min больше auto_max")
        self.auto_interval_ms = _int(
            auto_interval_ms, "auto_interval_ms", 1, None)
        self.auto_enabled = bool(auto)
        self._sensor = sensor
        self._auto_last = None
        self._auto_lux = None
        self.auto_error = None
        self.mode = "base"
        self.persistent = "base"
        self._mode_until = None
        self._overlay = None
        self._overlay_value = None
        self._overlay_date = None
        self._overlay_until = None
        self._clock_text = None
        self._clock_transition = None
        self._clock_second = None
        self._clock_second_start = 0
        self._clock_colon_step = None
        self._face_frame = None
        self._face_transition = None
        self._now_ms = 0
        self._opened = False

    # --- служебное -------------------------------------------------

    def _require(self):
        if not self._opened:
            raise UiError("UI не открыт")

    def _reset_clock(self):
        self._clock_text = None
        self._clock_transition = None
        self._clock_second = None
        self._clock_second_start = 0
        self._clock_colon_step = None

    def _now(self, now_ms):
        if now_ms is None:
            return self._now_ms
        return _int(now_ms, "now_ms", 0, None)

    def _sensor_module(self):
        if self._sensor is not None:
            return self._sensor
        try:
            from micro_hal import hal_light
        except Exception as exc:
            raise UiError("датчик света недоступен: {}".format(exc))
        self._sensor = hal_light
        return self._sensor

    def set_auto(self, enabled):
        """Включить/выключить авто-яркость."""
        self._require()
        if not isinstance(enabled, bool):
            raise UiError("auto должен быть True или False")
        if enabled:
            if self.auto_enabled:
                return True
            sensor = self._sensor_module()
            available = getattr(sensor, "available", None)
            if callable(available) and not available():
                raise UiError("датчик света недоступен")
            self.auto_enabled = True
            self._auto_last = None
            self._auto_lux = None
            self._auto_tick(self._now_ms, force=True)
        else:
            self._auto_last = None
            self._auto_lux = None
            self.auto_error = None
            if not self.auto_enabled:
                if self.global_brightness != self.manual_global:
                    self.global_brightness = self.manual_global
                    self._apply_brightness()
                    self._refresh_display()
                return False
            self.auto_enabled = False
            self.global_brightness = self.manual_global
            self._apply_brightness()
            self._refresh_display()
        return self.auto_enabled

    def _auto_tick(self, now_ms, force=False):
        if not self.auto_enabled:
            return
        if (not force and self._auto_last is not None
                and now_ms - self._auto_last < self.auto_interval_ms):
            return
        self._auto_last = now_ms
        try:
            value = float(self._sensor_module().read())
        except Exception as exc:
            self.auto_error = "датчик света: {}".format(exc)
            return
        if value < 0:
            value = 0.0
        if value > MAX_LUX:
            # выброс датчика: яркость не трогаем
            return
        if self._auto_lux is None:
            self._auto_lux = value
        else:
            self._auto_lux = (self._auto_lux * 3 + value) / 4.0
        target = auto_target(
            self._auto_lux, self.auto_min, self.auto_max)
        if force or abs(target - self.global_brightness) >= 2:
            self.global_brightness = target
            self._apply_brightness()
            self._refresh_display()
        self.auto_error = None

    def open(self, now_ms=0, now=None):
        if self._opened:
            return self
        self.display.open()
        try:
            self.ring.open()
        except Exception:
            try:
                self.display.close()
            except Exception:
                pass
            raise
        self._opened = True
        self._now_ms = _int(now_ms, "now_ms", 0, None)
        self._apply_brightness()
        self.set_mode("base", now_ms=self._now_ms, now=now)
        if self.auto_enabled:
            self._auto_tick(self._now_ms, force=True)
        return self

    def close(self):
        if not self._opened:
            return True
        try:
            self.ring.close()
        finally:
            self.display.close()
            self._opened = False
        return True

    # --- режимы ----------------------------------------------------

    def set_mode(self, mode, lease_ms=None, now_ms=None, now=None):
        """Переключить режим; оверлей сбрасывается."""
        self._require()
        if mode not in MODES:
            raise UiError("неизвестный режим UI: {}".format(mode))
        now_ms = self._now(now_ms)
        self._now_ms = now_ms
        if mode in PERSISTENT_MODES:
            lease = 0
            self.persistent = mode
        else:
            if lease_ms is None:
                lease = MODE_LEASE_MS[mode]
            else:
                lease = _int(lease_ms, "lease_ms", 0, None)
        self.mode = mode
        self._mode_until = now_ms + lease if lease else None
        self._clear_overlay()
        self._reset_clock()
        self.ring.set_mode(mode)
        self._draw(now)
        return mode

    def show(self, mode, now=None):
        """Совместимая короткая форма `set_mode`."""
        return self.set_mode(mode, now_ms=None, now=now)

    def sync(self, mode, lease_ms=None, now_ms=None, now=None):
        """Сверить режим: применить только если он отличается.

        В отличие от `set_mode`, не сбрасывает анимацию кольца,
        оверлей и часы, когда режим уже такой.
        """
        self._require()
        if mode not in MODES:
            raise UiError("неизвестный режим UI: {}".format(mode))
        if mode == self.mode:
            return mode
        return self.set_mode(mode, lease_ms=lease_ms,
                             now_ms=now_ms, now=now)

    def set_dither(self, enabled):
        """Включить/выключить временной дизеринг яркости."""
        self._require()
        if not isinstance(enabled, bool):
            raise UiError("dither должен быть True или False")
        return self.ring.set_dither(enabled)

    def _restore(self, now=None):
        self.mode = self.persistent
        self._mode_until = None
        self._reset_clock()
        self.ring.set_mode(self.persistent)
        if self._overlay is None:
            self._draw(now)

    # --- оверлеи ---------------------------------------------------

    def _clear_overlay(self):
        self._overlay = None
        self._overlay_value = None
        self._overlay_date = None
        self._overlay_until = None

    def _effective(self, base):
        return base * self.global_brightness // 100

    def _apply_brightness(self):
        self.display.set_brightness(self._effective(self.display_base))
        self.ring.set_brightness(self._effective(self.ring_base))

    def _refresh_display(self):
        if self._overlay == "date" and self._overlay_date is not None:
            self.display.date(self._overlay_date[0], self._overlay_date[1])
        elif self._overlay == "volume":
            self.display.volume(self._overlay_value)
        elif self._overlay == "face":
            self.display.face(self._overlay_value)
        else:
            self._reset_clock()
            self._draw()

    def show_date(self, now_ms=None, now=None, ttl_ms=None):
        """Показать дату `ММ.ДД` на `ttl_ms` и вернуться к режиму."""
        self._require()
        now_ms = self._now(now_ms)
        if ttl_ms is None:
            ttl_ms = self.date_ms
        else:
            ttl_ms = _int(ttl_ms, "ttl_ms", 1, None)
        local = _local(now)
        self.display.date(local[1], local[2])
        self._overlay = "date"
        self._face_transition = None
        self._overlay_value = None
        self._overlay_date = (local[1], local[2])
        self._overlay_until = now_ms + ttl_ms
        self._reset_clock()
        return self._overlay_until

    def show_volume(self, percent, ttl_ms=None, now_ms=None):
        """Показать громкость на `ttl_ms` и вернуться к режиму."""
        self._require()
        percent = _int(percent, "percent", 0, 100)
        now_ms = self._now(now_ms)
        if ttl_ms is None:
            ttl_ms = self.volume_ms
        else:
            ttl_ms = _int(ttl_ms, "ttl_ms", 1, None)
        self.display.volume(percent)
        self._overlay = "volume"
        self._face_transition = None
        self._overlay_value = percent
        self._overlay_until = now_ms + ttl_ms
        self._reset_clock()
        return self._overlay_until

    def show_face(self, name, ttl_ms=None, now_ms=None):
        """Показать смайл на `ttl_ms` и вернуться к режиму."""
        self._require()
        face_masks(name)
        now_ms = self._now(now_ms)
        if ttl_ms is None:
            ttl_ms = self.face_ms
        else:
            ttl_ms = _int(ttl_ms, "ttl_ms", 1, None)
        self.display.face(name)
        self._overlay = "face"
        self._face_transition = None
        self._overlay_value = name
        self._overlay_until = now_ms + ttl_ms
        self._reset_clock()
        return self._overlay_until

    def set_brightness(self, display=None, ring=None):
        """Установить базовую яркость дисплея и/или кольца."""
        self._require()
        if display is None and ring is None:
            raise UiError("нужна яркость дисплея или кольца")
        old_display = self.display_base
        old_ring = self.ring_base
        if display is not None:
            self.display_base = _int(
                display, "brightness дисплея", 0, 100)
        if ring is not None:
            self.ring_base = _int(ring, "brightness кольца", 0, 100)
        if (self.display_base == old_display
                and self.ring_base == old_ring):
            return self
        self._apply_brightness()
        self._refresh_display()
        return self

    def set_global(self, percent):
        """Установить ручной общий множитель яркости 0…100."""
        self._require()
        percent = _int(percent, "global", 0, 100)
        if self.manual_global == percent:
            return self
        self.manual_global = percent
        if not self.auto_enabled:
            self.global_brightness = percent
            self._apply_brightness()
            self._refresh_display()
        return self

    # --- отрисовка -------------------------------------------------

    def _draw(self, now=None):
        if self.mode in MODE_FACES:
            self._show_face(MODE_FACES[self.mode])
        else:
            self._face_frame = None
            self._face_transition = None
            self._draw_clock(now)

    def _show_face(self, name):
        """Показать лицо; при смене — плавный переход от прежнего."""
        target = self.display.face_frame(name)
        if self._face_frame is None or self._face_frame == target:
            self.display.show_frame(target)
            self._face_frame = target
            self._face_transition = None
            return
        self._face_transition = {
            "old": self._face_frame,
            "new": target,
            "start": self._now_ms,
            "duration": FACE_TRANSITION_MS,
            "steps": FACE_TRANSITION_STEPS,
            "last": -1,
        }

    def _draw_face_transition(self):
        transition = self._face_transition
        if transition is None:
            return
        elapsed = self._now_ms - transition["start"]
        if elapsed < 0:
            elapsed = 0
        steps = transition["steps"]
        step = elapsed * steps // transition["duration"]
        if step >= steps:
            self.display.show_frame(transition["new"])
            self._face_frame = transition["new"]
            self._face_transition = None
            return
        if step != transition["last"]:
            values = []
            for old, new in zip(transition["old"], transition["new"]):
                if old == new:
                    values.append(old)
                else:
                    values.append(old + (new - old) * step // steps)
            self.display.show_frame(values)
            transition["last"] = step

    def _clock_level(self):
        getter = getattr(self.display, "level", None)
        if callable(getter):
            try:
                return getter()
            except Exception:
                pass
        return 100

    def _show_clock_text(self, text, level):
        frame = self.display.frame(text, brightness=level, colon=False)
        self.display.show_frame(frame)
        self.display.colon(True, True, level)
        return frame

    def _draw_clock(self, now=None):
        """Неблокирующие эффекты: переход минуты и затухание точек."""
        now = _local(now)
        text = "%02d%02d" % (now[3], now[4])
        second = now[5]
        level = self._clock_level()
        if self._clock_text is None:
            self._clock_text = text
            self._clock_second = second
            self._clock_second_start = self._now_ms
            self._show_clock_text(text, level)
            self._clock_colon_step = 0
            return
        if text != self._clock_text:
            old = self.display.frame(
                self._clock_text, brightness=level, colon=False)
            new = self.display.frame(
                text, brightness=level, colon=False)
            self._clock_transition = {
                "old": old,
                "new": new,
                "start": self._now_ms,
                "duration": 200,
                "steps": 5,
                "last": -1,
            }
            self._clock_text = text
            self._clock_second = second
            self._clock_colon_step = None
        transition = self._clock_transition
        if transition is not None:
            elapsed = self._now_ms - transition["start"]
            steps = transition["steps"]
            step = elapsed * steps // transition["duration"]
            if step >= steps:
                self.display.show_frame(transition["new"])
                self.display.colon(True, True, level)
                self._clock_transition = None
                self._clock_second = second
                self._clock_second_start = self._now_ms
                self._clock_colon_step = 0
                return
            if step != transition["last"]:
                values = []
                for old, new in zip(
                        transition["old"], transition["new"]):
                    if old == new:
                        values.append(old)
                    else:
                        values.append(
                            old + (new - old) * step // steps)
                self.display.show_frame(values)
                self.display.colon(True, True, level)
                transition["last"] = step
            return
        if second != self._clock_second:
            self._clock_second = second
            self._clock_second_start = self._now_ms
            self._clock_colon_step = None
        elapsed = self._now_ms - self._clock_second_start
        if elapsed < 0:
            elapsed = 0
        step = elapsed * 20 // 1000
        if step > 20:
            step = 20
        if step != self._clock_colon_step:
            value = level * (20 - step) // 20
            self.display.colon(True, True, value)
            self._clock_colon_step = step

    def tick(self, now_ms, now=None):
        """Один шаг: часы, оверлей, lease и кадр кольца."""
        self._require()
        now_ms = _int(now_ms, "now_ms", 0, None)
        self._now_ms = now_ms
        self._auto_tick(now_ms)
        if (self.mode in TRANSIENT_MODES
                and self._mode_until is not None
                and now_ms >= self._mode_until):
            self._restore(now)
        if self._overlay is not None:
            if now_ms >= self._overlay_until:
                self._clear_overlay()
                self._reset_clock()
                self._draw(now)
        elif self.mode in CLOCK_MODES:
            self._draw_clock(now)
        elif self._face_transition is not None:
            self._draw_face_transition()
        self.ring.tick(now_ms)
        return self.mode

    # --- состояние -------------------------------------------------

    def info(self):
        display = getattr(self.display, "info", None)
        ring = getattr(self.ring, "info", None)
        ring_info = ring() if callable(ring) else None
        return {
            "mode": self.mode,
            "persistent": self.persistent,
            "mode_until": self._mode_until,
            "overlay": self._overlay,
            "overlay_value": self._overlay_value,
            "overlay_until": self._overlay_until,
            "display_brightness": self.display_base,
            "ring_brightness": self.ring_base,
            "global_brightness": self.global_brightness,
            "display_effective": self._effective(self.display_base),
            "ring_effective": self._effective(self.ring_base),
            "manual_global": self.manual_global,
            "auto": self.auto_enabled,
            "auto_min": self.auto_min,
            "auto_max": self.auto_max,
            "auto_lux": self._auto_lux,
            "auto_error": self.auto_error,
            "now_ms": self._now_ms,
            "opened": self._opened,
            "display": display() if callable(display) else None,
            "ring": ring_info,
            "phase": (ring_info or {}).get("phase"),
            "dither": (ring_info or {}).get("dither"),
        }
