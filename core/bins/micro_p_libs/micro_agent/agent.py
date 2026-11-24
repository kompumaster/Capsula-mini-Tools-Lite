"""Точка входа micro_agent: цикл, машина состояний, модули.

Скелет: агент опрашивает модули, собирает события и получает команды
от машины состояний. Модули подключаются позже; железо здесь не
трогается.
"""

from micro_agent.commands import CommandContext, parse as parse_command
from micro_agent.config import Config
from micro_agent.core import events as ev
from micro_agent.core.buttons import (
    BT_NEXT, BT_PREV, BT_TOGGLE, LISTEN, MIC_TOGGLE, TTS_TOGGLE, VOLUME,
    ButtonRouter)
from micro_agent.core.events import Event
from micro_agent.core.loop import Loop
from micro_agent.core.state import (CMD_ERROR, STATE_ASR, STATE_BASE,
                                    STATE_BT_MODE, STATE_SPEAK,
                                    StateMachine)

ERROR_RECOVER_MS = 5000
ERROR_TASK = "error-recovery"


def _clock_ms():
    try:
        import time
    except ImportError:
        return 0
    ticks = getattr(time, "ticks_ms", None)
    if ticks is not None:
        return int(ticks())
    monotonic = getattr(time, "monotonic", None)
    if monotonic is not None:
        return int(monotonic() * 1000)
    return 0


def _sleep_ms(value):
    try:
        import time
    except ImportError:
        return
    sleep_ms = getattr(time, "sleep_ms", None)
    if sleep_ms is not None:
        sleep_ms(int(value))
        return
    sleep = getattr(time, "sleep", None)
    if sleep is not None:
        sleep(max(0, int(value)) / 1000.0)


