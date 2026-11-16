"""Дисплей: часы, смайлы, дата и громкость.

Тонкая обёртка над `micro_hal.lib_display`. Здесь нет времени и
анимаций — только кадры; режимы и таймеры ведёт `core.py`.
"""

from micro_ui.errors import UiError
from micro_ui.faces import FACE_COLON, face_masks


def _int(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise UiError("{} должен быть целым числом".format(name))
    if value < low or value > high:
        raise UiError("{} должен быть в {}…{}".format(name, low, high))
    return value


class Display:
    """Кадры на четырёхзначном дисплее."""

    def __init__(self, lib=None, brightness=80):
        self._lib = lib
        self.brightness = _int(brightness, "brightness", 0, 100)
        self._opened = False

    def open(self):
        if self._opened:
            return self
        if self._lib is None:
            try:
                from micro_hal import lib_display
            except Exception as exc:
                raise UiError(
                    "micro_hal/lib_display недоступен: {}".format(exc))
            self._lib = lib_display
        opener = getattr(self._lib, "open", None)
        if callable(opener):
            opener()
        try:
            self._lib.brightness(self.brightness)
        except AttributeError:
            pass
        except Exception as exc:
            raise UiError("дисплей: {}".format(exc))
        self._opened = True
        return self

    def _require(self):
        if not self._opened:
            raise UiError("дисплей не открыт")

    def set_brightness(self, percent):
        percent = _int(percent, "brightness", 0, 100)
        self.brightness = percent
        if not self._opened:
            return percent
        try:
            self._lib.brightness(percent)
        except Exception as exc:
            raise UiError("дисплей: {}".format(exc))
        return percent

    def text(self, value, colon=True):
        self._require()
        return self._lib.text(value, colon=colon)

    def frame(self, value, brightness=None, colon=True):
        self._require()
        return self._lib.frame(value, value=brightness, colon=colon)

    def show_frame(self, values):
        self._require()
        return self._lib.show_frame(values)

    def colon(self, top=True, bottom=True, value=None):
        self._require()
        return self._lib.colon(top=top, bottom=bottom, value=value)

    def level(self):
        self._require()
        return self._lib.level()

    def clock(self, hour, minute):
        hour = _int(hour, "hour", 0, 23)
        minute = _int(minute, "minute", 0, 59)
        return self.text("%02d%02d" % (hour, minute))

    def date(self, month, day):
        month = _int(month, "month", 1, 12)
        day = _int(day, "day", 1, 31)
        return self.text("%02d%02d" % (month, day))

    def volume(self, percent):
        percent = _int(percent, "percent", 0, 100)
        return self.text("%3d " % percent, colon=False)

    def face(self, name="eyes"):
        masks = face_masks(name)
        return self._lib.masks(masks, colon=FACE_COLON)

    def face_frame(self, name="eyes", brightness=None):
        """Кадр лица для плавного перехода (как у цифр)."""
        masks = face_masks(name)
        return self._lib.frame_masks(masks, value=brightness,
                                     colon=FACE_COLON)

    def clear(self):
        self._require()
        return self.text("    ", colon=False)

    def close(self):
        if self._opened:
            try:
                self.clear()
            except Exception:
                pass
            closer = getattr(self._lib, "close", None)
            if callable(closer):
                closer()
            self._opened = False

    def info(self):
        return {"brightness": self.brightness, "opened": self._opened}
