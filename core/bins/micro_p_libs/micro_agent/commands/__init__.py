"""Реестр прямых команд и разбор текста."""

from micro_agent.commands.base import Command, CommandContext
from micro_agent.commands.auto import AutoBrightnessOff, AutoBrightnessOn
from micro_agent.commands.bluetooth import BluetoothOff, BluetoothOn
from micro_agent.commands.date import DateCommand
from micro_agent.commands.face import FaceCommand
from micro_agent.commands.volume import VolumeDown, VolumeUp
from micro_agent.intent import normalize

COMMANDS = (
    BluetoothOff(),
    BluetoothOn(),
    VolumeUp(),
    VolumeDown(),
    DateCommand(),
    FaceCommand(),
    AutoBrightnessOn(),
    AutoBrightnessOff(),
)


def parse(text):
    """Вернуть команду или None; текст нормализуется."""
    value = normalize(text)
    if not value:
        return None
    for command in sorted(COMMANDS, key=lambda item: item.order):
        if command.matches(value):
            return command
    return None


def run(text, context):
    """Разобрать и выполнить команду; вернуть её или None."""
    command = parse(text)
    if command is None:
        return None
    command.run(context)
    return command


__all__ = [
    "COMMANDS", "Command", "CommandContext", "parse", "run",
]
