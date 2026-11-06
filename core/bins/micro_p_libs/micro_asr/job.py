"""Задача распознавания и её состояния."""

from micro_asr import audio
from micro_asr.errors import AsrError

STATE_IDLE = "idle"
STATE_CAPTURING = "capturing"
STATE_PREPARING = "preparing"
STATE_UPLOADING = "uploading"
STATE_RECOGNIZING = "recognizing"
STATE_DONE = "done"
STATE_STOPPED = "stopped"
STATE_ERROR = "error"

FINAL_STATES = (STATE_DONE, STATE_STOPPED, STATE_ERROR)

_ALLOWED = {
    STATE_IDLE: (STATE_CAPTURING, STATE_PREPARING, STATE_STOPPED,
                 STATE_ERROR),
    STATE_CAPTURING: (STATE_PREPARING, STATE_RECOGNIZING, STATE_DONE,
                      STATE_STOPPED, STATE_ERROR),
    STATE_PREPARING: (STATE_UPLOADING, STATE_RECOGNIZING, STATE_DONE,
                      STATE_STOPPED, STATE_ERROR),
    STATE_UPLOADING: (STATE_RECOGNIZING, STATE_DONE, STATE_STOPPED,
                      STATE_ERROR),
    STATE_RECOGNIZING: (STATE_DONE, STATE_STOPPED, STATE_ERROR),
    STATE_DONE: (),
    STATE_STOPPED: (),
    STATE_ERROR: (),
}


class RecognitionJob:
    """Одна задача: захват, подготовка, распознавание."""

    def __init__(self, job_id, source="?"):
        self.id = job_id
        self.source = source
        self.state = STATE_IDLE
        self.text = ""
        self.speech = False
        self.bytes = 0
        self.duration = 0.0
        self.sample_rate = 0
        self.engine = None
        self.error = None

    def _move(self, state):
        if state not in _ALLOWED.get(self.state, ()):
            raise AsrError(
                "задача {}: нельзя {} → {}".format(
                    self.id, self.state, state))
        self.state = state

    def mark_capturing(self):
        self._move(STATE_CAPTURING)

    def mark_preparing(self):
        self._move(STATE_PREPARING)

    def mark_uploading(self):
        self._move(STATE_UPLOADING)

    def mark_recognizing(self):
        self._move(STATE_RECOGNIZING)

    def set_audio(self, pcm, rate):
        self.bytes = len(pcm)
        self.duration = audio.duration(pcm, rate)
        self.sample_rate = rate

    def mark_done(self, text="", speech=None):
        self._move(STATE_DONE)
        self.text = text or ""
        if speech is not None:
            self.speech = bool(speech)

    def mark_stopped(self):
        self._move(STATE_STOPPED)

    def fail(self, message):
        self._move(STATE_ERROR)
        self.error = str(message)

    def finished(self):
        return self.state in FINAL_STATES

    def status(self):
        return {
            "state": self.state,
            "job_id": self.id,
            "source": self.source,
            "text": self.text,
            "speech": self.speech,
            "bytes": self.bytes,
            "duration": self.duration,
            "sample_rate": self.sample_rate,
            "engine": self.engine,
            "error": self.error,
        }
