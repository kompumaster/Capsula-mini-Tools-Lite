"""Дисплей: шрифт, раскладка, текст и часы.

Поверх `hal_display`: здесь нет sysfs, только логика кадра.
"""

import json
import time

from micro_hal import hal_common, hal_display
from micro_hal.hal_common import HalError

__all__ = [
    "FONT", "SEGMENTS", "STOCK_MAP", "LAYOUT", "COLON",
    "COLON_TOP", "COLON_BOTTOM", "STOCK_MAX",
    "brightness", "get_brightness", "get_gamma", "level",
    "digits", "dots", "frame", "text", "clock", "transition", "pulse",
    "colon", "colon_fade", "map_logical", "raw_logical", "demo_stock",
]

STOCK_MAX = hal_display.STOCK_MAX
SEGMENTS = "abcdefg"
FONT = (0x3f, 0x06, 0x5b, 0x4f, 0x66, 0x6d, 0x7d, 0x07, 0x7f, 0x6f)

_brightness = 100
_gamma = False

# Логический индекс кадра -> физический канал (из voice-agent).
STOCK_MAP = (
    1, 28, 21, 17, 22, 29, 24,
    26, 25, 19, 18, 23, 27, 20,
    16, 15,
    0, 2, 7, 5, 6, 4, 3,
    10, 12, 11, 14, 13, 8, 9,
)

# Сегмент -> физический канал.
LAYOUT = {
    "digit0": {"a": 1, "b": 28, "c": 21, "d": 17, "e": 22, "f": 29, "g": 24},
    "digit1": {"a": 26, "b": 25, "c": 19, "d": 18, "e": 23, "f": 27, "g": 20},
    "digit2": {"a": 0, "b": 2, "c": 7, "d": 5, "e": 6, "f": 4, "g": 3},
    "digit3": {"a": 10, "b": 12, "c": 11, "d": 14, "e": 13, "f": 8, "g": 9},
}
DIGITS = ("digit0", "digit1", "digit2", "digit3")

# Двоеточие — два независимых канала контроллера (не GPIO):
# 0-based 16 = верхняя точка (clock-led17), 15 = нижняя (clock-led16).
COLON_TOP = 16
COLON_BOTTOM = 15
COLON = (COLON_TOP, COLON_BOTTOM)


def brightness(percent=None, gamma=None):
    """Глобальная яркость 0…100; без аргументов — текущий уровень."""
    global _brightness, _gamma
    if gamma is not None:
        _gamma = bool(gamma)
    if percent is not None:
        _brightness = max(0, min(100, int(percent)))
    return level()


def get_brightness():
    """Текущий процент яркости."""
    return _brightness


def get_gamma():
    """Включена ли стоковая кривая яркости."""
    return _gamma


def level(percent=None, gamma=None):
    """Значение сегмента 0…153 для процента и режима."""
    if percent is None:
        percent = _brightness
    if gamma is None:
        gamma = _gamma
    percent = max(0, min(100, int(percent)))
    if percent == 0:
        return 0
    if gamma:
        factor = (percent * 0.62862504 / 100.0) + 0.2514867
        value = int(round(255 * (factor ** 4)))
    else:
        value = STOCK_MAX * percent // 100
    return hal_display.clamp(value)


def _resolve(value):
    return level() if value is None else hal_display.clamp(value)


def digits(string):
    """Четыре позиции: цифры и пробелы; двоеточия игнорируются."""
    tokens = []
    for char in str(string):
        if char.isdigit() or char == " ":
            tokens.append(char)
        elif char != ":":
            raise HalError("недопустимый символ: {!r}".format(char))
    if len(tokens) != 4:
        raise HalError("нужно 4 позиции, получено {}".format(len(tokens)))
    return tokens


def dots(colon):
    """Двоеточие: True/False или пара (верхняя, нижняя)."""
    if colon is True:
        return True, True
    if colon is False:
        return False, False
    if isinstance(colon, (tuple, list)) and len(colon) == 2:
        return bool(colon[0]), bool(colon[1])
    raise HalError("двоеточие: True, False или пара из двух значений")


def frame(string, value=None, colon=True):
    """30 физических значений для строки из 4 цифр."""
    value = _resolve(value)
    values = [0] * hal_display.COUNT
    for position, char in enumerate(digits(string)):
        if char == " ":
            continue
        mask = FONT[int(char)]
        layout = LAYOUT[DIGITS[position]]
        for bit, segment in enumerate(SEGMENTS):
            if mask & (1 << bit):
                values[layout[segment]] = value
    top, bottom = dots(colon)
    if top:
        values[COLON_TOP] = value
    if bottom:
        values[COLON_BOTTOM] = value
    return values


def text(string, value=None, colon=True):
    """Показать 4 цифры; возвращает записанный кадр."""
    values = frame(string, value=value, colon=colon)
    hal_display.raw(values)
    return values


def clock(value=None, colon=True, blink=False, off_ms=250):
    """Текущее время ЧЧ:ММ, 24 часа, ведущий ноль.

    `blink=True` — один цикл: точки выключены `off_ms`, затем включены
    остаток секунды. Функция возвращает кадр с включёнными точками.
    """
    now = time.localtime()
    hour = now[3]
    minute = now[4]
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        values = [0] * hal_display.COUNT
        hal_display.raw(values)
        return values
    string = "%02d%02d" % (hour, minute)
    if not blink:
        return text(string, value=value, colon=colon)
    off_ms = max(0, min(1000, int(off_ms)))
    text(string, value=value, colon=False)
    time.sleep(off_ms / 1000.0)
    values = text(string, value=value, colon=True)
    time.sleep((1000 - off_ms) / 1000.0)
    return values