class Agent:
    """Оркестратор: модули → события → состояния → команды."""

    def __init__(self, config=None, loop=None, state=None):
        self.config = config if config is not None else Config()
        self.loop = loop if loop is not None else Loop()
        self.state = state if state is not None else StateMachine()
        self.last_events = []
        self.last_commands = []
        self.handlers = {}
        self.pending = []
        self.services = {}
        self.command_context = None
        self.router = None
        self.muted = False
        self._mute_return = "base"
        self._tts_paused = False
        self._now_ms = 0
        self._closed = False

    def _check(self):
        if self._closed:
            raise RuntimeError("агент уже закрыт")

    def add(self, module):
        self._check()
        return self.loop.add(module)

    def remove(self, module):
        self._check()
        return self.loop.remove(module)

    def on(self, name, handler):
        """Обработчик команды состояния (по имени)."""
        if not callable(handler):
            raise ValueError("обработчик не вызывается")
        self.handlers[name] = handler
        return handler

    def post(self, event):
        """Положить событие в очередь следующего шага."""
        self._check()
        self.pending.append(event)
        return event

    def _schedule_error_recovery(self, data):
        """Запланировать возврат из ERROR; 0/None - не возвращаться."""
        scheduler = self.loop.scheduler
        scheduler.cancel(ERROR_TASK)
        delay = data.get("recover_ms")
        if isinstance(delay, bool) or not isinstance(delay, int) or delay <= 0:
            return
        scheduler.after(
            self._now_ms + delay,
            lambda: Event(ev.ERROR_CLEARED),
            name=ERROR_TASK)
        print("RECOVER in", delay)

    def _dispatch(self, commands):
        for item in commands:
            if item["name"] == CMD_ERROR:
                self._schedule_error_recovery(item.get("data") or {})
            handler = self.handlers.get(item["name"])
            if handler is None:
                continue
            try:
                handler(item.get("data") or {})
            except Exception as exc:
                self.post(Event(ev.ERROR, message=str(exc),
                                recover_ms=ERROR_RECOVER_MS))

    def _commands_for(self, event):
        """Прямая команда из ASR-текста вместо вопроса LLM."""
        if (self.command_context is None
                or not hasattr(event, "kind")
                or event.kind != ev.UTTERANCE):
            return None
        command = parse_command(event.get("text", ""))
        if command is None:
            return None
        print("COMMAND", command.name)
        try:
            command.run(self.command_context)
        except Exception as exc:
            return Event(ev.ERROR, message=str(exc),
                         recover_ms=ERROR_RECOVER_MS)
        mode = None
        if command.name == "bluetooth.on":
            mode = STATE_BT_MODE
        elif command.name == "bluetooth.off":
            mode = STATE_BASE
        return Event(ev.COMMAND_EXECUTED, ack=command.ack(), mode=mode)

    def handle(self, events):
        """Разобрать готовые события; вернуть команды."""
        self._check()
        if isinstance(events, Event):
            events = [events]
        else:
            events = list(events or [])
        incoming = self.pending + events
        self.pending = []
        prepared = []
        for event in incoming:
            replacement = self._commands_for(event)
            prepared.append(event if replacement is None else replacement)
        self.last_events = prepared
        for event in prepared:
            if getattr(event, "kind", None) == ev.ERROR_CLEARED:
                print("RECOVERED")
        was_dialog = self.state.dialog
        self.last_commands = self.state.handle_all(prepared)
        if was_dialog and not self.state.dialog:
            print("DIALOG end")
        self._dispatch(self.last_commands)
        return self.last_commands

    def attach(self, ui=None, audio=None, speech=None, tts=None,
               assistant=None, network=None, web=None, buttons=None,
               router=None):
        """Подключить сервисы и их обработчики команд."""
        if buttons is not None:
            self.services["buttons"] = buttons
        if router is not None:
            self.router = router
        if ui is not None:
            self.services["ui"] = ui
            self.add(ui)
            self.on("ui", lambda data: ui.show(data.get("mode")))
        if audio is not None:
            self.services["audio"] = audio
            self.on("ack", lambda data: audio.ack())
            self.on("bt_audio", lambda data: self._bt_audio_state(audio, data))
            if callable(getattr(audio, "poll", None)):
                self.add(audio)
        if speech is not None:
            self.services["speech"] = speech
            self.on("asr_start", lambda data: self._start_asr(speech))
            self.on("asr_stop", lambda data: speech.stop())
        if tts is not None:
            self.services["tts"] = tts
            self.add(tts)
            self.on("speak", lambda data: self._speak(tts, data))
            self.on("tts_stop", lambda data: self._tts_stop(tts))
        if assistant is not None:
            self.services["assistant"] = assistant
            self.on("think", lambda data: self._think(assistant, data))
        if network is not None:
            self.services["network"] = network
            self.add(network)
            self.on("ap", lambda data: self._ap(network, data))
        if web is not None:
            self.services["web"] = web
            self.add(web)
        if audio is not None or ui is not None:
            self.command_context = CommandContext(audio=audio, ui=ui)
        return self

    def _start_asr(self, speech):
        if self.state.dialog and self.state.state == STATE_ASR:
            print("DIALOG ask")
        # Микрофон один: сначала освобождаем его от wake word.
        try:
            speech.stop()
        except Exception:
            pass
        # Затем переводим состояние в ASR и делаем блокирующий захват.
        self.post(Event(ev.ASR_STARTED))
        try:
            text = speech.capture()
        except Exception as exc:
            self.post(Event(ev.ERROR, message=str(exc),
                            recover_ms=ERROR_RECOVER_MS))
            return
        if text:
            print("ASR:", text)
            print("ASR text", len(text))
            self.post(Event(ev.UTTERANCE, text=text))
        else:
            print("ASR empty")
            self.post(Event(ev.UTTERANCE_EMPTY))

    def _think(self, assistant, data):
        try:
            answer = assistant.ask(data.get("text", ""))
        except Exception as exc:
            self.post(Event(ev.ERROR, message=str(exc),
                            recover_ms=ERROR_RECOVER_MS))
            return
        self.post(Event(ev.ANSWER, text=answer or ""))

    def _speak(self, tts, data):
        text = data.get("text", "")
        if not text:
            self.post(Event(ev.TTS_FINISHED))
            return
        self._tts_paused = False
        try:
            print("SPEAK", len(text))
            tts.say(text, cache=data.get("cache"))
        except Exception as exc:
            print("TTS error", type(exc).__name__, str(exc))
            self.post(Event(ev.ERROR, message=str(exc),
                            recover_ms=ERROR_RECOVER_MS))

    def _bt_audio_state(self, audio, data):
        try:
            if data.get("state") == "suspend":
                audio.bt_suspend()
            else:
                audio.bt_resume()
        except Exception as exc:
            self.post(Event(ev.ERROR, message=str(exc),
                            recover_ms=ERROR_RECOVER_MS))

    def _ap(self, network, data):
        try:
            if data.get("state") == "start":
                network.start_ap()
            else:
                network.stop_ap()
        except Exception as exc:
            self.post(Event(ev.ERROR, message=str(exc),
                            recover_ms=ERROR_RECOVER_MS))

    def _poll_buttons(self):
        """Кнопки - до всего остального: работают в любом режиме."""
        buttons = self.services.get("buttons")
        if buttons is None or self.router is None:
            return []
        try:
            events = buttons.poll(self._now_ms)
        except Exception as exc:
            print("BUTTONS error", type(exc).__name__, str(exc))
            return []
        actions = self.router.route(events, self._button_context())
        for action in actions:
            try:
                self._run_action(action)
            except Exception as exc:
                print("BUTTONS action", action, type(exc).__name__, str(exc))
        return actions

    def _button_context(self):
        tts = self.services.get("tts")
        playing = False
        if tts is not None:
            try:
                playing = bool(tts.busy())
            except Exception:
                playing = False
        return {
            "state": self.state.state,
            "tts_playing": playing,
            "bt_audio": self._bt_audio(),
            "muted": self.muted,
        }

    def _tts_stop(self, tts):
        self._tts_paused = False
        return tts.stop()

    def _bt_audio(self):
        audio = self.services.get("audio")
        getter = getattr(audio, "bt_audio", None)
        if not callable(getter):
            return False
        try:
            return bool(getter())
        except Exception:
            return False

    def _run_action(self, action):
        kind = action[0]
        if kind == VOLUME:
            self._change_volume(action[1])
        elif kind == LISTEN:
            self._start_listening()
        elif kind == TTS_TOGGLE:
            self._toggle_tts()
        elif kind == BT_TOGGLE:
            self._bt_media("play_pause")
        elif kind == BT_NEXT:
            self._bt_media("next")
        elif kind == BT_PREV:
            self._bt_media("previous")
        elif kind == MIC_TOGGLE:
            self._set_muted(not self.muted)

    def _change_volume(self, step):
        audio = self.services.get("audio")
        if audio is None:
            return None
        try:
            if step > 0:
                percent = audio.volume_up()
            else:
                percent = audio.volume_down()
        except Exception as exc:
            print("VOLUME error", type(exc).__name__, str(exc))
            return None
        ui = self.services.get("ui")
        if ui is not None:
            try:
                ui.show_volume(percent)
            except Exception as exc:
                print("VOLUME ui", type(exc).__name__, str(exc))
        return percent

    def _toggle_tts(self):
        tts = self.services.get("tts")
        if tts is None:
            return False
        try:
            if self._tts_paused:
                tts.resume()
                self._tts_paused = False
            else:
                tts.pause()
                self._tts_paused = True
        except Exception as exc:
            print("TTS toggle", type(exc).__name__, str(exc))
            return False
        return True

    def _bt_media(self, name):
        try:
            from micro_hal import lib_bt
        except Exception as exc:
            print("BT media", type(exc).__name__, str(exc))
            return False
        function = getattr(lib_bt, name, None)
        if not callable(function):
            print("BT media: нет AVRCP")
            return False
        try:
            function()
        except Exception as exc:
            print("BT media", name, type(exc).__name__, str(exc))
            return False
        return True

    def _start_listening(self):
        """Сбросить сценарий и начать новый (как ключевая фраза)."""
        self.post(Event(ev.CANCEL))
        self.post(Event(ev.KEYWORD_DETECTED))

    def _set_muted(self, muted):
        if muted == self.muted:
            return self.muted
        speech = self.services.get("speech")
        ui = self.services.get("ui")
        if muted:
            if self.state.state in (STATE_BASE, STATE_BT_MODE):
                self._mute_return = self.state.state
            else:
                self._mute_return = STATE_BASE
            self.post(Event(ev.CANCEL))
            self.muted = True
            if speech is not None:
                try:
                    speech.pause()
                except Exception as exc:
                    print("MUTE speech", type(exc).__name__, str(exc))
            self._source_mute(True)
            if ui is not None:
                try:
                    ui.show("muted")
                    ui.show_face("flat")
                except Exception as exc:
                    print("MUTE ui", type(exc).__name__, str(exc))
        else:
            self.muted = False
            self._source_mute(False)
            if speech is not None:
                try:
                    speech.resume()
                except Exception as exc:
                    print("MUTE speech", type(exc).__name__, str(exc))
            if ui is not None:
                try:
                    ui.show(self._mute_return)
                except Exception as exc:
                    print("MUTE ui", type(exc).__name__, str(exc))
        return self.muted

    def _source_mute(self, on):
        try:
            from micro_hal import hal_mic
            hal_mic.set_mute(on)
        except Exception as exc:
            print("MUTE pactl", type(exc).__name__, str(exc))

    def _poll_keyword(self, now_ms):
        if self.muted:
            return
        speech = self.services.get("speech")
        if speech is None:
            return
        if self.state.state not in (STATE_BASE, STATE_BT_MODE, STATE_SPEAK):
            return
        wait = getattr(speech, "wait_keyword", None)
        if not callable(wait):
            return
        try:
            event = wait(timeout=0)
        except Exception as exc:
            self.post(Event(ev.ERROR, message=str(exc),
                            recover_ms=ERROR_RECOVER_MS))
            return
        if event is not None:
            print("WAKE")
            self.post(Event(ev.KEYWORD_DETECTED))

    def tick(self, now_ms):
        """Один шаг: кнопки, модули и события."""
        self._check()
        self._now_ms = int(now_ms)
        if self.command_context is not None:
            self.command_context.now_ms = int(now_ms)
        self._poll_buttons()
        self._poll_keyword(now_ms)
        commands = self.handle(self.loop.poll(now_ms))
        web = self.services.get("web")
        if web is not None:
            update = getattr(web, "update", None)
            if callable(update):
                try:
                    update(self.status())
                except Exception:
                    pass
        return commands

    def run(self, clock=None, sleep_ms=None, should_stop=None,
            max_steps=None):
        """Цикл до остановки или `max_steps` шагов."""
        self._check()
        clock = clock if clock is not None else _clock_ms
        sleep_ms = sleep_ms if sleep_ms is not None else _sleep_ms
        steps = 0
        while True:
            now = clock()
            self.tick(now)
            if should_stop is not None and should_stop():
                break
            steps += 1
            if max_steps is not None and steps >= max_steps:
                break
            delay = self.loop.scheduler.next_delay(clock())
            if delay is None:
                delay = self.config.tick_ms
            if delay > self.config.tick_ms:
                delay = self.config.tick_ms
            sleep_ms(delay)

    def status(self):
        self._check()
        return {
            "config": self.config.as_dict(),
            "state": self.state.status(),
            "modules": len(self.loop.modules),
            "events": len(self.last_events),
            "commands": len(self.last_commands),
            "handlers": sorted(self.handlers.keys()),
            "services": sorted(self.services.keys()),
            "pending": len(self.pending),
            "closed": self._closed,
        }

    def close(self):
        if self._closed:
            return True
        for name in ("buttons", "web", "network", "tts", "speech",
                     "audio", "ui"):
            service = self.services.get(name)
            if service is not None:
                try:
                    service.close()
                except Exception:
                    pass
        self._closed = True
        return True


