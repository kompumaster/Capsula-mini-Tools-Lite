"""Машина состояний сценария micro_agent.

На входе — события, на выходе — команды модулям. Железо и таймеры
здесь не трогаются, поэтому переходы проверяются без платы.
"""

from micro_agent.core import events as ev

STATE_BASE = "base"
STATE_WAKE = "wake"
STATE_ASR = "asr"
STATE_THINK = "think"
STATE_SPEAK = "speak"
STATE_BT_MODE = "bt_mode"
STATE_NETLOST = "netlost"
STATE_APMODE = "apmode"
STATE_ERROR = "error"

RETURN_MODES = (STATE_BASE, STATE_BT_MODE)

CMD_UI = "ui"
CMD_ACK = "ack"
CMD_ASR_START = "asr_start"
CMD_ASR_STOP = "asr_stop"
CMD_THINK = "think"
CMD_SPEAK = "speak"
CMD_TTS_STOP = "tts_stop"
CMD_BT_AUDIO = "bt_audio"
CMD_AP = "ap"
CMD_ERROR = "error"


def command(name, **data):
    return {"name": name, "data": data}


def _kind(event):
    if hasattr(event, "kind"):
        return event.kind
    if isinstance(event, dict):
        return event.get("kind")
    return None


def _get(event, name, default=None):
    if hasattr(event, "get"):
        return event.get(name, default)
    return default


