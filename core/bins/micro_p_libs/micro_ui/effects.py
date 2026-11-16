"""Чистые эффекты кольца.

Каждая функция получает число пикселей, фазу и параметры режима и
возвращает список RGB-цветов. Без железа, сна и блокировок.

Скорость движения задаётся периодом в миллисекундах (`period_ms`),
а не шагом за кадр: тогда частота кадров (`interval`) не влияет на
скорость. Позиции голов - дробные, поэтому движение плавное.
"""

BLACK = (0, 0, 0)


def _clamp(value):
    value = int(value)
    if value < 0:
        return 0
    if value > 255:
        return 255
    return value


def _color(value):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError("цвет должен быть (r, g, b)")
    return (_clamp(value[0]), _clamp(value[1]), _clamp(value[2]))


def scale(color, level):
    red, green, blue = _color(color)
    level = _clamp(level)
    return (red * level // 255, green * level // 255,
            blue * level // 255)


def blend(first, second, level):
    first = _color(first)
    second = _color(second)
    level = _clamp(level)
    return tuple(first[index]
                 + (second[index] - first[index]) * level // 255
                 for index in range(3))


def add(first, second):
    """Сложить два цвета с насыщением."""
    first = _color(first)
    second = _color(second)
    return tuple(_clamp(first[index] + second[index])
                 for index in range(3))


def falloff(distance):
    """Мягкий хвост: 255 в центре, 0 на краю (`distance` 0…1).

    Профиль `(1 - x²)²`: плоский у вершины и у края, поэтому голова
    не «вспыхивает» при подходе.
    """
    distance = float(distance)
    if distance <= 0.0:
        return 255
    if distance >= 1.0:
        return 0
    left = 1.0 - distance * distance
    return int(left * left * 255 + 0.5)


def lobe(offset, width=127):
    """Мягкое пятно: 255 в центре, 0 дальше `width`."""
    offset = float(offset) % 255.0
    if offset > 127.5:
        offset = 255.0 - offset
    width = float(width)
    if width < 1.0:
        width = 1.0
    if offset >= width:
        return 0
    return falloff(offset / width)


def speed_of(config, units):
    """Дробная скорость: units за кадр из периода в миллисекундах."""
    if "speed" in config:
        return float(config["speed"])
    period = float(config.get("period_ms", 0.0))
    if period <= 0.0:
        return 1.0
    interval = float(config.get("interval", 50))
    return units * interval / period


def _wave(phase, speed):
    """0…255…0; период 512 кадров при speed=1."""
    position = (phase * speed) % 512.0
    return 255.0 - abs(position - 255.0)


def _tri(phase, speed):
    """0…255…0; точный период 510 кадров при speed=1."""
    position = (phase * speed) % 510.0
    if position <= 255.0:
        return position
    return 510.0 - position


def breathe(pixels, phase, config):
    wave = _wave(phase, speed_of(config, 512.0))
    base = int(config.get("base", 20))
    gamma = float(config.get("gamma", 1.0))
    if gamma == 1.0:
        level = max(base, wave)
    else:
        level = base + int((255 - base) * (wave / 255.0) ** gamma)
    color = scale(config.get("color", (0, 180, 60)), level)
    return [color] * pixels


def pair_pulse(pixels, phase, config):
    """Две противоположные дуги пульсируют в противофазе."""
    width = max(1, int(config.get("width", 3)))
    first = config.get("color", (0, 200, 255))
    second = config.get("color2", (0, 100, 255))
    level = _tri(phase, speed_of(config, 510.0))
    colors = [BLACK] * pixels
    for index in range(min(width, pixels)):
        opposite = (index + pixels // 2) % pixels
        colors[index] = scale(first, level)
        colors[opposite] = scale(second, 255.0 - level)
    return colors


def orbit(pixels, phase, config):
    """Одно мягкое пятно медленно обходит кольцо."""
    base = int(config.get("base", 25))
    width = float(config.get("width", 100))
    head = (phase * speed_of(config, 255.0)) % 255.0
    color = config.get("color", (0, 170, 55))
    light = config.get("color2", (40, 255, 150))
    colors = []
    for index in range(pixels):
        offset = index * 255.0 / pixels - head
        wave = lobe(offset, width)
        tint = blend(color, light, wave)
        level = base + (255 - base) * wave // 255
        colors.append(scale(tint, level))
    return colors


def pulse(pixels, phase, config):
    return breathe(pixels, phase, config)


def comet(pixels, phase, config, head=None, color=None):
    tail = max(0.5, float(config.get("tail", 4)))
    front = max(0.1, float(config.get("front", 1.0)))
    if head is None:
        head = phase * speed_of(config, float(pixels))
    head = float(head) % pixels
    first = _color(config.get("color", (0, 200, 255)))
    if color is not None:
        first = _color(color)
    second = _color(config.get("color2", first))
    colors = []
    for index in range(pixels):
        behind = (head - index) % pixels
        if behind > pixels / 2.0:
            behind -= pixels          # отрицательное - впереди головы
        if behind >= 0.0:
            level = falloff(behind / tail)
        else:
            level = falloff(-behind / front)
        colors.append(scale(blend(second, first, level), level))
    return colors


def double_comet(pixels, phase, config):
    head = (phase * speed_of(config, float(pixels))) % pixels
    first = comet(
        pixels, phase, config, head=head,
        color=config.get("color", (130, 0, 255)))
    second = comet(
        pixels, phase, config, head=(pixels / 2.0 - head) % pixels,
        color=config.get("color2", (220, 0, 200)))
    colors = []
    for index in range(pixels):
        left = first[index]
        right = second[index]
        colors.append(tuple(max(left[channel], right[channel])
                            for channel in range(3)))
    return colors


def theater(pixels, phase, config):
    """Мягкие точки через `gap`, рисунок плавно поворачивается."""
    gap = max(1.0, float(config.get("gap", 3)))
    shift = (phase * speed_of(config, gap)) % gap
    first = _color(config.get("color", (220, 230, 255)))
    second = _color(config.get("color2", (0, 100, 255)))
    colors = []
    for index in range(pixels):
        value = (index + shift) % gap
        distance = min(value, gap - value)
        level = falloff(distance / (gap / 2.0))
        cell = int((index + shift) // gap)
        color = first if cell % 2 == 0 else second
        colors.append(scale(color, level))
    return colors


def _blink(pixels, phase, config):
    """Вспышки по времени: `cycle_ms` и интервалы `on_ms`."""
    interval = float(config.get("interval", 50))
    cycle = float(config.get("cycle_ms", 1000))
    spans = config.get("on_ms") or ()
    first = _color(config.get("color", (255, 0, 0)))
    second = _color(config.get("color2", first))
    time_ms = phase * interval
    position = time_ms % cycle
    lit = False
    for start, end in spans:
        if start <= position < end:
            lit = True
            break
    if not lit:
        return [BLACK] * pixels
    index = int(time_ms // cycle)
    return [first if index % 2 == 0 else second] * pixels


def double_blink(pixels, phase, config):
    return _blink(pixels, phase, config)


def triple_flash(pixels, phase, config):
    return _blink(pixels, phase, config)


def wave(pixels, phase, config):
    """Волна бежит по кольцу: у каждого пикселя свой сдвиг."""
    speed = speed_of(config, 510.0)
    head = phase * speed
    first = _color(config.get("color", (0, 255, 140)))
    second = _color(config.get("color2", (0, 160, 80)))
    colors = []
    for index in range(pixels):
        position = (head + index * 255.0 / pixels) % 510.0
        if position > 255.0:
            position = 510.0 - position
        colors.append(scale(blend(second, first, position), position))
    return colors


def single(pixels, phase, config):
    """Короткая дуга или несколько точек медленно дышат."""
    width = max(1, int(config.get("width", 1)))
    spread = max(1, int(config.get("spread", 1)))
    start = int(config.get("index", 0)) % pixels
    base = int(config.get("base", 10))
    wave = _wave(phase, speed_of(config, 512.0))
    level = max(base, wave)
    color = scale(config.get("color", (255, 140, 0)), level)
    colors = [BLACK] * pixels
    for index in range(min(width, pixels)):
        position = (start + index * spread) % pixels
        colors[position] = color
    return colors


def solid(pixels, phase, config):
    return [_color(config.get("color", (255, 255, 255)))] * pixels


EFFECTS = {
    "breathe": breathe,
    "pulse": pulse,
    "comet": comet,
    "double_comet": double_comet,
    "theater": theater,
    "double_blink": double_blink,
    "triple_flash": triple_flash,
    "wave": wave,
    "orbit": orbit,
    "pair_pulse": pair_pulse,
    "single": single,
    "solid": solid,
}


def frame(effect, pixels, phase, config):
    """Собрать кадр эффекта; неизвестный эффект - ValueError."""
    try:
        function = EFFECTS[effect]
    except KeyError:
        raise ValueError("неизвестный эффект: {}".format(effect))
    return function(int(pixels), int(phase), config)
