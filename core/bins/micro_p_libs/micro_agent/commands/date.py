"""Команда показа даты на дисплее."""

from micro_agent.commands.base import Command
from micro_agent.intent import has_any


class DateCommand(Command):
    name = "date"
    order = 30
    ack_text = "дата на экране"

    def matches(self, text):
        return has_any(text, ("дата", "дату", "число", "сегодняшн",
                              "какое сегодня", "какой сегодня"))

    def run(self, context):
        return context.show_date()