def transition(old, new, fade_out=1.0, fade_in=1.0, steps=20,
               value=None, colon=None):
    """Плавно заменить цифры: старые гаснут, новые загораются.

    Меняются только различающиеся сегменты; общие остаются на месте.
    `fade_out` и `fade_in` — секунды на фазу, `steps` — шагов в каждой.
    `colon=None` сохраняет текущее состояние точек; True/False или пара
    задаёт их на всё время перехода.
    """
    if steps < 1:
        raise HalError("steps должен быть >= 1")
    steps = int(steps)
    if fade_out < 0 or fade_in < 0:
        raise HalError("fade_out/fade_in не могут быть отрицательными")

    old_frame = frame(old, value=value, colon=False)
    new_frame = frame(new, value=value, colon=False)

    if colon is None:
        colon_top = hal_display.get(COLON_TOP)
        colon_bottom = hal_display.get(COLON_BOTTOM)
    else:
        top_on, bottom_on = dots(colon)
        level = _resolve(value)
        colon_top = level if top_on else 0
        colon_bottom = level if bottom_on else 0

    changed = [
        index for index in range(hal_display.COUNT)
        if index not in COLON and old_frame[index] != new_frame[index]
    ]

    if not changed:
        final = list(new_frame)
        final[COLON_TOP] = colon_top
        final[COLON_BOTTOM] = colon_bottom
        hal_display.raw(final)
        return final

    delay_out = fade_out / steps
    delay_in = fade_in / steps

    for step in range(1, steps + 1):
        values = list(new_frame)
        for index in changed:
            values[index] = old_frame[index] * (steps - step) // steps
        values[COLON_TOP] = colon_top
        values[COLON_BOTTOM] = colon_bottom
        hal_display.raw(values)
        if delay_out:
            time.sleep(delay_out)

    for step in range(1, steps + 1):
        values = list(new_frame)
        for index in changed:
            values[index] = new_frame[index] * step // steps
        values[COLON_TOP] = colon_top
        values[COLON_BOTTOM] = colon_bottom
        hal_display.raw(values)
        if delay_in:
            time.sleep(delay_in)

    return values


def pulse(string, seconds=1.0, steps=20, value=None, colon=True):
    """Показать кадр ярко и плавно погасить за `seconds`.

    Первый кадр — полный, затем `steps` кадров с уменьшением яркости до
    нуля. В конце дисплей погашен.
    """
    if steps < 1:
        raise HalError("steps должен быть >= 1")
    if seconds < 0:
        raise HalError("seconds не может быть отрицательным")
    steps = int(steps)

    values = frame(string, value=value, colon=colon)
    hal_display.raw(values)
    delay = seconds / steps
    for step in range(1, steps + 1):
        factor = (steps - step) / steps
        faded = [int(item * factor) for item in values]
        hal_display.raw(faded)
        if delay:
            time.sleep(delay)
    return [0] * hal_display.COUNT


def colon(top=True, bottom=True, value=None):
    """Включить/выключить точки, не трогая цифры."""
    value = _resolve(value)
    hal_display.set(COLON_TOP, value if top else 0)
    hal_display.set(COLON_BOTTOM, value if bottom else 0)


def colon_fade(seconds=1.0, steps=20, top=True, bottom=True,
               value=None, stop=None):
    """Плавно погасить точки от `value` до нуля за `seconds`.

    `stop` — необязательная функция без аргументов; если она вернула
    True, цикл прерывается (например, наступила следующая секунда).
    """
    if steps < 1:
        raise HalError("steps должен быть >= 1")
    if seconds < 0:
        raise HalError("seconds не может быть отрицательным")
    steps = int(steps)
    level = _resolve(value)
    delay = seconds / steps
    current = level
    for step in range(steps, -1, -1):
        if stop is not None and stop():
            break
        current = level * step // steps
        hal_display.set(COLON_TOP, current if top else 0)
        hal_display.set(COLON_BOTTOM, current if bottom else 0)
        if step and delay:
            time.sleep(delay)
    return current


def map_logical(values):
    """Логический кадр стокового порядка -> физический."""
    if len(values) != hal_display.COUNT:
        raise HalError(
            "кадр: {} значений, ожидается {}".format(
                len(values), hal_display.COUNT))
    physical = [0] * hal_display.COUNT
    for index, value in enumerate(values):
        physical[STOCK_MAP[index]] = value
    return physical


def raw_logical(values):
    """Записать кадр в стоковом порядке (как в JSON-анимациях)."""
    return hal_display.raw(map_logical(values))


def demo_stock(path, speed=1.0, scale=True):
    """Проиграть стоковую JSON-анимацию из `brightness`."""
    if speed <= 0:
        raise HalError("speed должен быть больше нуля")
    frames = json.loads(hal_common.read_text(path))
    factor = level()
    for item in frames:
        values = item["brightness"]
        if scale:
            values = [value * factor // 255 for value in values]
        raw_logical(values)
        time.sleep(item.get("duration", 0.1) / speed)
    return len(frames)