def build_ui(settings):
    """Создать UDP-клиент micro_ui по настройкам [ui]."""
    from micro_agent.modules.ui_client import UiClient
    return UiClient(
        host=settings.get("ui", "host") or "127.0.0.1",
        port=settings.get_int("ui", "port", 1, 65535),
        sync_ms=settings.get_int("ui", "sync_ms", 1),
        date_ms=settings.get_int("ui", "date_seconds", 1, 3600) * 1000,
        volume_ms=settings.get_int("ui", "volume_ms", 1),
        display_brightness=settings.get_int(
            "ui", "display_brightness", 0, 100),
        ring_brightness=settings.get_int(
            "ui", "ring_brightness", 0, 100),
        global_brightness=settings.get_int(
            "ui", "global_brightness", 0, 100),
        auto_brightness=settings.get_bool(
            "ui", "auto_brightness", False))


TTS_EMOTIONS = ("neutral", "good", "evil")
TTS_RATES = (8000, 16000, 48000)


def build_tts_options(settings):
    """Параметры движка синтеза из настроек `[tts]`."""
    emotion = (settings.get("tts", "emotion") or "neutral").strip().lower()
    if emotion not in TTS_EMOTIONS:
        emotion = "neutral"
    sample_rate = settings.get_int("tts", "sample_rate", 8000, 48000)
    if sample_rate not in TTS_RATES:
        sample_rate = 16000
    return {
        "emotion": emotion,
        "speed": settings.get_float("tts", "speed", 0.1, 3.0),
        "lang": settings.get("tts", "lang") or "ru-RU",
        "sample_rate": sample_rate,
    }


