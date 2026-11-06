"""Координатор TTS: задача, движок, кеш и плеер.

Библиотека не создаёт потоков: оркестратор вызывает `submit()` и
`pump()`, а воспроизведение идёт через плеер. Кеш по умолчанию
выключен; включается параметром запроса `cache=True`.
"""

import os

from micro_tts import audio
from micro_tts.cache.codec import WavCodec
from micro_tts.cache.file import FileCache
from micro_tts.cache.key import cache_key
from micro_tts.cache.mp3 import Mp3Codec
from micro_tts.config import (
    Config, DEFAULT_CACHE_DIR, DEFAULT_CACHE_MAX_BYTES,
    DEFAULT_CACHE_MAX_ENTRIES, DEFAULT_CACHE_MAX_CHARS,
    DEFAULT_CHUNK_CHARS)
from micro_tts.engine.base import check_format
from micro_tts.engine.registry import get_engine
from micro_tts.errors import TtsError
from micro_tts.job import (
    PLAYBACK_PAUSED, PLAYBACK_PLAYING, PLAYBACK_STOPPED,
    PROCESSING_AUDIO_READY, PROCESSING_CACHE_LOOKUP,
    PROCESSING_SYNTHESIZING, PROCESSING_TEXT_SENT, SpeechJob)
from micro_tts.text.russian import RussianNormalizer

_PREPARING = (
    PROCESSING_TEXT_SENT,
    PROCESSING_CACHE_LOOKUP,
    PROCESSING_SYNTHESIZING,
)

# Короткий PCM держим в памяти; длинный уходит в файл.
TEMP_DIR = "/tmp"
TEMP_LIMIT = 256 * 1024

# Запас под лимит запроса движка: склеиваем чуть меньше.
STREAM_MARGIN = 128


