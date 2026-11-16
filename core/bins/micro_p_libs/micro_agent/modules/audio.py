"""Звук: громкость, Bluetooth-аудио и короткий сигнал.

`micro_hal` подключается только в `open()`. Bluetooth-аудио можно
приостановить, не разрывая соединение: `bt_suspend()`/`bt_resume()`.

Громкость запоминается: после изменения и `save_ms` простоя модуль
отдаёт значение в `store()` (агент пишет его в `[audio] last_volume`).
"""

from micro_agent.errors import AgentError

SAVE_MS = 5000


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


def _percent(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentError("громкость должна быть целым числом")
    if value < 0 or value > 100:
        raise AgentError("громкость должна быть в 0…100")
    return value


class Audio:
    """Выход и громкость колонки."""

    def __init__(self, volume=None, bt=None, speaker=None,
                 save_ms=SAVE_MS, clock=None):
        self._volume = volume
        self._bt = bt
        self._speaker = speaker
        if isinstance(save_ms, bool) or not isinstance(save_ms, int):
            raise AgentError("save_ms должен быть целым числом")
        if save_ms < 0:
            raise AgentError("save_ms не может быть отрицательным")
        self.save_ms = save_ms
        self._clock = clock if clock is not None else _clock_ms
        self._store = None
        self._pending = None
        self._changed_ms = 0
        self._opened = False

    def open(self):
        if self._opened:
            return self
        if self._volume is None:
            try:
                from micro_hal import lib_volume
                self._volume = lib_volume.Volume()
            except Exception as exc:
                raise AgentError("громкость недоступна: {}".format(exc))
        if self._bt is None:
            try:
                from micro_hal import lib_bt
                self._bt = lib_bt
            except Exception as exc:
                raise AgentError("Bluetooth недоступен: {}".format(exc))
        if self._speaker is None:
            try:
                from micro_hal import lib_speaker
                self._speaker = lib_speaker
            except Exception as exc:
                raise AgentError("динамик недоступен: {}".format(exc))
        self._opened = True
        return self

    def _require(self):
        if not self._opened:
            raise AgentError("звук не открыт")

    def volume(self):
        self._require()
        try:
            return self._volume.get()
        except Exception as exc:
            raise AgentError("громкость: {}".format(exc))

    def set_volume(self, percent):
        self._require()
        try:
            value = self._volume.set(_percent(percent))
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("громкость: {}".format(exc))
        self._touch(value)
        return value

    def volume_up(self):
        self._require()
        try:
            self._volume.up()
            value = self._volume.get()
        except Exception as exc:
            raise AgentError("громкость: {}".format(exc))
        self._touch(value)
        return value

    def volume_down(self):
        self._require()
        try:
            self._volume.down()
            value = self._volume.get()
        except Exception as exc:
            raise AgentError("громкость: {}".format(exc))
        self._touch(value)
        return value

    # --- сохранение громкости --------------------------------------

    def set_store(self, callback):
        """Кто запоминает громкость: `callback(percent)` или `None`."""
        if callback is not None and not callable(callback):
            raise AgentError("store должен вызываться")
        self._store = callback
        return self

    def _touch(self, percent):
        self._pending = _percent(int(percent))
        self._changed_ms = int(self._clock())

    def _flush(self):
        percent = self._pending
        if percent is None:
            return None
        self._pending = None
        if self._store is None:
            return percent
        try:
            self._store(percent)
        except Exception as exc:
            print("VOLUME store", type(exc).__name__, str(exc))
        return percent

    def poll(self, now_ms=None):
        """Сохранить громкость после `save_ms` без изменений."""
        if self._pending is None:
            return []
        now = int(self._clock() if now_ms is None else now_ms)
        if now - self._changed_ms < self.save_ms:
            return []
        self._flush()
        return []

    def bt_enable(self):
        self._require()
        try:
            status = self._bt.enable()
            audio = self._bt.audio_start()
        except Exception as exc:
            raise AgentError("Bluetooth: {}".format(exc))
        return {"status": status, "audio": audio}

    def bt_disable(self):
        self._require()
        try:
            return self._bt.disable()
        except Exception as exc:
            raise AgentError("Bluetooth: {}".format(exc))

    def bt_suspend(self):
        """Снять звук телефона, не разрывая A2DP."""
        self._require()
        try:
            return self._bt.mute(True)
        except Exception as exc:
            raise AgentError("Bluetooth: {}".format(exc))

    def bt_resume(self):
        self._require()
        try:
            return self._bt.mute(False)
        except Exception as exc:
            raise AgentError("Bluetooth: {}".format(exc))

    def bt_audio(self):
        """Идёт ли звук телефона на динамик."""
        self._require()
        try:
            return bool(self._bt.audio())
        except Exception as exc:
            raise AgentError("Bluetooth: {}".format(exc))

    def ack(self):
        """Короткий сигнал готовности; ждём его окончания перед ASR."""
        self._require()
        try:
            return self._speaker.tone(880, 0.12, wait=True)
        except Exception as exc:
            raise AgentError("динамик: {}".format(exc))

    def stop(self):
        self._require()
        try:
            return self._speaker.stop()
        except Exception as exc:
            raise AgentError("динамик: {}".format(exc))

    def close(self):
        if not self._opened:
            return True
        self._flush()
        try:
            self.stop()
        except Exception:
            pass
        self._opened = False
        return True

    def info(self):
        result = {"opened": self._opened, "save_ms": self.save_ms,
                  "pending": self._pending}
        if self._opened:
            try:
                result["volume"] = self._volume.get()
            except Exception:
                result["volume"] = None
        return result