AGE_LIMIT_TEMPLATE = (
    "Ты разговариваешь с детьми {} лет: говори понятно и по-доброму,\n"
    "но речь сильно не упрощай и не сюсюкай.\n"
    "Острые темы и темы для взрослых обходи: мягко переводи разговор\n"
    "на другое или коротко скажи, что это не для детей."
)
SYSTEM_LIMIT = 2000


def age_limit_prefix(age):
    """Блок про детей для промпта; пусто - ограничения нет."""
    if age is None or age >= 18:
        return ""
    return AGE_LIMIT_TEMPLATE.format(int(age))


def build_llm(settings):
    """Создать клиент LLM по настройкам `[llm]` и `[agent] age_limit`."""
    from micro_llm import LlmClient
    from micro_llm.text.system import load_system

    path = settings.get("llm", "system_file") or "/home/system.txt"
    age = settings.get_int("agent", "age_limit", 1, 120)
    prefix = age_limit_prefix(age)
    limit = SYSTEM_LIMIT
    if prefix:
        limit = max(1, SYSTEM_LIMIT - len(prefix) - 2)
    system = load_system(path, limit)
    if prefix and system:
        system = prefix + "\n\n" + system
    return LlmClient(
        engine=settings.get("llm", "engine") or "openai",
        system=system, system_file=None,
        ttl_ms=settings.get_int(
            "llm", "session_ttl_seconds", 1, 86400) * 1000,
        max_turns=settings.get_int("llm", "max_turns", 0, 100),
        max_chars=settings.get_int("llm", "max_chars", 0, 100000))


