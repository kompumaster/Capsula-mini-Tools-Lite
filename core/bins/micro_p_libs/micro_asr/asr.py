"""Объект ASR: сценарии распознавания.

Библиотека не решает, когда слушать: `listen()` и `capture()` —
блокирующие вызовы, которые запускает оркестратор. Для файлов и
памяти есть кооперативный режим `submit` + `pump`.
"""

from micro_asr import audio
from micro_asr.config import Config
from micro_asr.engines.base import check_format
from micro_asr.engines.registry import get_engine
from micro_asr.errors import AsrError
from micro_asr.job import (
    STATE_CAPTURING, STATE_DONE, STATE_PREPARING, STATE_RECOGNIZING,
    RecognitionJob)
from micro_asr.sources.base import Source
from micro_asr.sources.file import FileSource
from micro_asr.sources.memory import MemorySource
from micro_asr.vad import SpeechDetector

DEFAULT_SILENCE = 0.8
DEFAULT_START_TIMEOUT = 5.0
DEFAULT_MAX_SECONDS = 25.0
DEFAULT_MIN_SPEECH = 0.3
MIC_CHUNK_BYTES = 640


def _positive_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AsrError("{} должен быть числом".format(name))
    value = float(value)
    if value <= 0:
        raise AsrError("{} должен быть больше нуля".format(name))
    return value


