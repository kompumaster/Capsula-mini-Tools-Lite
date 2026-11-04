"""Эффекты кольца поверх hal_ring."""

import time

from micro_hal import hal_ring
from micro_hal.hal_common import HalError

__all__ = [
    "hsv_to_rgb", "blend", "fade_color", "seed",
    "rainbow_frame", "breathe_frame", "comet_frame",
    "theater_frame", "wipe_frame",
    "static", "blink", "fade", "twinkle", "sparkle",
    "larson_scanner", "bicolor_chase", "tricolor_chase",
    "running_lights", "fire_flicker",
    "rainbow", "breathe", "comet", "theater_chase", "color_wipe",
]

BLACK = (0, 0, 0)
_seed = 1


def _cycles(value):
    value = int(value)
    if value < 1:
        raise HalError("cycles должен быть >= 1")
    return value


def seed(value):
    global _seed
    _seed = int(value) & 0x7FFFFFFF or 1


def _rand():
    global _seed
    _seed = (_seed * 1103515245 + 12345) & 0x7FFFFFFF
    return _seed


def _randbelow(limit):
    if limit <= 0:
        raise HalError("случайное число: limit должен быть > 0")
    return _rand() % limit


def blend(color1, color2, level):
    first = hal_ring.parse_color(color1)
    second = hal_ring.parse_color(color2)
    level = hal_ring.clamp(level)
    return tuple(
        first[index] + (second[index] - first[index]) * level // 255
        for index in range(3)
    )


def fade_color(color, amount):
    red, green, blue = hal_ring.parse_color(color)
    amount = hal_ring.clamp(amount)
    return (max(0, red - amount), max(0, green - amount),
            max(0, blue - amount))


def _show(ring, colors):
    if len(colors) != ring.pixels:
        raise HalError(
            "кадр: {} пикселей, ожидается {}".format(len(colors), ring.pixels))
    for index, color in enumerate(colors):
        ring.pixel(index, color)
    return ring.show()


