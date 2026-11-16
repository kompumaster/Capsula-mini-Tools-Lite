"""Координатор `WakeWord`: источник, движок, окно и события.

Библиотека не решает, когда слушать. Оркестратор вызывает `start()` и
`poll()`/`listen()`, а после срабатывания сам останавливает прослушивание
и запускает ASR.
"""

from micro_ww.config import Config
from micro_ww.engines.registry import get_engine
from micro_ww.errors import WwError
from micro_ww.window import (
    DEFAULT_CUTOFF, DEFAULT_WINDOW, ProbabilityWindow)

STATE_IDLE = "idle"
STATE_LISTENING = "listening"
STATE_DETECTED = "detected"
STATE_STOPPED = "stopped"
STATE_ERROR = "error"

DEFAULT_STEP_MS = 10


def _now_ms():
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


def _timeout_ms(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WwError("timeout должен быть числом или None")
    value = float(value)
    if value < 0:
        raise WwError("timeout не может быть отрицательным")
    return int(value * 1000)


class WakeWord:
    """Прослушивание микрофона и событие ключевого слова."""

    def __init__(self, engine=None, model=None, sample_rate=None,
                 threshold=None, window=None, cooldown_ms=None,
                 engine_options=None, mic=None):
        self.config = Config(
            engine=engine, model=model, sample_rate=sample_rate,
            threshold=threshold, window=window, cooldown_ms=cooldown_ms,
            engine_options=engine_options)
        self._mic = mic
        self._engine = None
        self._source = None
        self._manifest = None
        self._window = None
        self._state = STATE_IDLE
        self._closed = False
        self._started = False
        self._frames = 0
        self._step_ms = DEFAULT_STEP_MS
        self._last_event = None
        self._error = None

    # --- служебное -------------------------------------------------

    def _check(self):
        if self._closed:
            raise WwError("WakeWord уже закрыт")

    def _ensure_engine(self):
        if self._engine is not None:
            return
        engine = get_engine(self.config.engine)
        try:
            engine.open(
                model=self.config.model,
                sample_rate=self.config.sample_rate,
                **self.config.engine_options)
        except WwError:
            engine.close()
            raise
        except Exception as exc:
            engine.close()
            raise WwError("движок: {}".format(exc))
        self._engine = engine
        self._manifest = getattr(engine, "manifest", None)
        info = engine.info() if hasattr(engine, "info") else {}
        self._step_ms = int(info.get("step_ms", DEFAULT_STEP_MS) or
                            DEFAULT_STEP_MS)
        cutoff = self.config.threshold
        if cutoff is None:
            if self._manifest is not None:
                cutoff = self._manifest.probability_cutoff
            else:
                cutoff = DEFAULT_CUTOFF
        size = self.config.window
        if size is None:
            if self._manifest is not None:
                size = self._manifest.sliding_window_size
            else:
                size = DEFAULT_WINDOW
        self._window = ProbabilityWindow(
            size=size, cutoff=cutoff, cooldown_ms=self.config.cooldown_ms)

    def _ensure_source(self):
        if self._source is not None:
            return
        if self._mic is None:
            raise WwError("нет источника звука; передайте mic=")
        source = self._mic() if callable(self._mic) else self._mic
        if source is None:
            raise WwError("фабрика mic вернула None")
        for name in ("open", "read", "close"):
            if not hasattr(source, name):
                raise WwError("источник не похож на Source")
        source.open()
        self._source = source

    def _process(self, pcm):
        if not isinstance(pcm, (bytes, bytearray)):
            raise WwError("PCM должен быть bytes или bytearray")
        if len(pcm) % 2:
            raise WwError("PCM должен содержать целые 16-битные сэмплы")
        if self._state == STATE_DETECTED:
            return None
        values = self._engine.push(bytes(pcm))
        for value in values:
            self._frames += 1
            now_ms = self._frames * self._step_ms
            result = self._window.push(value, now_ms=now_ms)
            if not result["detected"]:
                continue
            word = (self._manifest.wake_word
                    if self._manifest is not None else "wake")
            event = {
                "detected": True,
                "word": word,
                "probability": value,
                "average": result["average"],
                "frames": self._frames,
                "time_ms": now_ms,
            }
            self._last_event = event
            self._state = STATE_DETECTED
            return event
        return None

    # --- запуск и прослушивание ------------------------------------

    def start(self):
        """Открыть движок и микрофон, начать слушать."""
        self._check()
        if self._started:
            return self
        self._ensure_engine()
        self._ensure_source()
        self._engine.reset()
        self._window.reset()
        self._frames = 0
        self._last_event = None
        self._error = None
        self._started = True
        self._state = STATE_LISTENING
        return self

    def poll(self):
        """Один шаг: прочитать окно микрофона и обработать его."""
        self._check()
        if not self._started:
            raise WwError("WakeWord не запущен")
        if self._source is None:
            raise WwError("нет источника звука")
        if self._state == STATE_DETECTED:
            return None
        return self._process(self._source.read())

    def listen(self, timeout=None):
        """Блокирующий цикл до события или таймаута."""
        self._check()
        if not self._started:
            self.start()
        deadline = None
        if timeout is not None:
            limit = _timeout_ms(timeout)
            deadline = _now_ms() + limit
        while True:
            event = self.poll()
            if event is not None:
                return event
            if deadline is not None and _now_ms() >= deadline:
                return None

    def feed(self, pcm):
        """Офлайн: обработать готовый PCM без источника."""
        self._check()
        self._ensure_engine()
        return self._process(pcm)

    def reset(self):
        """Сбросить модель и окно, не закрывая источник."""
        self._check()
        if self._engine is None:
            raise WwError("движок не открыт")
        self._engine.reset()
        self._window.reset()
        self._frames = 0
        self._last_event = None
        self._error = None
        self._state = STATE_LISTENING if self._started else STATE_IDLE
        return True

    def stop(self):
        """Остановить прослушивание; движок остаётся открытым."""
        self._check()
        was_started = self._started
        if self._source is not None:
            try:
                self._source.close()
            finally:
                self._source = None
        self._started = False
        if self._state != STATE_ERROR:
            self._state = STATE_STOPPED
        return was_started

    def close(self):
        """Остановить всё и закрыть движок."""
        if self._closed:
            return True
        try:
            self.stop()
        finally:
            if self._engine is not None:
                try:
                    self._engine.close()
                except Exception:
                    pass
            self._engine = None
            self._window = None
            self._closed = True
        return True

    # --- состояние -------------------------------------------------

    def status(self):
        self._check()
        source = None
        if self._source is not None:
            try:
                source = self._source.info()
            except Exception:
                source = None
        return {
            "state": self._state,
            "started": self._started,
            "closed": self._closed,
            "engine": self._engine.name if self._engine else None,
            "model": self.config.model,
            "wake_word": (self._manifest.wake_word
                          if self._manifest is not None else None),
            "threshold": (self._window.cutoff
                          if self._window is not None else None),
            "window": (self._window.size
                       if self._window is not None else None),
            "cooldown_ms": self.config.cooldown_ms,
            "frames": self._frames,
            "last_event": dict(self._last_event)
            if self._last_event is not None else None,
            "source": source,
            "error": self._error,
        }

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
