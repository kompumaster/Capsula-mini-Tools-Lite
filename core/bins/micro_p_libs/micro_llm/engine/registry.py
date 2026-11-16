"""Реестр LLM-движков.

Встроенные адаптеры регистрируются лениво, при первом обращении к
реестру. Импорт пакета не загружает движки.
"""

from micro_llm.engine.base import Engine
from micro_llm.errors import LlmError

DEFAULT_ENGINE = "fake"

_ENGINES = {}
_BUILTINS_LOADED = False

_NAME_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def _check_name(name):
    if not isinstance(name, str):
        raise LlmError("имя движка должно быть строкой")
    name = name.strip()
    if not name:
        raise LlmError("пустое имя движка")
    for char in name:
        if char not in _NAME_CHARS:
            raise LlmError("неверное имя движка: {!r}".format(name))
    return name


def _load_builtins():
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    _BUILTINS_LOADED = True
    from micro_llm import engines  # noqa: F401


def register_engine(name, factory, replace=False):
    """Зарегистрировать движок; вернуть нормализованное имя."""
    name = _check_name(name)
    if not callable(factory):
        raise LlmError("движок {}: фабрика не вызывается".format(name))
    if name in _ENGINES and not replace:
        raise LlmError("движок {} уже зарегистрирован".format(name))
    _ENGINES[name] = factory
    return name


def available_engines():
    """Имена зарегистрированных движков, по алфавиту."""
    _load_builtins()
    return sorted(_ENGINES.keys())


def get_engine(spec=None):
    """Движок по имени или готовый объект (создан, но не открыт)."""
    _load_builtins()
    if isinstance(spec, Engine):
        return spec
    if spec is None:
        spec = DEFAULT_ENGINE
    if not isinstance(spec, str):
        raise LlmError("движок должен быть именем или объектом Engine")
    name = _check_name(spec)
    if name not in _ENGINES:
        raise LlmError("неизвестный движок {}; есть: {}".format(
            name, ", ".join(available_engines())))
    factory = _ENGINES[name]
    try:
        engine = factory()
    except LlmError:
        raise
    except Exception as exc:
        raise LlmError("не создать движок {}: {}".format(name, exc))
    if not isinstance(engine, Engine):
        raise LlmError("движок {} вернул не Engine".format(name))
    return engine
