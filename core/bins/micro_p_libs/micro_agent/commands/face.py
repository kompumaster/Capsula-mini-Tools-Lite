"""Команда показа смайла на дисплее."""

from micro_agent.commands.base import Command
from micro_agent.intent import has_any

# Порядок важен: более конкретные фразы раньше общих.
FACE_WORDS = (
    ("flat", ("спокойной ночи", "спи", "спать", "сон")),
    ("wink", ("подмигни", "подмигнуть")),
    ("smile", ("улыбнись", "улыбка", "улыбнись")),
    ("wide", ("удивись", "удиви", "удивление")),
    ("narrow", ("грустно", "грусть", "грустный")),
    ("eyes", ("покажи глаза", "глаза")),
    ("calm", ("спокойно", "спокойный")),
    ("round", ("круглый", "круг")),
    ("big", ("большой", "широко")),
    ("round", ("смайлик", "смайл", "покажи лицо")),
)


class FaceCommand(Command):
    name = "face"
    order = 40
    ack_text = "смайл на экране"

    def __init__(self):
        self.face = None

    def matches(self, text):
        for name, words in FACE_WORDS:
            if has_any(text, words):
                self.face = name
                return True
        return False

    def run(self, context):
        return context.show_face(self.face)
