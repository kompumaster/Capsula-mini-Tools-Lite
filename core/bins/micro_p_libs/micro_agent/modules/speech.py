"""Речь: `micro_ww` ждёт фразу, `micro_asr` распознаёт вопрос.

Микрофон один на процесс, поэтому владение переключается явно:
`ww` слушает → на фразе останавливается → `asr` пишет вопрос →
`ww` снова слушает. Библиотеки импортируются лениво.
"""

from micro_agent.errors import AgentError

DEFAULT_MODEL = "/home/microp/micro_ww/models/hey_jarvis.json"
DEFAULT_MIC_SOURCE = "mics"
DEFAULT_ASR_ENGINE = "yandexv1"
DEFAULT_MAX_SECONDS = 25.0
DEFAULT_ASR_THRESHOLD_DB = -48.0
DEFAULT_ASR_MIN_SPEECH = 0.15
DEFAULT_ASR_SILENCE = 0.8


def _max_seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentError("max_seconds должен быть числом")
    value = float(value)
    if value <= 0:
        raise AgentError("max_seconds должен быть больше нуля")
    return value


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentError("{} должен быть числом".format(name))
    value = float(value)
    if value != value or value < low or value > high:
        raise AgentError("{} вне допустимого диапазона".format(name))
    return value


class Speech:
    """Ключевая фраза и запись вопроса."""

    def __init__(self, ww=None, asr=None, model=DEFAULT_MODEL,
                 mic_source=DEFAULT_MIC_SOURCE,
                 asr_engine=DEFAULT_ASR_ENGINE,
                 max_seconds=DEFAULT_MAX_SECONDS,
                 asr_threshold_db=DEFAULT_ASR_THRESHOLD_DB,
                 asr_min_speech=DEFAULT_ASR_MIN_SPEECH,
                 asr_silence=DEFAULT_ASR_SILENCE,
                 threshold=None, window=None, cooldown_ms=None,
                 ww_factory=None, asr_factory=None):
        self._ww = ww
        self._asr = asr
        self.model = str(model)
        self.mic_source = str(mic_source)
        self.asr_engine = str(asr_engine)
        self.max_seconds = _max_seconds(max_seconds)
        self.asr_threshold_db = _number(
            asr_threshold_db, "asr_threshold_db", -120.0, 0.0)
        self.asr_min_speech = _number(
            asr_min_speech, "asr_min_speech", 0.01, 10.0)
        self.asr_silence = _number(
            asr_silence, "asr_silence", 0.1, 10.0)
        self.threshold = threshold
        self.window = window
        self.cooldown_ms = cooldown_ms
        self._ww_factory = ww_factory
        self._asr_factory = asr_factory
        self._paused = False
        self._opened = False

    def _make_ww(self):
        from micro_ww import WakeWord
        from micro_ww.sources.mic import MicroHalMic
        options = {
            "engine": "microwakeword",
            "model": self.model,
            "mic": lambda: MicroHalMic(source=self.mic_source),
        }
        if self.threshold is not None:
            options["threshold"] = self.threshold
        if self.window is not None:
            options["window"] = self.window
        if self.cooldown_ms is not None:
            options["cooldown_ms"] = self.cooldown_ms
        return WakeWord(**options)

    def _make_asr(self):
        from micro_asr import ASR
        from micro_asr.sources.mic import MicroHalMic
        return ASR(
            engine=self.asr_engine,
            mic=lambda: MicroHalMic(source=self.mic_source,
                                    settle_ms=0))

    def open(self):
        if self._opened:
            return self
        if self._ww is None:
            try:
                self._ww = (self._ww_factory() if self._ww_factory
                            else self._make_ww())
            except Exception as exc:
                raise AgentError("micro_ww: {}".format(exc))
        if self._asr is None:
            try:
                self._asr = (self._asr_factory() if self._asr_factory
                             else self._make_asr())
            except Exception as exc:
                raise AgentError("micro_asr: {}".format(exc))
        self._opened = True
        return self

    def _require(self):
        if not self._opened:
            raise AgentError("речь не открыта")

    def wait_keyword(self, timeout=None):
        """Ждать ключевую фразу; вернуть событие или None."""
        self._require()
        try:
            event = self._ww.listen(timeout=timeout)
        except Exception as exc:
            raise AgentError("ключевое слово: {}".format(exc))
        if event is not None:
            self._ww.stop()
        return event

    def capture(self, max_seconds=None):
        """Записать и распознать вопрос; после — снова слушать фразу."""
        self._require()
        seconds = self.max_seconds if max_seconds is None else _max_seconds(
            max_seconds)
        try:
            text = self._asr.listen(
                max_seconds=seconds,
                threshold_db=self.asr_threshold_db,
                min_speech=self.asr_min_speech,
                until_silence=self.asr_silence)
            if not text:
                status_getter = getattr(self._asr, "status", None)
                if callable(status_getter):
                    try:
                        status = status_getter()
                        print("ASR empty: speech", status.get("speech"),
                              "bytes", status.get("bytes"),
                              "duration", status.get("duration"))
                    except Exception:
                        pass
            return text
        except Exception as exc:
            raise AgentError("распознавание: {}".format(exc))
        finally:
            try:
                self._ww.start()
            except Exception:
                pass

    def stop(self):
        """Остановить ожидание/захват, не закрывая модули."""
        self._require()
        try:
            self._ww.stop()
        except Exception:
            pass
        try:
            self._asr.stop()
        except Exception:
            pass
        return True

    def pause(self):
        """Не слушать ключевую фразу (mute)."""
        self._require()
        try:
            self._ww.stop()
        except Exception as exc:
            raise AgentError("ключевое слово: {}".format(exc))
        self._paused = True
        return True

    def resume(self):
        """Снова слушать ключевую фразу."""
        self._require()
        try:
            self._ww.start()
        except Exception as exc:
            raise AgentError("ключевое слово: {}".format(exc))
        self._paused = False
        return True

    def close(self):
        if not self._opened:
            return True
        try:
            self._ww.close()
        except Exception:
            pass
        try:
            self._asr.close()
        except Exception:
            pass
        self._opened = False
        return True

    def info(self):
        return {
            "opened": self._opened,
            "model": self.model,
            "mic_source": self.mic_source,
            "asr_engine": self.asr_engine,
            "max_seconds": self.max_seconds,
            "asr_threshold_db": self.asr_threshold_db,
            "asr_min_speech": self.asr_min_speech,
            "asr_silence": self.asr_silence,
            "threshold": self.threshold,
            "window": self.window,
            "cooldown_ms": self.cooldown_ms,
        }
