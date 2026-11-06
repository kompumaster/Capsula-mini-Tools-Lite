"""Фиктивный плеер для тестов: состояние без реального времени."""

from micro_tts import audio
from micro_tts.errors import TtsError
from micro_tts.player.base import Player

IDLE = "idle"
PLAYING = "playing"
PAUSED = "paused"
FINISHED = "finished"
STOPPED = "stopped"


class FakePlayer(Player):
    """Запоминает вызовы и меняет состояние.

    `finish()` — тестовый хук: изображает конец воспроизведения.
    В интерфейс `Player` он не входит.
    """

    def __init__(self):
        self.state = IDLE
        self.last_pcm = None
        self.last_path = None
        self.last_rate = 0
        self.last_sink = None
        self.last_duration = 0.0
        self.starts = 0
        self.pauses = 0
        self.resumes = 0
        self.stops = 0
        self.closes = 0
        self.streams = 0
        self.stream_chunks = []
        self.stream_bytes = 0
        self.stream_finishes = 0
        self.last_stream_rate = 0
        self._owner = None

    def _start(self, wait):
        self.starts += 1
        if wait:
            self.state = FINISHED
        else:
            self.state = PLAYING

    def play_pcm(self, pcm, rate, sink=None, wait=False, owner=None):
        if self.state in (PLAYING, PAUSED):
            raise TtsError("плеер уже играет")
        rate = self._check_pcm(pcm, rate)
        if sink is not None and (not isinstance(sink, str) or not sink):
            raise TtsError("неверный sink")
        self.last_pcm = pcm
        self.last_path = None
        self.last_rate = rate
        self.last_sink = sink
        self.last_duration = audio.duration(pcm, rate)
        self._owner = owner
        self._start(wait)
        return True

    def play_wav(self, path, sink=None, wait=False, owner=None):
        if self.state in (PLAYING, PAUSED):
            raise TtsError("плеер уже играет")
        path = self._check_path(path)
        if sink is not None and (not isinstance(sink, str) or not sink):
            raise TtsError("неверный sink")
        self.last_pcm = None
        self.last_path = path
        self.last_sink = sink
        self.last_duration = 0.0
        self._owner = owner
        self._start(wait)
        return True

    def start_stream(self, rate, sink=None, owner=None):
        if self.state in (PLAYING, PAUSED):
            raise TtsError("плеер уже играет")
        if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
            raise TtsError("частота должна быть положительным целым")
        if sink is not None and (not isinstance(sink, str) or not sink):
            raise TtsError("неверный sink")
        self.streams += 1
        self.stream_chunks = []
        self.stream_bytes = 0
        self.last_stream_rate = rate
        self.last_sink = sink
        self._owner = owner
        self.state = PLAYING
        return True

    def write_stream(self, pcm):
        if self.state != PLAYING:
            raise TtsError("поток не играет")
        if not isinstance(pcm, (bytes, bytearray)):
            raise TtsError("нужны bytes")
        if len(pcm) % 2 != 0:
            raise TtsError("PCM должен быть кратен 2 байтам")
        self.stream_chunks.append(bytes(pcm))
        self.stream_bytes += len(pcm)
        self.last_duration += len(pcm) / 2.0 / self.last_stream_rate
        return len(pcm)

    def finish_stream(self, wait=False):
        if self.state not in (PLAYING, PAUSED):
            return False
        self.stream_finishes += 1
        self.state = FINISHED
        return True

    def pause(self):
        if self.state != PLAYING:
            return False
        self.state = PAUSED
        self.pauses += 1
        return True

    def resume(self):
        if self.state != PAUSED:
            return False
        self.state = PLAYING
        self.resumes += 1
        return True

    def paused(self):
        return self.state == PAUSED

    def owner(self):
        if self.state in (PLAYING, PAUSED):
            return self._owner
        return None

    def stop(self, owner=None):
        if self.state not in (PLAYING, PAUSED):
            return False
        if owner is not None and self._owner not in (None, owner):
            return False
        self.state = STOPPED
        self._owner = None
        self.stops += 1
        return True

    def playing(self):
        return self.state in (PLAYING, PAUSED)

    def finish(self):
        """Тестовый хук: воспроизведение дошло до конца."""
        if self.state != PLAYING:
            return False
        self.state = FINISHED
        self._owner = None
        return True

    def close(self, owner=None):
        if owner is not None and self._owner not in (None, owner):
            return False
        self.state = IDLE
        self._owner = None
        self.last_pcm = None
        self.last_path = None
        self.last_rate = 0
        self.last_sink = None
        self.last_duration = 0.0
        self.closes += 1
        return True
