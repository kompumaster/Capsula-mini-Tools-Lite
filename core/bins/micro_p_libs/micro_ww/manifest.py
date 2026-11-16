"""Манифест модели microWakeWord.

Манифест — JSON рядом с `.tflite`:

```json
{
  "type": "micro",
  "wake_word": "Hey Jarvis",
  "model": "hey_jarvis.tflite",
  "version": 2,
  "micro": {
    "probability_cutoff": 0.97,
    "feature_step_size": 10,
    "sliding_window_size": 5,
    "tensor_arena_size": 22860
  }
}
```

Лишние поля (автор, сайт, языки) не мешают. Здесь только разбор и
проверки: файл модели не открывается.
"""

import json
import os

from micro_ww.errors import WwError

SUPPORTED_VERSIONS = (2,)
DEFAULT_LANGUAGES = ()


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise WwError("{} должен быть непустой строкой".format(name))
    return value.strip()


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise WwError("{} должен быть целым числом".format(name))
    if value < low or value > high:
        raise WwError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WwError("{} должен быть числом".format(name))
    value = float(value)
    if value != value:
        raise WwError("{} не может быть NaN".format(name))
    if value < low or value > high:
        raise WwError("{} должен быть в {}…{}".format(name, low, high))
    return value


def _is_absolute(path):
    return path.startswith("/") or path.startswith("\\")


def _dirname(path):
    index = max(path.rfind("/"), path.rfind("\\"))
    return path[:index] if index >= 0 else ""


def _join(base, name):
    if not base or _is_absolute(name):
        return name
    if base.endswith("/") or base.endswith("\\"):
        return base + name
    return base + "/" + name


def _exists(path):
    try:
        os.stat(path)
    except OSError:
        return False
    return True


class Manifest:
    """Разобранный и проверенный манифест."""

    def __init__(self, data, base_dir="", source=None,
                 check_model=False):
        if not isinstance(data, dict):
            raise WwError("манифест должен быть словарём")
        self.source = source
        self.base_dir = str(base_dir or "")

        kind = _text(data.get("type"), "type")
        if kind != "micro":
            raise WwError("type должен быть micro, а не {}".format(kind))

        version = _integer(data.get("version"), "version", 1, 1000)
        if version not in SUPPORTED_VERSIONS:
            raise WwError("версия манифеста {} не поддерживается".format(
                version))
        self.version = version

        self.wake_word = _text(data.get("wake_word"), "wake_word")

        model = _text(data.get("model"), "model")
        self.model = model
        self.model_path = _join(self.base_dir, model)

        micro = data.get("micro")
        if not isinstance(micro, dict):
            raise WwError("нет раздела micro")

        self.probability_cutoff = _number(
            micro.get("probability_cutoff"), "probability_cutoff", 0.0, 1.0)
        if self.probability_cutoff <= 0.0:
            raise WwError("probability_cutoff должен быть больше нуля")
        self.feature_step_size = _integer(
            micro.get("feature_step_size"), "feature_step_size", 1, 1000)
        self.sliding_window_size = _integer(
            micro.get("sliding_window_size"), "sliding_window_size",
            1, 1000)
        self.tensor_arena_size = _integer(
            micro.get("tensor_arena_size"), "tensor_arena_size", 1,
            64 * 1024 * 1024)

        languages = data.get("trained_languages")
        if languages is None:
            languages = list(DEFAULT_LANGUAGES)
        if not isinstance(languages, (list, tuple)):
            raise WwError("trained_languages должен быть списком")
        self.trained_languages = []
        for item in languages:
            self.trained_languages.append(
                _text(item, "trained_languages[]"))

        if check_model and not _exists(self.model_path):
            raise WwError("нет файла модели: {}".format(self.model_path))

    @classmethod
    def load(cls, path):
        """Прочитать манифест из файла и проверить файл модели."""
        path = _text(path, "путь манифеста")
        try:
            handle = open(path, "r")
        except OSError as exc:
            raise WwError("не открыть манифест {}: {}".format(path, exc))
        try:
            try:
                data = json.load(handle)
            except Exception as exc:
                raise WwError("манифест {}: {}".format(path, exc))
        finally:
            handle.close()
        return cls(data, base_dir=_dirname(path), source=path,
                   check_model=True)

    @classmethod
    def from_data(cls, data, base_dir="", check_model=False):
        """Манифест из словаря — для тестов и внешних вызовов."""
        return cls(data, base_dir=base_dir, check_model=check_model)

    def as_dict(self):
        """Словарь для отладки и `status()`."""
        return {
            "wake_word": self.wake_word,
            "model": self.model,
            "model_path": self.model_path,
            "version": self.version,
            "probability_cutoff": self.probability_cutoff,
            "feature_step_size": self.feature_step_size,
            "sliding_window_size": self.sliding_window_size,
            "tensor_arena_size": self.tensor_arena_size,
            "trained_languages": list(self.trained_languages),
        }

    def __repr__(self):
        return "Manifest({!r}, {})".format(
            self.wake_word, self.model_path)
