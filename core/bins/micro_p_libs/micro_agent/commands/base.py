"""База прямых команд и контекст выполнения."""

from micro_agent.errors import AgentError


class Command:
    """Одна короткая команда."""

    name = ""
    order = 100
    ack_text = None

    def matches(self, text):
        return False

    def run(self, context):
        raise NotImplementedError

    def ack(self):
        return self.ack_text


class CommandContext:
    """То, что нужно командам: звук, UI и текущее время."""

    def __init__(self, audio=None, ui=None, now_ms=0):
        self.audio = audio
        self.ui = ui
        self.now_ms = now_ms

    def _need(self, name):
        value = getattr(self, name, None)
        if value is None:
            raise AgentError("команде нужен {}".format(name))
        return value

    def bt_enable(self):
        return self._need("audio").bt_enable()

    def bt_disable(self):
        return self._need("audio").bt_disable()

    def _volume(self, method):
        value = getattr(self._need("audio"), method)()
        if value is not None and self.ui is not None:
            self.ui.show_volume(value)
        return value

    def volume_up(self):
        return self._volume("volume_up")

    def volume_down(self):
        return self._volume("volume_down")

    def show_date(self):
        self._need("ui").show_date(self.now_ms)

    def show_face(self, name):
        self._need("ui").show_face(name)

    def set_auto(self, enabled):
        self._need("ui").set_auto(enabled)
