"""Команды включения и выключения авто-яркости."""

from micro_agent.commands.base import Command
from micro_agent.intent import has_any

ON_WORDS = (
    "включи автояркость",
    "включи автоматическую яркость",
    "автояркость включи",
    "автояркость вкл",
)
OFF_WORDS = (
    "выключи автояркость",
    "выключи автоматическую яркость",
    "автояркость выключи",
    "автояркость выкл",
)


class AutoBrightnessOn(Command):
    name = "auto.on"
    order = 50
    ack_text = "автояркость включена"

    def matches(self, text):
        return has_any(text, ON_WORDS)

    def run(self, context):
        return context.set_auto(True)


class AutoBrightnessOff(Command):
    name = "auto.off"
    order = 51
    ack_text = "автояркость выключена"

    def matches(self, text):
        return has_any(text, OFF_WORDS)

    def run(self, context):
        return context.set_auto(False)
