"""Команды громкости: выше и ниже."""

from micro_agent.commands.base import Command
from micro_agent.intent import has_any

UP_WORDS = ("выше", "больше", "громче", "плюс", "прибавь", "увеличь",
            "вверх", "погромче")
DOWN_WORDS = ("ниже", "меньше", "тише", "минус", "убавь", "уменьш",
              "вниз", "потише")


def _volume(text):
    return has_any(text, ("громк", "звук", "громче", "тише",
                          "плюс", "минус", "погромче", "потише"))


class VolumeUp(Command):
    name = "volume.up"
    order = 20
    ack_text = "громкость повышена"

    def matches(self, text):
        return _volume(text) and has_any(text, UP_WORDS) \
            and not has_any(text, DOWN_WORDS)

    def run(self, context):
        return context.volume_up()


class VolumeDown(Command):
    name = "volume.down"
    order = 21
    ack_text = "громкость понижена"

    def matches(self, text):
        return _volume(text) and has_any(text, DOWN_WORDS) \
            and not has_any(text, UP_WORDS)

    def run(self, context):
        return context.volume_down()