class StateMachine:
    """Режимы колонки и переходы между ними."""

    def __init__(self, initial=STATE_BASE, dialog=False):
        if initial not in (STATE_BASE, STATE_BT_MODE):
            raise ValueError("неверное начальное состояние")
        self.state = initial
        self.return_mode = initial
        self.network_resume = initial
        self.dialog = bool(dialog)
        self.dialog_next = False

    # --- вспомогательное -------------------------------------------

    def set_dialog(self, enabled):
        """Включить/выключить режим диалога."""
        self.dialog = bool(enabled)
        if not self.dialog:
            self.dialog_next = False
        return self.dialog

    def _reset_dialog(self):
        self.dialog = False
        self.dialog_next = False

    def _ui(self, mode):
        return command(CMD_UI, mode=mode)

    def _bt_suspend(self, commands):
        if self.return_mode == STATE_BT_MODE:
            commands.append(command(CMD_BT_AUDIO, state="suspend"))

    def _return(self, commands, resume_bt=True):
        mode = self.return_mode
        self.state = mode
        self._reset_dialog()
        commands.append(self._ui(mode))
        if resume_bt and mode == STATE_BT_MODE:
            commands.append(command(CMD_BT_AUDIO, state="resume"))
        return commands

    # --- события ---------------------------------------------------

    def handle(self, event):
        kind = _kind(event)
        if kind is None:
            return []

        if kind == ev.KEYWORD_DETECTED:
            return self._keyword(event)
        if kind == ev.ASR_STARTED:
            if self.state == STATE_ASR:
                # Диалог: захват уже идёт; после него — индикация asr.
                return [self._ui(STATE_ASR)]
            if self.state != STATE_WAKE:
                return []
            self.state = STATE_ASR
            return [self._ui(STATE_ASR)]
        if kind == ev.UTTERANCE:
            if self.state != STATE_ASR:
                return []
            self.dialog_next = False
            text = _get(event, "text", "")
            if not text:
                return self.handle(ev.Event(ev.UTTERANCE_EMPTY))
            self.state = STATE_THINK
            return [command(CMD_ASR_STOP),
                    command(CMD_THINK, text=text)]
        if kind == ev.UTTERANCE_EMPTY:
            if self.state != STATE_ASR:
                return []
            commands = [command(CMD_ASR_STOP)]
            return self._return(commands)
        if kind == ev.COMMAND_EXECUTED:
            if self.state != STATE_ASR:
                return []
            self.dialog_next = False
            mode = _get(event, "mode")
            if mode in RETURN_MODES:
                self.return_mode = mode
            ack = _get(event, "ack")
            if ack:
                self.state = STATE_SPEAK
                return [command(CMD_ASR_STOP),
                        self._ui(STATE_SPEAK),
                        command(CMD_SPEAK, text=ack, cache=True)]
            commands = [command(CMD_ASR_STOP)]
            return self._return(commands)
        if kind == ev.ANSWER:
            if self.state != STATE_THINK:
                return []
            text = _get(event, "text", "")
            self.dialog_next = True
            self.state = STATE_SPEAK
            return [self._ui(STATE_SPEAK),
                    command(CMD_SPEAK, text=text)]
        if kind == ev.TTS_FINISHED:
            if self.state != STATE_SPEAK:
                return []
            if self.dialog and self.dialog_next:
                # Ответ LLM: сразу слушаем следующий вопрос, без ww.
                self.dialog_next = False
                self.state = STATE_ASR
                return [self._ui(STATE_WAKE),
                        command(CMD_ACK),
                        command(CMD_ASR_START)]
            return self._return([])
        if kind == ev.BT_MODE:
            if self.state not in (STATE_BASE, STATE_BT_MODE):
                return []
            self._reset_dialog()
            self.return_mode = STATE_BT_MODE
            self.state = STATE_BT_MODE
            return [self._ui(STATE_BT_MODE)]
        if kind == ev.BT_OFF:
            if self.state != STATE_BT_MODE:
                return []
            self._reset_dialog()
            self.return_mode = STATE_BASE
            self.state = STATE_BASE
            return [self._ui(STATE_BASE)]
        if kind == ev.NETWORK_LOST:
            return self._network_lost()
        if kind == ev.NETWORK_OK:
            return self._network_ok()
        if kind == ev.AP_MODE:
            if self.state != STATE_NETLOST:
                return []
            self.state = STATE_APMODE
            return [self._ui(STATE_APMODE),
                    command(CMD_AP, state="start")]
        if kind == ev.AP_STOP:
            return self._network_ok()
        if kind == ev.CANCEL:
            self._reset_dialog()
            if self.state in RETURN_MODES:
                return []
            return self._return([command(CMD_ASR_STOP),
                                 command(CMD_TTS_STOP)])
        if kind == ev.ERROR:
            return self._error(event)
        if kind == ev.ERROR_CLEARED:
            if self.state != STATE_ERROR:
                return []
            commands = []
            return self._return(commands)
        return []

    def handle_all(self, events):
        commands = []
        for event in events:
            commands.extend(self.handle(event))
        return commands

    def _keyword(self, event):
        if self.state == STATE_BASE:
            self.return_mode = STATE_BASE
        elif self.state == STATE_BT_MODE:
            self.return_mode = STATE_BT_MODE
        elif self.state == STATE_SPEAK:
            pass
        else:
            return []
        commands = []
        if self.state == STATE_SPEAK:
            commands.append(command(CMD_TTS_STOP))
        self._bt_suspend(commands)
        self.state = STATE_WAKE
        commands.append(self._ui(STATE_WAKE))
        commands.append(command(CMD_ACK))
        commands.append(command(CMD_ASR_START))
        return commands

    def _network_lost(self):
        if self.state in (STATE_NETLOST, STATE_APMODE):
            return []
        self._reset_dialog()
        if self.state in RETURN_MODES:
            self.network_resume = self.state
        else:
            self.network_resume = STATE_BASE
        self.state = STATE_NETLOST
        return [self._ui(STATE_NETLOST),
                command(CMD_ASR_STOP),
                command(CMD_TTS_STOP)]

    def _network_ok(self):
        if self.state not in (STATE_NETLOST, STATE_APMODE):
            return []
        self._reset_dialog()
        target = self.network_resume
        if target not in RETURN_MODES:
            target = STATE_BASE
        commands = []
        if self.state == STATE_APMODE:
            commands.append(command(CMD_AP, state="stop"))
        self.return_mode = target
        self.state = target
        commands.append(self._ui(target))
        if target == STATE_BT_MODE:
            commands.append(command(CMD_BT_AUDIO, state="resume"))
        return commands

    def _error(self, event):
        self._reset_dialog()
        data = {"message": _get(event, "message", "")}
        recover = _get(event, "recover_ms")
        if recover is not None:
            data["recover_ms"] = recover
        commands = [
            self._ui(STATE_ERROR),
            command(CMD_ASR_STOP),
            command(CMD_TTS_STOP),
            command(CMD_ERROR, **data),
        ]
        self._bt_suspend(commands)
        self.state = STATE_ERROR
        return commands

    def status(self):
        return {
            "state": self.state,
            "return_mode": self.return_mode,
            "network_resume": self.network_resume,
            "dialog": self.dialog,
            "dialog_next": self.dialog_next,
        }
