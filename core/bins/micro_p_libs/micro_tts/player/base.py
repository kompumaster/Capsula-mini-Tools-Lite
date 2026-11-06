"""Базовый интерфейс плеера.

Плеер только выводит PCM/WAV и управляет процессом. Он не синтезирует
и не знает про движки.
"""

from micro_tts import audio
from micro_tts.errors import TtsError


class Player:
    """Интерфейс воспроизведения.

    `playing()` истинно и во время проигрывания, и на паузе: это
    активный сеанс. `paused()` отличает паузу от игры.
    """

    def play_pcm(self, pcm, rate, sink=None, wait=False, owner=None):
        """Начать вывод PCM; занятый плеер — `TtsError`."""
        raise TtsError("плеер не реализует play_pcm()")

    def play_wav(self, path, sink=None, wait=False, owner=None):
        """Начать вывод WAV; занятый плеер — `TtsError`."""
        raise TtsError("плеер не реализует play_wav()")

    def start_stream(self, rate, sink=None, owner=None):
        """Начать потоковый вывод PCM; занятый плеер — `TtsError`."""
        raise TtsError("плеер не реализует поток")

    def write_stream(self, pcm):
        """Записать кусок PCM в поток."""
        raise TtsError("плеер не реализует поток")

    def finish_stream(self, wait=False):
        """Закончить поток и дождаться слива."""
        raise TtsError("плеер не реализует поток")

    def pause(self):
        """Пауза; `True`, если удалось."""
        return False

    def resume(self):
        """Продолжить; `True`, если удалось."""
        return False

    def paused(self):
        """На паузе ли воспроизведение."""
        return False

    def owner(self):
        """Владелец текущего сеанса или `None`."""
        return None

    def stop(self, owner=None):
        """Остановить; `owner` — только свою фразу."""
        return False

    def playing(self):
        """Есть ли активный сеанс: игра или пауза."""
        return False

    def close(self, owner=None):
        """Освободить ресурсы; чужую фразу не трогать."""
        return True

    def _check_pcm(self, pcm, rate):
        audio.validate_pcm(pcm)
        if not pcm:
            raise TtsError("пустой PCM")
        if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
            raise TtsError("частота должна быть положительным целым")
        return rate

    def _check_path(self, path):
        if not isinstance(path, str) or not path:
            raise TtsError("пустой путь WAV")
        return path