def build_llm_options(settings):
    """Параметры движка LLM из настроек `[llm]`."""
    return {
        "max_tokens": settings.get_int(
            "llm", "max_tokens", 1, 384000),
        "temperature": settings.get_float(
            "llm", "temperature", 0.0, 2.0),
        "thinking": settings.get_bool("llm", "thinking", False),
        "timeout": settings.get_int(
            "llm", "timeout_ms", 1000, 120000) / 1000.0,
    }


def build_state(settings):
    """Машина состояний: режим диалога из `[agent] dialog`."""
    return StateMachine(dialog=settings.get_bool("agent", "dialog"))


def build_speech(settings, config=None):
    """Речь: `[ww]` - фраза, `[asr]` - запись вопроса, `[agent]` - предел."""
    from micro_agent.modules.speech import Speech
    config = config if config is not None else settings.agent_config()
    return Speech(
        model=settings.get("ww", "model"),
        threshold=settings.get_float("ww", "threshold", 0.0, 1.0),
        window=settings.get_int("ww", "window", 1, 1000),
        cooldown_ms=settings.get_int("ww", "cooldown_ms", 0),
        mic_source=config.mic_source,
        max_seconds=config.max_utterance,
        asr_engine=settings.get("asr", "engine") or "yandexv1",
        asr_threshold_db=settings.get_float(
            "asr", "threshold_db", -120.0, 0.0),
        asr_min_speech=settings.get_float(
            "asr", "min_speech", 0.01, 10.0),
        asr_silence=settings.get_float("asr", "silence", 0.1, 10.0))


def build_buttons(settings):
    """Кнопки по настройкам `[keys]`; выключены - `None`."""
    if not settings.get_bool("keys", "enabled", True):
        return None
    from micro_agent.modules.buttons import Buttons
    return Buttons(
        debounce=settings.get_int("keys", "debounce_ms", 0, 1000),
        hold=settings.get_int("keys", "hold_ms", 0, 10000),
        click=settings.get_int("keys", "click_ms", 0, 5000),
        combo=settings.get_int("keys", "combo_ms", 0, 1000),
        combo_hold=settings.get_int(
            "keys", "combo_hold_ms", 0, 10000),
        step=settings.get_int("keys", "step_ms", 1, 5000))


