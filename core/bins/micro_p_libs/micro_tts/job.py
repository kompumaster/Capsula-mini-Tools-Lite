"""Задача синтеза и её состояния.

`SpeechJob` хранит только состояние и метаданные. Синтез, кеш и
воспроизведение живут в других модулях.
"""

from micro_tts import audio
from micro_tts.errors import TtsError

PROCESSING_IDLE = "idle"
PROCESSING_TEXT_SENT = "text_sent"
PROCESSING_CACHE_LOOKUP = "cache_lookup"
PROCESSING_SYNTHESIZING = "synthesizing"
PROCESSING_AUDIO_READY = "audio_ready"
PROCESSING_STOPPED = "stopped"
PROCESSING_ERROR = "error"

PLAYBACK_IDLE = "idle"
PLAYBACK_PLAYING = "playing"
PLAYBACK_PAUSED = "paused"
PLAYBACK_FINISHED = "finished"
PLAYBACK_STOPPED = "stopped"
PLAYBACK_ERROR = "error"

STATE_IDLE = "idle"
STATE_PREPARING = "preparing"
STATE_AUDIO_READY = "audio_ready"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"
STATE_FINISHED = "finished"
STATE_STOPPED = "stopped"
STATE_ERROR = "error"

_PREPARING = (
    PROCESSING_TEXT_SENT,
    PROCESSING_CACHE_LOOKUP,
    PROCESSING_SYNTHESIZING,
)


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TtsError("{} должен быть положительным целым".format(name))
    return value


def _non_negative_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TtsError("{} должен быть целым неотрицательным".format(name))
    return value