class TTS:
    """Связывает задачу, движок и плеер.

    Один экземпляр ведёт одну задачу в обработке. Готовые задачи можно
    хранить и играть по `play(job)`.
    """

    def __init__(self, engine=None, voice=None, rate=1.0, pitch=1.0,
                 volume=None, sink="master", chunk_chars=DEFAULT_CHUNK_CHARS,
                 player=None, normalizer=None, cache=False,
                 cache_dir=DEFAULT_CACHE_DIR,
                 cache_max_bytes=DEFAULT_CACHE_MAX_BYTES,
                 cache_max_entries=DEFAULT_CACHE_MAX_ENTRIES,
                 cache_max_chars=DEFAULT_CACHE_MAX_CHARS, options=None):
        self.config = Config(
            engine=engine, voice=voice, rate=rate, pitch=pitch,
            volume=volume, sink=sink, chunk_chars=chunk_chars,
            player=player, normalizer=normalizer, cache=cache,
            cache_dir=cache_dir, cache_max_bytes=cache_max_bytes,
            cache_max_entries=cache_max_entries,
            cache_max_chars=cache_max_chars, options=options)
        if self.config.normalizer is None:
            self._normalizer = RussianNormalizer()
        else:
            self._normalizer = self.config.normalizer
        self._engine = None
        self._format = None
        self._player = None
        self._cache = None
        self._pending = None
        self._active_job = None
        self._last_job = None
        self._last_prepared = None
        self._jobs = {}
        self._next_id = 1
        self._closed = False
        self._stream_stop = False
        self._encoded = {}

    # --- служебное -------------------------------------------------

    def _check(self):
        if self._closed:
            raise TtsError("TTS закрыт")

    def _cache_flag(self, value):
        if value is None:
            return self.config.cache
        if not isinstance(value, bool):
            raise TtsError("cache должен быть True, False или None")
        return value

    def _ensure_engine(self):
        if self._engine is not None:
            return
        engine = get_engine(self.config.engine)
        try:
            engine.open(voice=self.config.voice, rate=self.config.rate,
                        pitch=self.config.pitch, **self.config.options)
            fmt = check_format(engine.format())
        except TtsError:
            try:
                engine.close()
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                engine.close()
            except Exception:
                pass
            raise TtsError("не открыть движок: {}".format(exc))
        self._engine = engine
        self._format = fmt

    def _ensure_player(self):
        if self._player is not None:
            return
        if self.config.player is not None:
            self._player = self.config.player
            return
        try:
            from micro_tts.player.microhal import MicroHalPlayer
        except Exception as exc:
            raise TtsError("плеер не задан: {}".format(exc))
        self._player = MicroHalPlayer(sink=self.config.sink)

    def _ensure_cache(self):
        if self._cache is None:
            self._cache = FileCache(
                self.config.cache_dir,
                codecs={"wav": WavCodec(), "mp3": Mp3Codec()},
                max_bytes=self.config.cache_max_bytes,
                max_entries=self.config.cache_max_entries,
                max_chars=self.config.cache_max_chars)
        return self._cache

    def _cache_allowed(self, job):
        if not job.use_cache:
            return False
        limit = self.config.cache_max_chars
        if limit > 0 and len(job.text) > limit:
            return False
        return True

    def _make_cache_key(self, job):
        self._ensure_engine()
        try:
            tag = self._engine.cache_tag()
        except Exception as exc:
            raise TtsError("движок не даёт cache_tag: {}".format(exc))
        return cache_key(job.text, tag, self.config.voice,
                         self.config.rate, self.config.pitch,
                         self._normalizer, self._format)

    def _cache_info(self):
        if self._cache is None:
            return None
        return self._cache.info()

    def _temp_path(self, job, suffix):
        try:
            pid = os.getpid()
        except AttributeError:
            pid = id(self) & 0xFFFF
        return "{}/micro_tts.{}.{}.{}".format(
            TEMP_DIR, pid, job.id, suffix)

    def _write_file(self, path, data):
        try:
            handle = open(path, "wb")
            try:
                # Без bytes(data): это вторая полная копия PCM, из-за
                # неё на слабом хосте бывает MemoryError.
                handle.write(data)
            finally:
                handle.close()
        except OSError as exc:
            raise TtsError("не записать {}: {}".format(path, exc))

    def _append_file(self, path, data):
        try:
            handle = open(path, "ab")
            try:
                handle.write(data)
            finally:
                handle.close()
        except OSError as exc:
            raise TtsError("не дописать {}: {}".format(path, exc))

    def _append_pcm(self, job, pcm):
        if job.pcm is None:
            if job.audio_path is not None:
                try:
                    self._append_file(job.audio_path, pcm)
                except Exception:
                    # Обрывок файла задаче уже не поможет: убираем.
                    self._remove_job_file(job)
                    raise
                return
            job.pcm = bytearray()
        job.pcm.extend(pcm)
        if len(job.pcm) > TEMP_LIMIT:
            path = self._temp_path(job, "raw")
            # Путь фиксируем до записи: иначе при сбое файл остаётся
            # «ничейным» и stop()/close() его не находят.
            job.audio_path = path
            try:
                self._write_file(path, job.pcm)
            except Exception:
                self._remove_job_file(job)
                job.pcm = None
                raise
            job.pcm = None

    def _remove_file(self, path):
        if not path:
            return
        try:
            os.remove(path)
        except OSError:
            pass

    def _remove_job_file(self, job):
        path = job.audio_path
        job.audio_path = None
        self._remove_file(path)

    def _chunks(self, text):
        limit = self.config.chunk_chars
        try:
            chunks = self._normalizer.prepare(text, limit=limit)
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("нормализатор: {}".format(exc))
        if not isinstance(chunks, (list, tuple)) or not chunks:
            raise TtsError("нормализатор не дал чанков")
        result = []
        for chunk in chunks:
            if not isinstance(chunk, str) or not chunk.strip():
                raise TtsError("нормализатор вернул пустой чанк")
            result.append(chunk)
        return result

    @staticmethod
    def _bytes(text):
        try:
            return len(text.encode("utf-8"))
        except AttributeError:
            return len(text)

    @classmethod
    def _split_bytes(cls, text, limit):
        """Разбить строку на части не длиннее `limit` байт UTF-8."""
        parts = []
        current = ""
        for char in text:
            candidate = current + char
            if current and cls._bytes(candidate) > limit:
                parts.append(current.strip())
                current = "" if char == " " else char
            else:
                current = candidate
        if current.strip():
            parts.append(current.strip())
        return parts

    def _stream_segments(self, text):
        """Склеить предложения в сегменты под лимит одного запроса."""
        chunks = self._chunks(text)
        limit = self._engine.request_bytes() or 0
        if limit > 0:
            limit = max(256, limit - STREAM_MARGIN)
        segments = []
        current = ""
        for chunk in chunks:
            if limit and self._bytes(chunk) > limit:
                if current:
                    segments.append(current)
                    current = ""
                segments.extend(self._split_bytes(chunk, limit))
                continue
            candidate = chunk if not current else current + " " + chunk
            if limit and current and self._bytes(candidate) > limit:
                segments.append(current)
                current = chunk
            else:
                current = candidate
        if current:
            segments.append(current)
        if not segments:
            raise TtsError("нормализатор не дал текста для запроса")
        return segments

    def _fail(self, job, message):
        self._encoded.pop(job.id, None)
        self._remove_job_file(job)
        try:
            job.fail(message)
        except TtsError:
            pass
        self._pending = None

    def _fail_playback(self, job, message):
        try:
            job.fail(message, playback=True)
        except TtsError:
            pass
        if self._active_job is job:
            self._active_job = None

    def _sync_playback(self):
        job = self._active_job
        if job is None or self._player is None:
            return
        if job.playback in (PLAYBACK_PLAYING, PLAYBACK_PAUSED):
            try:
                owner = self._player.owner()
            except TtsError:
                owner = None
            if owner is not None and owner is not self:
                job.mark_playback_stopped()
                self._active_job = None
                return
        if job.playback == PLAYBACK_PLAYING:
            if not self._player.playing():
                job.mark_finished()
                self._active_job = None
            elif self._player.paused():
                job.mark_paused()
        elif job.playback == PLAYBACK_PAUSED:
            if not self._player.playing():
                job.mark_playback_stopped()
                self._active_job = None
            elif not self._player.paused():
                job.mark_resumed()

    def _encoded_format(self):
        """Формат сжатого аудио движка или None."""
        method = getattr(self._engine, "encoded_format", None)
        if method is None:
            return None
        try:
            value = method()
        except Exception:
            return None
        if isinstance(value, str) and value:
            return value
        return None

    def _idle_status(self, cache_info=None):
        return {
            "state": "idle",
            "processing": "idle",
            "playback": "idle",
            "job_id": None,
            "text": None,
            "cached": False,
            "chunks_total": 0,
            "chunks_done": 0,
            "bytes": 0,
            "duration": 0.0,
            "sample_rate": 0,
            "error": None,
            "cache": cache_info,
        }

    # --- API -------------------------------------------------------

    def submit(self, text, cache=None):
        """Принять текст и сразу вернуть задачу."""
        self._check()
        if self._pending is not None:
            raise TtsError("уже идёт обработка")
        use_cache = self._cache_flag(cache)
        job = SpeechJob(text, self._next_id, use_cache=use_cache)
        self._next_id += 1
        self._jobs[job.id] = job
        self._pending = job
        self._last_job = job
        return job

    def pump(self):
        """Сделать один ограниченный шаг обработки."""
        self._check()
        job = self._pending
        if job is None:
            return False

        if job.processing == PROCESSING_TEXT_SENT:
            try:
                chunks = self._chunks(job.text)
            except TtsError as exc:
                self._fail(job, str(exc))
                raise
            job.chunks = chunks
            job.set_chunks(len(chunks))
            if self._cache_allowed(job):
                job.mark_cache_lookup()
            else:
                job.mark_synthesizing()
            return True

        if job.processing == PROCESSING_CACHE_LOOKUP:
            try:
                job.cache_key = self._make_cache_key(job)
                cached = self._ensure_cache().get(
                    job.cache_key, job.text)
            except TtsError as exc:
                self._fail(job, str(exc))
                raise
            except Exception as exc:
                message = "кеш: {}".format(exc)
                self._fail(job, message)
                raise TtsError(message)
            if cached is not None:
                pcm, rate, _meta = cached
                try:
                    job.mark_audio_ready(pcm=pcm, sample_rate=rate,
                                         cached=True)
                except TtsError as exc:
                    self._fail(job, str(exc))
                    raise
                job.chunks_done = job.chunks_total
                self._pending = None
                self._last_prepared = job
                return True
            job.mark_synthesizing()
            return True

        if job.processing != PROCESSING_SYNTHESIZING:
            self._pending = None
            return False

        try:
            self._ensure_engine()
        except TtsError as exc:
            self._fail(job, str(exc))
            raise

        index = job.chunks_done
        if index >= len(job.chunks):
            message = "чанки закончились раньше времени"
            self._fail(job, message)
            raise TtsError(message)

        try:
            encoded_format = (self._encoded_format()
                              if self._cache_allowed(job) else None)
            if encoded_format:
                pcm, encoded = self._engine.synthesize_pair(
                    job.chunks[index])
                if encoded:
                    parts = self._encoded.setdefault(job.id, bytearray())
                    parts.extend(encoded)
            else:
                pcm = self._engine.synthesize(job.chunks[index])
        except TtsError as exc:
            self._fail(job, str(exc))
            raise
        except Exception as exc:
            message = "движок: {}".format(exc)
            self._fail(job, message)
            raise TtsError(message)

        try:
            audio.validate_pcm(pcm)
        except TtsError as exc:
            self._fail(job, str(exc))
            raise
        if not pcm:
            message = "движок вернул пустой PCM"
            self._fail(job, message)
            raise TtsError(message)

        try:
            self._append_pcm(job, pcm)
        except TtsError as exc:
            self._fail(job, str(exc))
            raise
        job.mark_chunk_done()

        if job.chunks_done >= job.chunks_total:
            if job.audio_path is not None:
                raw_path = job.audio_path
                wav_path = self._temp_path(job, "wav")
                try:
                    size = audio.raw_to_wav(
                        raw_path, wav_path, self._format.rate)
                except TtsError as exc:
                    self._fail(job, str(exc))
                    raise
                self._remove_file(raw_path)
                job.audio_path = wav_path
                job.pcm = None
                try:
                    job.mark_audio_ready(
                        audio_path=wav_path,
                        sample_rate=self._format.rate, size=size,
                        duration=size / 2.0 / self._format.rate)
                except TtsError as exc:
                    self._fail(job, str(exc))
                    raise
            else:
                data = bytes(job.pcm)
                job.pcm = data
                try:
                    job.mark_audio_ready(
                        pcm=data, sample_rate=self._format.rate)
                except TtsError as exc:
                    self._fail(job, str(exc))
                    raise
                if job.cache_key is not None:
                    try:
                        cache = self._ensure_cache()
                        encoded = self._encoded.pop(job.id, None)
                        encoded_format = self._encoded_format()
                        if (encoded and encoded_format
                                and len(job.chunks) == 1):
                            cache.put_encoded(
                                job.cache_key, bytes(encoded),
                                encoded_format, self._format.rate,
                                {"text": job.text})
                        else:
                            cache.put(
                                job.cache_key, data, self._format.rate,
                                {"text": job.text})
                    except Exception:
                        pass
            self._pending = None
            self._last_prepared = job
        return True

    def prepare(self, text, cache=None):
        """Синтезировать текст и вернуть готовую задачу."""
        self._check()
        job = self.submit(text, cache=cache)
        while job.processing in _PREPARING:
            if not self.pump():
                break
        if job.processing != PROCESSING_AUDIO_READY:
            raise TtsError("не удалось подготовить аудио: {}".format(
                job.processing))
        return job

    def say(self, text, cache=None, defer=False, wait=True,
            interrupt=False, stream=False):
        """Подготовить и, если не `defer`, воспроизвести.

        `stream=True` — потоковый режим: текст синтезируется и сразу
        играет кусками, PCM не накапливается. Кеш не используется,
        `defer` игнорируется, вызов блокирующий.
        """
        if stream:
            return self._say_stream(text, interrupt=interrupt)
        job = self.prepare(text, cache=cache)
        if defer:
            return job
        self.play(job, interrupt=interrupt, wait=wait)
        return job

    def _say_stream(self, text, interrupt=False):
        """Потоковый синтез и вывод: память ограничена куском."""
        self._check()
        self._ensure_engine()
        capabilities = self._engine.capabilities() or {}
        if not capabilities.get("stream"):
            raise TtsError(
                "движок {} не поддерживает поток".format(self._engine.name))
        format_value = check_format(self._engine.format())
        rate = format_value.rate

        self._ensure_player()
        if self._player.playing():
            if interrupt:
                self.stop()
                if self._player.playing():
                    self._player.stop()
            else:
                raise TtsError("уже играет")

        job = self.submit(text, cache=False)
        self._stream_stop = False
        self._encoded = {}
        self._active_job = job
        try:
            self._player.start_stream(rate, sink=self.config.sink,
                                      owner=self)
            job.mark_stream_started()
        except TtsError as exc:
            self._fail(job, str(exc))
            raise

        total = 0
        chunks = self._stream_segments(text)
        job.set_chunks(len(chunks))
        try:
            for chunk in chunks:
                if self._stream_stop:
                    break
                for piece in self._engine.stream(chunk):
                    if self._stream_stop:
                        break
                    self._player.write_stream(piece)
                    total += len(piece)
                if self._stream_stop:
                    break
                job.mark_chunk_done()
                job.mark_stream_progress(total, rate)
            if self._stream_stop:
                try:
                    self._player.stop()
                except TtsError:
                    pass
                self._stop_stream(job)
                return job
            self._player.finish_stream(wait=True)
            job.mark_stream_finished(total, rate)
        except TtsError as exc:
            try:
                self._player.stop()
            except TtsError:
                pass
            if self._stream_stop:
                self._stop_stream(job)
                return job
            job.fail(str(exc), playback=True)
            raise
        except Exception as exc:
            try:
                self._player.stop()
            except TtsError:
                pass
            message = "плеер: {}".format(exc)
            job.fail(message, playback=True)
            raise TtsError(message)
        finally:
            self._active_job = None
        return job

    def _stop_stream(self, job):
        if job.playback == PLAYBACK_PLAYING:
            job.mark_playback_stopped()
        if job.processing in _PREPARING:
            job.mark_processing_stopped()

    def play(self, job=None, interrupt=False, wait=False):
        """Начать воспроизведение готовой задачи."""
        self._check()
        self._sync_playback()
        job = job or self._last_prepared
        if job is None:
            raise TtsError("нет готовой задачи")
        if job.processing != PROCESSING_AUDIO_READY:
            raise TtsError("play без готового аудио")
        try:
            self._ensure_player()
        except TtsError as exc:
            self._fail_playback(job, str(exc))
            raise
        try:
            busy = self._player.playing()
        except TtsError as exc:
            self._fail_playback(job, str(exc))
            raise
        if busy:
            if not interrupt:
                raise TtsError("уже играет")
            self.stop()
            if self._player.playing():
                self._player.stop()
        try:
            if job.pcm is not None:
                self._player.play_pcm(
                    job.pcm, job.sample_rate,
                    sink=self.config.sink, wait=wait, owner=self)
            elif job.audio_path is not None:
                self._player.play_wav(
                    job.audio_path, sink=self.config.sink, wait=wait,
                    owner=self)
            else:
                raise TtsError("нет аудио")
        except TtsError as exc:
            self._fail_playback(job, str(exc))
            raise
        except Exception as exc:
            message = "плеер: {}".format(exc)
            self._fail_playback(job, message)
            raise TtsError(message)
        try:
            job.mark_playing()
        except TtsError:
            self._player.stop(owner=self)
            raise
        self._active_job = job
        if wait:
            job.mark_finished()
            self._active_job = None
        return True

    def pause(self):
        """Пауза текущего воспроизведения."""
        self._check()
        self._sync_playback()
        job = self._active_job
        if job is None or job.playback != PLAYBACK_PLAYING:
            return False
        if not self._player.pause():
            return False
        job.mark_paused()
        return True

    def resume(self):
        """Продолжить после паузы."""
        self._check()
        self._sync_playback()
        job = self._active_job
        if job is None or job.playback != PLAYBACK_PAUSED:
            return False
        if not self._player.resume():
            return False
        job.mark_resumed()
        return True

    def stop(self):
        """Остановить воспроизведение и обработку."""
        self._check()
        self._stream_stop = True
        self._sync_playback()
        stopped = False
        if self._player is not None:
            try:
                active = self._player.playing()
            except TtsError:
                active = False
            if active:
                try:
                    if self._player.stop(owner=self):
                        stopped = True
                except TtsError:
                    pass
        job = self._active_job
        if job is not None:
            if job.playback in (PLAYBACK_PLAYING, PLAYBACK_PAUSED):
                job.mark_playback_stopped()
                stopped = True
            self._active_job = None
        job = self._pending
        if job is not None:
            self._encoded.pop(job.id, None)
            if job.processing in _PREPARING:
                job.mark_processing_stopped()
                self._remove_job_file(job)
                stopped = True
            self._pending = None
        return stopped

    def status(self, job=None):
        """Снимок состояния задачи."""
        self._check()
        self._sync_playback()
        cache_info = self._cache_info()
        job = job or self._active_job or self._last_job
        if job is None:
            return self._idle_status(cache_info)
        return job.status(cache_info)

    def cache_info(self):
        """Сводка кеша; без кеша — нули."""
        self._check()
        if self._cache is None:
            return {
                "entries": 0,
                "bytes": 0,
                "hits": 0,
                "misses": 0,
                "path": self.config.cache_dir,
            }
        return self._cache.info()

    def clear_cache(self):
        """Удалить все записи кеша."""
        self._check()
        try:
            return self._ensure_cache().clear()
        except TtsError:
            raise
        except Exception as exc:
            raise TtsError("не очистить кеш: {}".format(exc))

    def playing(self):
        """Идёт ли активный сеанс: игра или пауза."""
        self._check()
        self._sync_playback()
        return (self._active_job is not None
                and self._active_job.playback
                in (PLAYBACK_PLAYING, PLAYBACK_PAUSED))

    def close(self):
        """Остановить всё, закрыть движок и плеер."""
        if self._closed:
            return True
        try:
            self.stop()
        finally:
            if self._player is not None:
                try:
                    self._player.close(owner=self)
                except Exception:
                    pass
            if self._engine is not None:
                try:
                    self._engine.close()
                except Exception:
                    pass
            self._player = None
            self._engine = None
            self._format = None
            self._cache = None
            self._pending = None
            self._active_job = None
            self._last_job = None
            self._last_prepared = None
            for job in self._jobs.values():
                self._remove_job_file(job)
            self._jobs = {}
            self._closed = True
        self._encoded.clear()
        return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
