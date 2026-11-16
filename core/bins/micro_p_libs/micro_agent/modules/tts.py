"""Синтез и воспроизведение ответа через `micro_tts`.

Политика повторов: всего 3 попытки, пауза 5 с. После двух неудач
движок пересоздаётся (новое соединение/сессия), затем ещё одна
попытка. Токен `Sec-MS-GEC` считается на каждый запрос.
"""

import time

from micro_agent.core.events import ERROR, Event, TTS_FINISHED
from micro_agent.errors import AgentError

DEFAULT_ATTEMPTS = 3
DEFAULT_RENEW_AFTER = 2
DEFAULT_DELAY = 5.0
DEFAULT_RECOVER_MS = 5000
# По умолчанию весь ответ уходит одним запросом. `chunk_chars` нужен
# только как запасной вариант для split=True.
DEFAULT_SPLIT = False
DEFAULT_CHUNK_CHARS = 90


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AgentError("{} должен быть положительным целым".format(name))
    return value


def _delay(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentError("retry_delay должен быть числом")
    value = float(value)
    if value < 0:
        raise AgentError("retry_delay не может быть отрицательным")
    return value


def _flag(value, name):
    if not isinstance(value, bool):
        raise AgentError("{} должен быть True или False".format(name))
    return value


class Tts:
    """Обёртка над `micro_tts.TTS` для цикла агента."""

    def __init__(self, tts=None, engine="edge", voice=None,
                 cache_dir=None, tts_factory=None,
                 attempts=DEFAULT_ATTEMPTS,
                 renew_after=DEFAULT_RENEW_AFTER,
                 retry_delay=DEFAULT_DELAY,
                 split=DEFAULT_SPLIT,
                 chunk_chars=DEFAULT_CHUNK_CHARS, cache=False,
                 recover_ms=DEFAULT_RECOVER_MS, options=None,
                 sleep=None):
        self._tts = tts
        self.engine = engine
        self.voice = voice
        self.cache_dir = cache_dir
        self._factory = tts_factory
        self.options = dict(options or {})
        self.attempts = _positive_int(attempts, "attempts")
        self.renew_after = _positive_int(renew_after, "renew_after")
        self.retry_delay = _delay(retry_delay)
        self.split = _flag(split, "split")
        self.chunk_chars = _positive_int(chunk_chars, "chunk_chars")
        self.cache = _flag(cache, "cache")
        self.recover_ms = _positive_int(recover_ms, "recover_ms")
        self._sleep = sleep if sleep is not None else time.sleep
        self._active = False
        self._opened = False

    def _make(self):
        if self._factory is not None:
            return self._factory()
        try:
            from micro_tts import TTS
        except Exception as exc:
            raise AgentError("micro_tts: {}".format(exc))
        kwargs = {
            "engine": self.engine,
            "voice": self.voice,
            "split": self.split,
            "chunk_chars": self.chunk_chars,
            "cache": self.cache,
            "options": self._options(),
        }
        if self.cache_dir is not None:
            kwargs["cache_dir"] = self.cache_dir
        try:
            return TTS(**kwargs)
        except Exception as exc:
            raise AgentError("micro_tts: {}".format(exc))

    def _options(self):
        """Параметры движка: повторы - на агенте, остальное - из настроек."""
        result = {"retries": 0, "retry_delay": 0}
        result.update(self.options)
        return result

    def open(self):
        if self._opened:
            return self
        if self._tts is None:
            self._tts = self._make()
        self._opened = True
        return self

    def _require(self):
        if not self._opened:
            raise AgentError("TTS не открыт")

    def _renew(self):
        old = self._tts
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        self._tts = self._make()
        self._active = False
        return self._tts

    def say(self, text, cache=None):
        self._require()
        last = None
        for attempt in range(1, self.attempts + 1):
            try:
                # Новый ответ заменяет предыдущий, а не ждёт его конца.
                try:
                    if self._tts.playing():
                        self._tts.stop()
                except Exception:
                    pass
                self._tts.say(text, wait=False, cache=cache)
                self._active = True
                return True
            except Exception as exc:
                last = exc
                if attempt >= self.attempts:
                    break
                if attempt == self.renew_after:
                    try:
                        self._renew()
                    except Exception as renew_exc:
                        last = renew_exc
                        break
                if self.retry_delay:
                    self._sleep(self.retry_delay)
        raise AgentError("TTS: {} (попыток {})".format(
            last, self.attempts))

    def stop(self):
        self._require()
        try:
            self._tts.stop()
        except Exception as exc:
            raise AgentError("TTS: {}".format(exc))
        self._active = False
        return True

    def pause(self):
        self._require()
        try:
            self._tts.pause()
        except Exception as exc:
            raise AgentError("TTS: {}".format(exc))
        return True

    def resume(self):
        self._require()
        try:
            self._tts.resume()
        except Exception as exc:
            raise AgentError("TTS: {}".format(exc))
        return True

    def busy(self):
        if not self._opened:
            return False
        try:
            return bool(self._tts.playing())
        except Exception:
            return False

    def _take_error(self):
        """Забрать ошибку воспроизведения у `micro_tts`, если она есть."""
        getter = getattr(self._tts, "take_error", None)
        if not callable(getter):
            return None
        try:
            message = getter()
        except Exception:
            return None
        if isinstance(message, str) and message.strip():
            return message
        return None

    def poll(self, now_ms):
        if self._active and not self.busy():
            self._active = False
            message = self._take_error()
            if message:
                print("TTS playback error", message)
                return [Event(ERROR, message="TTS: " + message,
                              recover_ms=self.recover_ms)]
            return [Event(TTS_FINISHED)]
        return []

    def close(self):
        if not self._opened:
            return True
        try:
            self._tts.close()
        except Exception:
            pass
        self._opened = False
        self._active = False
        return True

    def info(self):
        return {
            "engine": self.engine,
            "voice": self.voice,
            "split": self.split,
            "chunk_chars": self.chunk_chars,
            "cache": self.cache,
            "active": self._active,
            "opened": self._opened,
            "attempts": self.attempts,
            "renew_after": self.renew_after,
            "recover_ms": self.recover_ms,
        }