class SpeechJob:
    """Одна фраза: текст, состояние обработки и воспроизведения."""

    def __init__(self, text, job_id=0, use_cache=False):
        if not isinstance(text, str):
            raise TtsError("текст должен быть строкой")
        if not text.strip():
            raise TtsError("текст пустой")
        self.id = int(job_id)
        self.text = text
        self.use_cache = bool(use_cache)
        self.cache_key = None
        self.chunks = []
        self.processing = PROCESSING_TEXT_SENT
        self.playback = PLAYBACK_IDLE
        self.cached = False
        self.chunks_total = 0
        self.chunks_done = 0
        self.bytes = 0
        self.duration = 0.0
        self.sample_rate = 0
        self.pcm = None
        self.audio_path = None
        self.error = None

    @property
    def state(self):
        """Сводное состояние для оркестратора."""
        if (self.processing == PROCESSING_ERROR
                or self.playback == PLAYBACK_ERROR):
            return STATE_ERROR
        if (self.processing == PROCESSING_STOPPED
                or self.playback == PLAYBACK_STOPPED):
            return STATE_STOPPED
        if self.playback == PLAYBACK_PLAYING:
            return STATE_PLAYING
        if self.playback == PLAYBACK_PAUSED:
            return STATE_PAUSED
        if self.playback == PLAYBACK_FINISHED:
            return STATE_FINISHED
        if self.processing == PROCESSING_AUDIO_READY:
            return STATE_AUDIO_READY
        if self.processing in _PREPARING:
            return STATE_PREPARING
        return STATE_IDLE

    def ready(self):
        """Готово ли аудио к воспроизведению."""
        return self.processing == PROCESSING_AUDIO_READY

    def _check_processing(self, value, allowed):
        if self.processing not in allowed:
            raise TtsError("недопустимый переход processing: {} -> {}".format(
                self.processing, value))

    def _processing(self, value, allowed):
        self._check_processing(value, allowed)
        self.processing = value

    def _playback(self, value, allowed):
        if self.playback not in allowed:
            raise TtsError("недопустимый переход playback: {} -> {}".format(
                self.playback, value))
        self.playback = value

    def mark_cache_lookup(self):
        """Текст принят, ищем готовое аудио в кеше."""
        self._processing(
            PROCESSING_CACHE_LOOKUP, (PROCESSING_TEXT_SENT,))

    def mark_synthesizing(self):
        """Начинаем синтез."""
        self._processing(
            PROCESSING_SYNTHESIZING,
            (PROCESSING_TEXT_SENT, PROCESSING_CACHE_LOOKUP))

    def set_chunks(self, total):
        """Сколько чанков будет синтезировано."""
        total = _positive_int(total, "chunks_total")
        if self.processing not in (PROCESSING_TEXT_SENT,
                                   PROCESSING_CACHE_LOOKUP,
                                   PROCESSING_SYNTHESIZING):
            raise TtsError(
                "нельзя задать число чанков в состоянии {}".format(
                    self.processing))
        self.chunks_total = total
        self.chunks_done = 0

    def mark_chunk_done(self):
        """Один чанк синтезирован."""
        if self.processing != PROCESSING_SYNTHESIZING:
            raise TtsError("чанк завершён вне синтеза")
        if self.chunks_total <= 0:
            raise TtsError("число чанков не задано")
        if self.chunks_done >= self.chunks_total:
            raise TtsError("все чанки уже завершены")
        self.chunks_done += 1

    def mark_audio_ready(self, pcm=None, sample_rate=0, duration=None,
                         audio_path=None, cached=False, size=None):
        """Аудио готово; можно играть или отложить."""
        self._check_processing(
            PROCESSING_AUDIO_READY,
            (PROCESSING_CACHE_LOOKUP, PROCESSING_SYNTHESIZING))
        if pcm is None and audio_path is None:
            raise TtsError("audio_ready без аудио")
        if pcm is not None:
            audio.validate_pcm(pcm)
            if not pcm:
                raise TtsError("пустой PCM")
        sample_rate = _positive_int(sample_rate, "sample_rate")
        if duration is None:
            duration = 0.0
            if pcm is not None:
                duration = len(pcm) / 2.0 / sample_rate
        if (isinstance(duration, bool)
                or not isinstance(duration, (int, float))):
            raise TtsError("duration должен быть числом")
        duration = float(duration)
        if duration < 0:
            raise TtsError("duration не может быть отрицательной")
        if pcm is not None:
            bytes_count = len(pcm)
        else:
            bytes_count = 0 if size is None else _non_negative_int(
                size, "size")
        self.pcm = pcm
        self.audio_path = audio_path
        self.sample_rate = sample_rate
        self.duration = duration
        self.cached = bool(cached)
        self.bytes = bytes_count
        self.processing = PROCESSING_AUDIO_READY

    def mark_playing(self):
        """Начать воспроизведение готовой задачи."""
        if self.processing != PROCESSING_AUDIO_READY:
            raise TtsError("play без готового аудио")
        self._playback(
            PLAYBACK_PLAYING,
            (PLAYBACK_IDLE, PLAYBACK_FINISHED, PLAYBACK_STOPPED))

    def mark_paused(self):
        """Поставить воспроизведение на паузу."""
        self._playback(PLAYBACK_PAUSED, (PLAYBACK_PLAYING,))

    def mark_resumed(self):
        """Продолжить после паузы."""
        self._playback(PLAYBACK_PLAYING, (PLAYBACK_PAUSED,))

    def mark_finished(self):
        """Воспроизведение доиграло."""
        self._playback(PLAYBACK_FINISHED, (PLAYBACK_PLAYING,))

    def mark_stream_started(self):
        """Поток: синтез и воспроизведение идут одновременно."""
        self._playback(
            PLAYBACK_PLAYING,
            (PLAYBACK_IDLE, PLAYBACK_FINISHED, PLAYBACK_STOPPED))
        self._processing(
            PROCESSING_SYNTHESIZING,
            (PROCESSING_TEXT_SENT, PROCESSING_CACHE_LOOKUP,
             PROCESSING_SYNTHESIZING))

    def mark_stream_progress(self, size, sample_rate):
        """Сколько PCM уже ушло в плеер при потоке."""
        if self.processing != PROCESSING_SYNTHESIZING:
            raise TtsError("прогресс потока вне синтеза")
        if self.playback != PLAYBACK_PLAYING:
            raise TtsError("прогресс потока без воспроизведения")
        size = _non_negative_int(size, "bytes")
        sample_rate = _positive_int(sample_rate, "sample_rate")
        self.bytes = size
        self.sample_rate = sample_rate
        self.duration = size / 2.0 / sample_rate

    def mark_stream_finished(self, size, sample_rate):
        """Поток закончен: всё аудио проиграно."""
        if self.processing != PROCESSING_SYNTHESIZING:
            raise TtsError("поток завершён вне синтеза")
        size = _non_negative_int(size, "bytes")
        sample_rate = _positive_int(sample_rate, "sample_rate")
        self.bytes = size
        self.sample_rate = sample_rate
        self.duration = size / 2.0 / sample_rate
        self.processing = PROCESSING_AUDIO_READY
        self._playback(PLAYBACK_FINISHED, (PLAYBACK_PLAYING,))

    def mark_playback_stopped(self):
        """Воспроизведение остановлено."""
        self._playback(
            PLAYBACK_STOPPED, (PLAYBACK_PLAYING, PLAYBACK_PAUSED))

    def mark_processing_stopped(self):
        """Обработка отменена."""
        self._processing(
            PROCESSING_STOPPED,
            (PROCESSING_TEXT_SENT, PROCESSING_CACHE_LOOKUP,
             PROCESSING_SYNTHESIZING))

    def fail(self, message, playback=False):
        """Зафиксировать ошибку обработки или воспроизведения."""
        if not isinstance(message, str) or not message.strip():
            raise TtsError("пустое сообщение об ошибке")
        if playback:
            if self.playback not in (PLAYBACK_IDLE, PLAYBACK_PLAYING,
                                     PLAYBACK_PAUSED):
                raise TtsError(
                    "нельзя записать ошибку воспроизведения в состоянии "
                    "{}".format(self.playback))
            self.playback = PLAYBACK_ERROR
        else:
            if self.processing in (PROCESSING_ERROR, PROCESSING_STOPPED):
                raise TtsError(
                    "нельзя записать ошибку обработки в состоянии "
                    "{}".format(self.processing))
            self.processing = PROCESSING_ERROR
        self.error = message

    def status(self, cache_info=None):
        """Снимок для оркестратора."""
        return {
            "state": self.state,
            "processing": self.processing,
            "playback": self.playback,
            "job_id": self.id,
            "text": self.text,
            "cached": self.cached,
            "chunks_total": self.chunks_total,
            "chunks_done": self.chunks_done,
            "bytes": self.bytes,
            "duration": self.duration,
            "sample_rate": self.sample_rate,
            "error": self.error,
            "cache": cache_info,
        }
