"""Плеер через `micro_hal.lib_speaker`.

Всё общение со звуком идёт через фасад `lib_speaker`: он сам
подтягивает `hal_pulse`, `hal_speaker` и `hal_volume`, поэтому в
`micro_tts` нет прямых вызовов `pactl`/`pacat` и временных файлов.

`micro_hal` импортируется только внутри методов: модуль открывается
на хосте без установленного HAL.
"""

from micro_tts.errors import TtsError
from micro_tts.player.base import Player


class MicroHalPlayer(Player):
    """Вывод через `micro_hal.lib_speaker`."""

    def __init__(self, sink="master", lib=None):
        if not isinstance(sink, str) or not sink:
            raise TtsError("пустое имя sink")
        self.sink = sink
        self._lib = lib
        self._stream = None
        self._owner = None

    # --- зависимости -----------------------------------------------

    def _speaker(self):
        if self._lib is not None:
            return self._lib
        try:
            from micro_hal import lib_speaker
        except Exception as exc:
            raise TtsError("нет micro_hal.lib_speaker: {}".format(exc))
        self._lib = lib_speaker
        return lib_speaker

    def _sink_value(self, sink):
        if sink is None:
            return self.sink
        if not isinstance(sink, str) or not sink:
            raise TtsError("пустое имя sink")
        return sink

    # --- воспроизведение -------------------------------------------

    def play_pcm(self, pcm, rate, sink=None, wait=False, owner=None):
        if self.playing():
            raise TtsError("плеер уже играет")
        rate = self._check_pcm(pcm, rate)
        sink = self._sink_value(sink)
        try:
            self._speaker().play_pcm(pcm, rate=rate, channels=1,
                                     sink=sink, wait=wait)
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("micro_hal: {}".format(exc))
        self._owner = owner
        return True

    def play_wav(self, path, sink=None, wait=False, owner=None):
        if self.playing():
            raise TtsError("плеер уже играет")
        path = self._check_path(path)
        sink = self._sink_value(sink)
        try:
            self._speaker().play_wav(path, sink=sink, wait=wait)
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("micro_hal: {}".format(exc))
        self._owner = owner
        return True

    def owner(self):
        if self.playing():
            return self._owner
        return None

    def playing(self):
        if self._stream is not None:
            try:
                return bool(self._stream.running())
            except TtsError:
                raise
            except Exception as exc:
                raise TtsError("micro_hal: {}".format(exc))
        try:
            return self._speaker().playing() is not None
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("micro_hal: {}".format(exc))

    # --- поток -----------------------------------------------------

    def start_stream(self, rate, sink=None, owner=None):
        if self.playing():
            raise TtsError("плеер уже играет")
        if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
            raise TtsError("частота должна быть положительным целым")
        sink = self._sink_value(sink)
        try:
            stream = self._speaker().stream(sink=sink, rate=rate,
                                            channels=1)
            stream.open()
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("micro_hal: {}".format(exc))
        self._stream = stream
        self._owner = owner
        return True

    def write_stream(self, pcm):
        if self._stream is None:
            raise TtsError("поток не открыт")
        if not isinstance(pcm, (bytes, bytearray)):
            raise TtsError("нужны bytes")
        if len(pcm) % 2 != 0:
            raise TtsError("PCM должен быть кратен 2 байтам")
        try:
            self._stream.write(pcm)
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("micro_hal: {}".format(exc))
        return len(pcm)

    def finish_stream(self, wait=False):
        stream = self._stream
        self._stream = None
        self._owner = None
        if stream is None:
            return False
        try:
            stream.close()
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("micro_hal: {}".format(exc))
        return True

    # --- пауза -----------------------------------------------------

    def pause(self):
        try:
            return bool(self._speaker().pause())
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("micro_hal: {}".format(exc))

    def resume(self):
        try:
            return bool(self._speaker().resume())
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("micro_hal: {}".format(exc))

    def paused(self):
        try:
            return bool(self._speaker().paused())
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("micro_hal: {}".format(exc))

    # --- остановка -------------------------------------------------

    def stop(self, owner=None):
        if owner is not None and self._owner not in (None, owner):
            return False
        stream = self._stream
        self._stream = None
        self._owner = None
        if stream is not None:
            try:
                return bool(stream.stop())
            except TtsError:
                raise
            except Exception as exc:
                raise TtsError("не остановить плеер: {}".format(exc))
        try:
            return bool(self._speaker().stop())
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("не остановить плеер: {}".format(exc))

    def close(self, owner=None):
        if owner is not None and self._owner not in (None, owner):
            return False
        try:
            self.stop(owner=owner)
        except TtsError:
            pass
        return True
