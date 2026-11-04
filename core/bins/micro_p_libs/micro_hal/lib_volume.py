"""Громкость: проценты, шаг, mute поверх `hal_volume`.

Логика без железа: удобные `up`/`down`, ограничение 0…100 и шаг.
Владелец громкости — PulseAudio; ALSA `TV-Set` не трогаем.
"""

from micro_hal import hal_volume
from micro_hal.hal_common import HalError

__all__ = ["DEFAULT_SINK", "DEFAULT_STEP", "Volume"]

DEFAULT_SINK = "master"
DEFAULT_STEP = 5


class Volume:
    """Один sink: `get`, `set`, `up`, `down`, `mute`, `toggle`."""

    def __init__(self, sink=DEFAULT_SINK, step=DEFAULT_STEP):
        step = int(step)
        if step <= 0:
            raise HalError("шаг громкости должен быть больше нуля")
        self.sink = sink
        self.step = step

    def get(self):
        """Текущая громкость 0…100."""
        return hal_volume.get_percent(self.sink)

    def set(self, value):
        """Поставить громкость; значение ограничивается 0…100."""
        return hal_volume.set_percent(self.sink, value)

    def up(self, step=None):
        """Прибавить шаг (по умолчанию `self.step`)."""
        step = self.step if step is None else int(step)
        if step <= 0:
            raise HalError("шаг громкости должен быть больше нуля")
        return self.set(min(100, self.get() + step))

    def down(self, step=None):
        """Убавить шаг (по умолчанию `self.step`)."""
        step = self.step if step is None else int(step)
        if step <= 0:
            raise HalError("шаг громкости должен быть больше нуля")
        return self.set(max(0, self.get() - step))

    def muted(self):
        """Заглушен ли sink."""
        return hal_volume.get_mute(self.sink)

    def mute(self):
        """Заглушить."""
        return hal_volume.set_mute(self.sink, True)

    def unmute(self):
        """Включить звук."""
        return hal_volume.set_mute(self.sink, False)

    def toggle(self):
        """Переключить mute и вернуть новое состояние."""
        hal_volume.toggle_mute(self.sink)
        return self.muted()
