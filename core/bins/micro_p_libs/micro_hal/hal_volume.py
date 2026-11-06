"""Громкость PulseAudio: sink'и, проценты, mute.

Только железо/звуковой стек: команды `pactl` и разбор их вывода.
Проценты, шаг и удобные вызовы — в `lib_volume`. Напрямую ALSA
`TV-Set` не трогаем: `ntp-ibb-volume-syncer` сам повторяет за Pulse,
иначе получится двойное ослабление.
"""

from micro_hal import hal_common, hal_pulse
from micro_hal.hal_common import HalError

__all__ = [
    "PACTL",
    "available", "sinks", "default_sink",
    "parse_percent", "parse_mute",
    "get_percent", "set_percent",
    "get_mute", "set_mute", "toggle_mute",
]

PACTL = "/usr/bin/pactl"


def _pactl(args):
    """Выполнить `pactl` с аргументами и вернуть вывод."""
    command = hal_pulse.prefix() + "{} {}".format(
        PACTL, " ".join(args))
    code, text = hal_common.capture(command)
    if code != 0:
        raise HalError("pactl {}: код {}: {}".format(
            " ".join(args), code, text.strip()))
    return text


def available():
    """Отвечает ли PulseAudio."""
    if not hal_common.exists(PACTL):
        return False
    code, text = hal_common.capture(hal_pulse.prefix() + PACTL + " info")
    return code == 0 and "Server Name:" in text


def sinks():
    """Имена доступных sink'ов."""
    text = _pactl(["list", "short", "sinks"])
    names = []
    for line in text.split("\n"):
        parts = line.split()
        if len(parts) >= 2:
            names.append(parts[1])
    return names


def default_sink():
    """Sink по умолчанию (обычно `master`)."""
    text = _pactl(["info"])
    for line in text.split("\n"):
        if line.startswith("Default Sink:"):
            return line.split(":", 1)[1].strip()
    raise HalError("pactl: не найден Default Sink")


def _check_sink(sink):
    """Проверить имя sink и что он есть в Pulse."""
    sink = str(sink)
    if not sink:
        raise HalError("пустое имя sink")
    allowed = ("abcdefghijklmnopqrstuvwxyz"
               "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "0123456789_.-")
    for char in sink:
        if char not in allowed:
            raise HalError("неверное имя sink: {!r}".format(sink))
    names = sinks()
    if sink not in names:
        raise HalError("нет sink {} (есть: {})".format(
            sink, ", ".join(names)))
    return sink


def parse_percent(text):
    """Среднее из всех `NN%` в выводе `pactl`."""
    values = []
    for token in text.replace(",", " ").split():
        if token.endswith("%"):
            try:
                values.append(int(token[:-1]))
            except ValueError:
                continue
    if not values:
        raise HalError("не разобрать громкость: {!r}".format(text.strip()))
    return sum(values) // len(values)


def parse_mute(text):
    """`True`, если в выводе `Mute: yes`."""
    for line in text.split("\n"):
        if line.startswith("Mute:"):
            value = line.split(":", 1)[1].strip().lower()
            return value in ("yes", "1", "true")
    raise HalError("не разобрать mute: {!r}".format(text.strip()))


def get_percent(sink="master"):
    """Громкость sink'а в процентах 0…100."""
    sink = _check_sink(sink)
    return parse_percent(_pactl(["get-sink-volume", sink]))


def set_percent(sink, value):
    """Поставить громкость; значение ограничивается 0…100."""
    sink = _check_sink(sink)
    value = max(0, min(100, int(value)))
    _pactl(["set-sink-volume", sink, "{}%".format(value)])
    return value


def get_mute(sink="master"):
    """Заглушен ли sink."""
    sink = _check_sink(sink)
    return parse_mute(_pactl(["get-sink-mute", sink]))


def set_mute(sink, muted):
    """Заглушить (`True`) или включить (`False`)."""
    sink = _check_sink(sink)
    _pactl(["set-sink-mute", sink, "1" if muted else "0"])
    return bool(muted)


def toggle_mute(sink="master"):
    """Переключить mute."""
    sink = _check_sink(sink)
    _pactl(["set-sink-mute", sink, "toggle"])
