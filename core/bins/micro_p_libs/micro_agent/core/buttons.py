"""Правила кнопок: событие + состояние → действие агента.

Здесь нет железа и сервисов: только чистая логика, поэтому матрица
проверяется на хосте.
"""

DEFAULT_VOLUME_STEP = 5

# Действия, которые понимает агент.
VOLUME = "volume"
LISTEN = "listen"
TTS_TOGGLE = "tts_toggle"
BT_TOGGLE = "bt_toggle"
BT_NEXT = "bt_next"
BT_PREV = "bt_prev"
MIC_TOGGLE = "mic_toggle"


class ButtonRouter:
    """Переводит события клавиш в действия."""

    def __init__(self, volume_step=DEFAULT_VOLUME_STEP):
        if isinstance(volume_step, bool) or not isinstance(
                volume_step, int):
            raise ValueError("volume_step должен быть целым числом")
        if volume_step < 1 or volume_step > 50:
            raise ValueError("volume_step должен быть в 1…50")
        self.volume_step = volume_step

    def route(self, events, context=None):
        """События клавиш → список действий."""
        context = context or {}
        playing = bool(context.get("tts_playing"))
        bt_audio = bool(context.get("bt_audio"))
        muted = bool(context.get("muted"))
        actions = []
        for event in events or ():
            if not event:
                continue
            name = event[0]
            action = event[1] if len(event) > 1 else ""
            if name in ("vol+", "vol-"):
                if action not in ("press", "step"):
                    continue
                step = self.volume_step
                actions.append((VOLUME, step if name == "vol+" else -step))
                continue
            if name == "mic":
                if action == "click":
                    actions.append((MIC_TOGGLE,))
                continue
            if name == "circle":
                if action == "click" and not muted:
                    actions.append((LISTEN,))
                continue
            if name == "play":
                if action != "click" or muted:
                    continue
                if playing:
                    actions.append((TTS_TOGGLE,))
                elif bt_audio:
                    actions.append((BT_TOGGLE,))
                continue
            if name == "circle+vol+" or name == "circle+vol-":
                if action != "combo_hold" or muted or not bt_audio:
                    continue
                actions.append(
                    (BT_NEXT if name == "circle+vol+" else BT_PREV,))
                continue
        return actions