class ASR:
    """Распознавание речи: микрофон, память, файл."""

    def __init__(self, engine=None, language=None, sample_rate=None,
                 engine_options=None, mic=None):
        self.config = Config(
            engine=engine, language=language,
            sample_rate=sample_rate, engine_options=engine_options)
        self._mic = mic
        self._engine = None
        self._rate = self.config.sample_rate
        self._pending = None
        self._last_job = None
        self._counter = 0
        self._closed = False

    # --- служебное -------------------------------------------------

    def _check(self):
        if self._closed:
            raise AsrError("ASR уже закрыт")

    def _new_job(self, source):
        self._counter += 1
        return RecognitionJob(self._counter, source)

    def _idle_status(self):
        return {
            "state": "idle",
            "job_id": None,
            "source": None,
            "text": "",
            "speech": False,
            "bytes": 0,
            "duration": 0.0,
            "sample_rate": 0,
            "engine": None,
            "error": None,
        }

    def status(self):
        """Снимок последней или текущей задачи."""
        self._check()
        job = self._pending[0] if self._pending else self._last_job
        if job is None:
            return self._idle_status()
        return job.status()

    def _ensure_engine(self):
        if self._engine is not None:
            return
        engine = get_engine(self.config.engine)
        try:
            engine.open(
                language=self.config.language,
                sample_rate=self.config.sample_rate,
                **self.config.engine_options)
            value = check_format(engine.format())
        except AsrError:
            engine.close()
            raise
        except Exception as exc:
            engine.close()
            raise AsrError("движок: {}".format(exc))
        self._engine = engine
        self._rate = value.rate

    def _make_source(self, value, rate=None, channels=None):
        if isinstance(value, Source):
            return value
        if isinstance(value, (bytes, bytearray)):
            return MemorySource(
                value,
                self.config.sample_rate if rate is None else rate,
                1 if channels is None else channels)
        if isinstance(value, str):
            return FileSource(value)
        raise AsrError("источник должен быть Source, bytes или путём")

    # --- файл и память --------------------------------------------

    def submit(self, source, rate=None, channels=None):
        """Принять источник и сразу вернуть задачу."""
        self._check()
        value = self._make_source(source, rate, channels)
        job = self._new_job(value.name)
        job.mark_preparing()
        self._pending = [job, value, None]
        self._last_job = job
        return job

    def pump(self):
        """Один шаг обработки; `True`, если была работа."""
        self._check()
        if self._pending is None:
            return False
        job, source, pcm = self._pending
        if job.state == STATE_PREPARING:
            try:
                self._ensure_engine()
                info = source.info()
                prepared = audio.prepare(
                    source.read(), info["rate"], info["channels"],
                    info["width"], self._rate)
                job.set_audio(prepared, self._rate)
                job.engine = self._engine.name
                job.mark_recognizing()
            except AsrError as exc:
                job.fail(str(exc))
                self._pending = None
                raise
            except Exception as exc:
                message = "источник: {}".format(exc)
                job.fail(message)
                self._pending = None
                raise AsrError(message)
            self._pending = [job, source, prepared]
            return True
        if job.state == STATE_RECOGNIZING:
            try:
                text = self._engine.recognize(pcm)
            except AsrError as exc:
                job.fail(str(exc))
                self._pending = None
                raise
            except Exception as exc:
                message = "движок: {}".format(exc)
                job.fail(message)
                self._pending = None
                raise AsrError(message)
            job.mark_done(text, speech=True)
            self._pending = None
            return True
        self._pending = None
        return False

    def _run(self, job):
        while not job.finished():
            if not self.pump():
                break
        if job.state != STATE_DONE:
            raise AsrError(
                "не удалось распознать: {}".format(
                    job.error or job.state))
        return job.text

    def recognize_pcm(self, pcm, rate=None, channels=None):
        """Распознать буфер PCM."""
        return self._run(self.submit(pcm, rate, channels))

    def recognize_file(self, path):
        """Распознать файл PCM, WAV или MP3."""
        return self._run(self.submit(path))

    # --- микрофон --------------------------------------------------

    def _open_mic(self):
        factory = self._mic
        if factory is None:
            from micro_asr.sources.mic import MicroHalMic
            factory = MicroHalMic
        mic = factory() if callable(factory) else factory
        try:
            mic.open(rate=self.config.sample_rate, channels=1)
        except AsrError:
            raise
        except Exception as exc:
            raise AsrError("микрофон: {}".format(exc))
        return mic

    def _read_seconds(self, mic, seconds):
        rate = self.config.sample_rate
        need = int(round(seconds * rate)) * 2
        data = bytearray()
        while len(data) < need:
            chunk = mic.read(need - len(data))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > need:
            data = data[:need]
        return bytes(data)

    def _read_until_silence(self, mic, silence, max_seconds,
                            start_timeout, min_speech, threshold_db):
        detector = SpeechDetector(
            rate=self.config.sample_rate,
            silence=silence,
            start_timeout=start_timeout,
            max_seconds=max_seconds,
            min_speech=min_speech,
            threshold_db=threshold_db)
        data = bytearray()
        while not detector.finished:
            chunk = mic.read(MIC_CHUNK_BYTES)
            if not chunk:
                detector.finish()
                break
            data.extend(chunk)
            detector.feed(chunk)
        return bytes(data), detector.speech

    def _capture(self, seconds, until_silence, max_seconds,
                 start_timeout, min_speech, threshold_db):
        self._check()
        if seconds is not None:
            seconds = _positive_number(seconds, "seconds")
        job = self._new_job("microphone")
        self._last_job = job
        job.mark_capturing()
        mic = None
        try:
            mic = self._open_mic()
            if seconds is not None:
                pcm = self._read_seconds(mic, seconds)
                speech = bool(pcm)
            else:
                silence = (DEFAULT_SILENCE if until_silence is None
                           else _positive_number(until_silence,
                                                 "until_silence"))
                pcm, speech = self._read_until_silence(
                    mic, silence, max_seconds, start_timeout,
                    min_speech, threshold_db)
        except AsrError as exc:
            if not job.finished():
                job.fail(str(exc))
            raise
        except Exception as exc:
            message = "микрофон: {}".format(exc)
            if not job.finished():
                job.fail(message)
            raise AsrError(message)
        finally:
            if mic is not None:
                try:
                    mic.close()
                except Exception:
                    pass
        job.set_audio(pcm, self.config.sample_rate)
        job.speech = speech
        job.engine = self._engine.name if self._engine else None
        return job, pcm

    def capture(self, seconds=None, until_silence=None,
                max_seconds=DEFAULT_MAX_SECONDS,
                start_timeout=DEFAULT_START_TIMEOUT,
                min_speech=DEFAULT_MIN_SPEECH, threshold_db=None):
        """Записать звук и вернуть PCM; без распознавания."""
        job, pcm = self._capture(
            seconds, until_silence, max_seconds, start_timeout,
            min_speech, threshold_db)
        if job.state == STATE_CAPTURING:
            job.mark_done("", speech=job.speech)
        return pcm

    def listen(self, seconds=None, until_silence=None,
               max_seconds=DEFAULT_MAX_SECONDS,
               start_timeout=DEFAULT_START_TIMEOUT,
               min_speech=DEFAULT_MIN_SPEECH, threshold_db=None):
        """Записать с микрофона и распознать; пустая строка — тишина."""
        job, pcm = self._capture(
            seconds, until_silence, max_seconds, start_timeout,
            min_speech, threshold_db)
        if not job.speech or not pcm:
            job.mark_done("", speech=False)
            return ""
        try:
            self._ensure_engine()
            prepared = audio.prepare(
                pcm, self.config.sample_rate, 1, 2, self._rate)
            job.set_audio(prepared, self._rate)
            job.engine = self._engine.name
            job.mark_preparing()
            job.mark_recognizing()
            text = self._engine.recognize(prepared)
        except AsrError as exc:
            if not job.finished():
                job.fail(str(exc))
            raise
        except Exception as exc:
            message = "движок: {}".format(exc)
            if not job.finished():
                job.fail(message)
            raise AsrError(message)
        job.mark_done(text, speech=True)
        return text

    # --- управление ------------------------------------------------

    def stop(self):
        """Отменить текущую задачу; `True`, если что-то остановлено."""
        self._check()
        job = self._pending[0] if self._pending else None
        if job is not None and not job.finished():
            job.mark_stopped()
            self._pending = None
            return True
        job = self._last_job
        if job is not None and not job.finished():
            job.mark_stopped()
            return True
        return False

    def close(self):
        """Закрыть движок и освободить ресурсы."""
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
            self._pending = None
            self._closed = True
        return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
