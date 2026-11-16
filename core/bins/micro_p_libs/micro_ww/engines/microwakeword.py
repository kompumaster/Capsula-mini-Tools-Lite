"""Движок microWakeWord через C-рантайм `libc_ww.so`.

Модель и манифест - данные. Движок возвращает вероятности по шагам,
а окно, порог и пауза - дело координатора.
"""

from micro_ww.engines.base import Engine
from micro_ww.errors import WwError
from micro_ww.manifest import Manifest
from micro_ww.runtime import Runtime


def _sample_rate(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise WwError("sample_rate должен быть целым числом")
    if value != 16000:
        raise WwError("microWakeWord работает только на 16 кГц")
    return value


def _arena(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WwError("arena_size должен быть целым неотрицательным")
    return value


def _step(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise WwError("step_ms должен быть целым числом")
    if value < 1 or value > 1000:
        raise WwError("step_ms должен быть в 1…1000")
    return value


class MicroWakeWordEngine(Engine):
    """Модель microWakeWord: PCM → вероятности."""

    name = "microwakeword"
    version = "1"

    def __init__(self):
        Engine.__init__(self)
        self.manifest = None
        self.runtime = None
        self.sample_rate = 16000
        self.step_ms = 10
        self.library = None

    def open(self, model=None, sample_rate=16000, **options):
        sample_rate = _sample_rate(sample_rate)
        if model is None:
            model = options.get("model")
        if model is None:
            raise WwError("нужен манифест модели")
        if isinstance(model, Manifest):
            manifest = model
        elif isinstance(model, str):
            manifest = Manifest.load(model)
        else:
            raise WwError("модель должна быть путём к манифесту или Manifest")

        arena = options.get("arena_size", manifest.tensor_arena_size)
        arena = _arena(arena)
        step = _step(options.get("step_ms", manifest.feature_step_size))
        library = options.get("library") or self.library

        if self._opened:
            self.close()
        runtime = Runtime(path=library)
        try:
            runtime.open(manifest.model_path, arena, step)
        except Exception:
            runtime.close()
            raise

        self.manifest = manifest
        self.runtime = runtime
        self.sample_rate = sample_rate
        self.step_ms = step
        self._opened = True
        return self

    def push(self, pcm):
        self._require_opened()
        if not isinstance(pcm, (bytes, bytearray)):
            raise WwError("PCM должен быть bytes или bytearray")
        if len(pcm) % 2:
            raise WwError("PCM должен содержать целые 16-битные сэмплы")
        if not pcm:
            return []
        return self.runtime.push(pcm)

    def reset(self):
        self._require_opened()
        return self.runtime.reset()

    def close(self):
        if self.runtime is not None:
            self.runtime.close()
            self.runtime = None
        self._opened = False
        return True

    def info(self):
        result = {
            "name": self.name,
            "version": self.version,
            "sample_rate": self.sample_rate,
            "step_ms": self.step_ms,
        }
        if self.manifest is not None:
            result.update({
                "wake_word": self.manifest.wake_word,
                "model_path": self.manifest.model_path,
                "probability_cutoff": self.manifest.probability_cutoff,
                "sliding_window_size": self.manifest.sliding_window_size,
            })
        if self.runtime is not None:
            result["arena_used"] = self.runtime.arena_used()
            result["backend"] = self.runtime.backend
        return result