def build_router(settings):
    """Правила кнопок (шаг громкости из `[keys]`)."""
    return ButtonRouter(
        volume_step=settings.get_int("keys", "volume_step", 1, 50))


def make_volume_saver(settings):
    """Функция для `Audio`: пишет громкость в `[audio] last_volume`."""
    def save(percent):
        try:
            if settings.get("audio", "last_volume") == str(percent):
                return
            settings.set("audio", "last_volume", percent)
            settings.save()
            print("VOLUME save", percent)
        except Exception as exc:
            print("VOLUME save", type(exc).__name__, str(exc))
    return save


def apply_saved_volume(audio, settings):
    """Поставить громкость из `[audio] last_volume` при старте."""
    raw = settings.get("audio", "last_volume")
    value = settings.last_volume()
    if value is None:
        if raw is not None and str(raw).strip() != "":
            print("VOLUME restore: неверное значение", raw)
        return None
    try:
        audio.set_volume(value)
    except Exception as exc:
        print("VOLUME restore", type(exc).__name__, str(exc))
        return None
    print("VOLUME restore", value)
    return value


def main():
    from micro_agent.adapters.assistant import EchoAssistant, LlmAssistant
    from micro_agent.modules.audio import Audio
    from micro_agent.modules.net import Network
    from micro_agent.modules.tts import Tts
    from micro_agent.settings import Settings

    settings = Settings.load()
    if not settings.loaded:
        try:
            settings.save()
        except Exception as exc:
            print("settings save:", exc)
    for problem in settings.errors:
        print("settings:", problem)
    config = settings.agent_config()

    ui = build_ui(settings)
    audio = Audio(save_ms=settings.get_int("audio", "save_ms", 100, 60000))
    speech = build_speech(settings, config)
    print("WW threshold", speech.threshold,
          "window", speech.window,
          "cooldown", speech.cooldown_ms)
    print("ASR", speech.asr_engine,
          "threshold", speech.asr_threshold_db,
          "min_speech", speech.asr_min_speech,
          "silence", speech.asr_silence)
    tts = Tts(
        engine=settings.get("tts", "engine") or "edge",
        voice=settings.get("tts", "voice") or None,
        cache_dir="/home/microp/tts_cache",
        cache=settings.get_bool("tts", "cache", False),
        options=build_tts_options(settings))
    network = Network(
        interval_ms=config.watchdog_ms,
        ap_after_ms=config.ap_after_ms)

    ui.open()
    audio.open()
    audio.set_store(make_volume_saver(settings))
    apply_saved_volume(audio, settings)
    speech.open()
    tts.open()
    network.open()

    buttons = build_buttons(settings)
    if buttons is not None:
        try:
            buttons.open()
            print("KEYS combo_hold", buttons.info()["combo_hold"])
        except Exception as exc:
            print("Кнопки недоступны:", exc)
            buttons = None
    router = build_router(settings)

    llm = build_llm(settings)
    assistant = EchoAssistant(delay=0)
    try:
        llm.open(**build_llm_options(settings))
        assistant = LlmAssistant(llm)
        print("LLM", llm.info()["model"],
              "ttl", settings.get_int(
                  "llm", "session_ttl_seconds", 1, 86400), "с")
    except Exception as exc:
        print("LLM недоступен:", exc)

    state = build_state(settings)
    print("DIALOG", "on" if state.dialog else "off")
    print("AGE limit", settings.get_int("agent", "age_limit", 1, 120))
    agent = Agent(config=config, state=state)
    agent.attach(ui=ui, audio=audio, speech=speech, tts=tts,
                 assistant=assistant, network=network,
                 buttons=buttons, router=router)
    agent.on("error", lambda data: print(
        "AGENT ERROR", data.get("message")))

    print("READY")
    try:
        agent.run()
    except KeyboardInterrupt:
        pass
    finally:
        print("STOP")
        agent.close()


if __name__ == "__main__":
    main()
