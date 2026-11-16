"""События micro_agent.

Событие — маленький объект с именем и данными. Модули возвращают
события из `poll(now)`, машина состояний их разбирает.
"""

KEYWORD_DETECTED = "keyword_detected"
ASR_STARTED = "asr_started"
UTTERANCE = "utterance"
UTTERANCE_EMPTY = "utterance_empty"
COMMAND_EXECUTED = "command_executed"
ANSWER = "answer"
TTS_FINISHED = "tts_finished"
NETWORK_LOST = "network_lost"
NETWORK_OK = "network_ok"
AP_MODE = "ap_mode"
AP_STOP = "ap_stop"
CANCEL = "cancel"
BT_MODE = "bt_mode"
BT_OFF = "bt_off"
ERROR = "error"
ERROR_CLEARED = "error_cleared"


class Event:
    """Имя события и его данные."""

    def __init__(self, kind, **data):
        if not isinstance(kind, str) or not kind:
            raise ValueError("имя события должно быть непустой строкой")
        self.kind = kind
        self.data = data

    def get(self, name, default=None):
        return self.data.get(name, default)

    def __repr__(self):
        return "Event({!r}, {!r})".format(self.kind, self.data)


def event(kind, **data):
    """Короткая фабрика событий."""
    return Event(kind, **data)
