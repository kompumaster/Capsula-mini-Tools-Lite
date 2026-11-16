"""Кнопки: устройство ввода и декодирование событий.

`micro_hal` подключается только в `open()`. Модуль отдаёт готовые
события `(name, action, count)`; что с ними делать, решает агент.
"""

from micro_agent.errors import AgentError

DEFAULT_DEBOUNCE = 40
DEFAULT_HOLD = 600
DEFAULT_CLICK = 350
DEFAULT_COMBO = 100
DEFAULT_STEP = 150
DEFAULT_COMBO_HOLD = 2000


def _non_negative(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentError("{} должен быть целым числом".format(name))
    if value < 0:
        raise AgentError("{} не может быть отрицательным".format(name))
    return value


class Buttons:
    """Кнопки колонки: `open`, `poll`, `close`."""

    def __init__(self, device=None, keys=None,
                 debounce=DEFAULT_DEBOUNCE, hold=DEFAULT_HOLD,
                 click=DEFAULT_CLICK, combo=DEFAULT_COMBO,
                 step=DEFAULT_STEP, combo_hold=DEFAULT_COMBO_HOLD):
        self._device = device
        self._keys = keys
        self.debounce = _non_negative(debounce, "debounce")
        self.hold = _non_negative(hold, "hold")
        self.click = _non_negative(click, "click")
        self.combo = _non_negative(combo, "combo")
        self.step = _non_negative(step, "step")
        self.combo_hold = _non_negative(combo_hold, "combo_hold")
        self._opened = False

    def open(self):
        if self._opened:
            return self
        try:
            if self._keys is None:
                if self._device is None:
                    from micro_hal import hal_keys
                    self._device = hal_keys.KeysDevice()
                from micro_hal import lib_keys
                self._keys = lib_keys.Keys(
                    device=self._device, debounce=self.debounce,
                    hold=self.hold, click=self.click,
                    combo=self.combo, step=self.step,
                    combo_hold=self.combo_hold)
        except Exception as exc:
            self._device = None
            self._keys = None
            raise AgentError("кнопки: {}".format(exc))
        self._opened = True
        return self

    def _require(self):
        if not self._opened:
            raise AgentError("кнопки не открыты")

    def poll(self, now_ms=None):
        """События клавиш: `[(name, action, count)]`."""
        self._require()
        try:
            return self._keys.poll(0)
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("кнопки: {}".format(exc))

    def close(self):
        self._opened = False
        if self._keys is not None:
            try:
                self._keys.close()
            except Exception:
                pass
        self._keys = None
        self._device = None
        return True

    def info(self):
        return {
            "opened": self._opened,
            "debounce": self.debounce,
            "hold": self.hold,
            "click": self.click,
            "combo": self.combo,
            "combo_hold": self.combo_hold,
            "step": self.step,
        }
