"""Реестр движков распознавания.

Встроенные адаптеры регистрируются лениво, при первом обращении к
реестру. Импорт пакета не загружает движки.
"""

from micro_asr.engines.base import Engine
from micro_asr.errors import AsrError

DEFAULT_ENGINE = "fake"

_ENGINES = {}
_BUILTINS_LOADED = False

_NAME_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)


def _check_name(name):
    if not isinstance(name, str):
        raise AsrError("имя движка должно быть строкой")
    name = name.strip()
    if not name:
        raise AsrError("пустое имя движка")
    for char in name:
        if char not in _NAME_CHARS:
            raise AsrError("неверное имя движка: {!r}".format(name))
    return name


def _load_builtins():
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    _BUILTINS_LOADED = True
    # Флаг выше защищает от повторного входа, если адаптер сам
    # обратится к реестру.
    from micro_asr.engines.fake import FakeEngine
    register_engine("fake", FakeEngine)
    from micro_asr.engines.yandexv1 import YandexV1Engine
    register_engine("yandexv1", YandexV1Engine)


def register_engine(name, factory, replace=False):
    """Зарегистрировать движок; вернуть нормализованное имя.

    `factory` — класс или функция без аргументов, возвращающая
    объект `Engine`. Повторное имя без `replace=True` — ошибка.
    """
    name = _check_name(name)
    if not callable(factory):
        raise AsrError("движок {}: фабрика не вызывается".format(name))
    if name in _ENGINES and not replace:
        raise AsrError("движок {} уже зарегистрирован".format(name))
    _ENGINES[name] = factory
    return name


def available_engines():
    """Имена зарегистрированных движков, по алфавиту."""
    _load_builtins()
    return sorted(_ENGINES.keys())


def get_engine(spec=None):
    """Получить движок по имени или готовому объекту.

    `None` — движок по умолчанию. Движок создаётся, но не
    открывается.
    """
    _load_builtins()
    if isinstance(spec, Engine):
        return spec
    if spec is None:
        spec = DEFAULT_ENGINE
    if not isinstance(spec, str):
        raise AsrError("движок должен быть именем или объектом Engine")
    name = _check_name(spec)
    if name not in _ENGINES:
        raise AsrError("неизвестный движок {}; есть: {}".format(
            name, ", ".join(available_engines())))
    factory = _ENGINES[name]
    try:
        engine = factory()
    except AsrError:
        raise
    except Exception as exc:
        raise AsrError("не создать движок {}: {}".format(name, exc))
    if not isinstance(engine, Engine):
        raise AsrError("движок {} вернул не Engine".format(name))
    return engine