def hsv_to_rgb(hue, saturation=255, value=255):
    """HSV 0…359 / 0…255 / 0…255 -> (r, g, b)."""
    hue = int(hue) % 360
    saturation = hal_ring.clamp(saturation)
    value = hal_ring.clamp(value)
    if saturation == 0:
        return (value, value, value)
    sector = hue // 60
    fraction = (hue % 60) * 255 // 60
    p = value * (255 - saturation) // 255
    q = value * (255 - (saturation * fraction) // 255) // 255
    t = value * (255 - (saturation * (255 - fraction)) // 255) // 255
    if sector == 0:
        return (value, t, p)
    if sector == 1:
        return (q, value, p)
    if sector == 2:
        return (p, value, t)
    if sector == 3:
        return (p, q, value)
    if sector == 4:
        return (t, p, value)
    return (value, p, q)


def rainbow_frame(pixels, offset=0):
    return [
        hsv_to_rgb((offset + index * 360 // pixels) % 360)
        for index in range(pixels)
    ]


def breathe_frame(pixels, color, level):
    value = hal_ring.scale_color(color, level)
    return [value] * pixels


def comet_frame(pixels, color, head, tail):
    tail = max(1, min(int(tail), pixels))
    head = int(head) % pixels
    colors = [BLACK] * pixels
    for index in range(pixels):
        distance = (head - index) % pixels
        if distance < tail:
            level = 255 * (tail - distance) // tail
            colors[index] = hal_ring.scale_color(color, level)
    return colors


def theater_frame(pixels, color, step, gap=3):
    gap = max(1, int(gap))
    colors = [BLACK] * pixels
    for index in range(pixels):
        if (index + int(step)) % gap == 0:
            colors[index] = hal_ring.parse_color(color)
    return colors


def wipe_frame(pixels, color, count, reverse=False):
    count = max(0, min(int(count), pixels))
    value = hal_ring.parse_color(color)
    colors = [BLACK] * pixels
    if reverse:
        for index in range(pixels - count, pixels):
            colors[index] = value
    else:
        for index in range(count):
            colors[index] = value
    return colors


def rainbow(ring, cycles=1, delay=0.05, step=2):
    cycles = _cycles(cycles)
    step = max(1, int(step))
    for offset in range(0, 360 * cycles, step):
        _show(ring, rainbow_frame(ring.pixels, offset))
        time.sleep(delay)


def breathe(ring, color, cycles=3, delay=0.02, maximum=255, step=5):
    cycles = _cycles(cycles)
    maximum = hal_ring.clamp(maximum)
    step = max(1, int(step))
    for _cycle in range(cycles):
        for level in range(0, maximum + 1, step):
            _show(ring, breathe_frame(ring.pixels, color, level))
            time.sleep(delay)
        for level in range(maximum - step, -1, -step):
            _show(ring, breathe_frame(ring.pixels, color, level))
            time.sleep(delay)


def comet(ring, color, tail=4, cycles=1, delay=0.05):
    cycles = _cycles(cycles)
    for head in range(ring.pixels * cycles):
        _show(ring, comet_frame(ring.pixels, color, head, tail))
        time.sleep(delay)


def theater_chase(ring, color, cycles=3, delay=0.1, gap=3):
    cycles = _cycles(cycles)
    gap = max(1, int(gap))
    for step in range(gap * cycles):
        _show(ring, theater_frame(ring.pixels, color, step, gap))
        time.sleep(delay)


def color_wipe(ring, color, cycles=1, delay=0.05, reverse=False):
    cycles = _cycles(cycles)
    for _cycle in range(cycles):
        for count in range(1, ring.pixels + 1):
            _show(ring, wipe_frame(ring.pixels, color, count, reverse))
            time.sleep(delay)


def static(ring, color):
    ring.fill(color)
    return ring.show()


def blink(ring, color, cycles=5, delay=0.5):
    cycles = _cycles(cycles)
    for _cycle in range(cycles):
        ring.fill(color)
        ring.show()
        time.sleep(delay)
        ring.clear()
        ring.show()
        time.sleep(delay)


def fade(ring, color, cycles=1, delay=0.03, step=16, maximum=255):
    cycles = _cycles(cycles)
    step = max(1, int(step))
    maximum = hal_ring.clamp(maximum)
    levels = list(range(maximum, -1, -step))
    if not levels or levels[-1] != 0:
        levels.append(0)
    for _cycle in range(cycles):
        for level in levels:
            _show(ring, breathe_frame(ring.pixels, color, level))
            time.sleep(delay)


def twinkle(ring, color, cycles=10, delay=0.3, count=1):
    cycles = _cycles(cycles)
    count = max(1, min(int(count), ring.pixels))
    for _cycle in range(cycles):
        ring.clear()
        for _index in range(count):
            ring.pixel(_randbelow(ring.pixels), color)
        ring.show()
        time.sleep(delay)
    ring.clear()
    ring.show()


def sparkle(ring, color, cycles=10, delay=0.1, count=2, decay=64):
    cycles = _cycles(cycles)
    count = max(1, min(int(count), ring.pixels))
    colors = [BLACK] * ring.pixels
    for _cycle in range(cycles):
        for _index in range(count):
            colors[_randbelow(ring.pixels)] = hal_ring.parse_color(color)
        _show(ring, colors)
        time.sleep(delay)
        colors = [fade_color(value, decay) for value in colors]
    ring.clear()
    ring.show()


def larson_scanner(ring, color, cycles=1, delay=0.05, decay=48):
    cycles = _cycles(cycles)
    value = hal_ring.parse_color(color)
    positions = list(range(ring.pixels)) + list(range(ring.pixels - 2, 0, -1))
    trail = [BLACK] * ring.pixels
    for _cycle in range(cycles):
        for head in positions:
            trail = [fade_color(item, decay) for item in trail]
            trail[head] = value
            _show(ring, trail)
            time.sleep(delay)
    ring.clear()
    ring.show()


def bicolor_chase(ring, color1, color2, cycles=3, delay=0.1):
    cycles = _cycles(cycles)
    first = hal_ring.parse_color(color1)
    second = hal_ring.parse_color(color2)
    for step in range(2 * cycles):
        colors = [first if (index + step) % 2 == 0 else second
                  for index in range(ring.pixels)]
        _show(ring, colors)
        time.sleep(delay)


def tricolor_chase(ring, colors, cycles=3, delay=0.1):
    cycles = _cycles(cycles)
    if len(colors) != 3:
        raise HalError("tricolor_chase: нужно 3 цвета")
    values = [hal_ring.parse_color(color) for color in colors]
    for step in range(3 * cycles):
        frame = [values[(index + step) % 3] for index in range(ring.pixels)]
        _show(ring, frame)
        time.sleep(delay)


def running_lights(ring, color1, color2, cycles=1, delay=0.05, step=1):
    cycles = _cycles(cycles)
    step = max(1, int(step))
    first = hal_ring.parse_color(color1)
    second = hal_ring.parse_color(color2)
    span = 2 * ring.pixels
    for phase in range(0, span * cycles, step):
        colors = []
        for index in range(ring.pixels):
            position = (index + phase) % span
            level = position if position < ring.pixels else span - position
            colors.append(blend(first, second, level * 255 // ring.pixels))
        _show(ring, colors)
        time.sleep(delay)


def fire_flicker(ring, color=(255, 80, 0), cycles=30, delay=0.05,
                 maximum=255):
    cycles = _cycles(cycles)
    maximum = hal_ring.clamp(maximum)
    for _cycle in range(cycles):
        colors = [
            hal_ring.scale_color(color, _randbelow(maximum + 1))
            for _index in range(ring.pixels)
        ]
        _show(ring, colors)
        time.sleep(delay)
    ring.clear()
    ring.show()
