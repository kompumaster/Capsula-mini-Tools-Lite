"""Смайлы дисплея: 7-сегментные маски.

Биты: 0 - a, 1 - b, …, 6 - g. Лицо рисуется двумя «глазами» на
позициях 0 и 2, между ними - нижняя точка двоеточия.
"""

from micro_ui.errors import UiError

# a=1, b=2, c=4, d=8, e=16, f=32, g=64
GLYPHS = {
    " ": 0x00,
    "-": 0x40,
    "0": 0x3F,
    "O": 0x3F,
    "8": 0x7F,
    "o": 0x5C,
    "о": 0x5C,
    "П": 0x37,
    "п": 0x33,
    "u": 0x1C,
    "U": 0x3E,
}

# Имя лица -> (левый глаз, правый глаз)
FACES = {
    "flat": ("-", "-"),
    "wink": ("о", "-"),
    "eyes": ("0", "0"),
    "calm": ("о", "0"),
    "round": ("о", "о"),
    "wide": ("П", "П"),
    "narrow": ("п", "п"),
    "smile": ("u", "u"),
    "big": ("U", "U"),
    "speech": ("8", "8"),
}

# Псевдонимы для внешних вызовов.
ALIASES = {
    "sleep": "flat",
    "neutral": "flat",
    "happy": "eyes",
    "joy": "eyes",
    "surprise": "wide",
    "sad": "narrow",
    # старые имена режимов
    "error": "flat",
    "think": "wink",
    "speak": "big",
}

# Режимы агента -> лицо.
MODE_FACES = {
    "wake": "eyes",
    "asr": "calm",
    "think": "wink",
    "speak": "speech",
    "error": "flat",
}

FACE_COLON = (False, True)


def face_names():
    """Все доступные имена, включая псевдонимы."""
    return tuple(FACES.keys()) + tuple(ALIASES.keys())


def _name(name):
    if not isinstance(name, str) or not name:
        raise UiError("имя смайла должно быть непустой строкой")
    name = name.lower()
    if name in ALIASES:
        name = ALIASES[name]
    if name not in FACES:
        raise UiError("неизвестный смайл: {}".format(name))
    return name


def face_masks(name):
    """Четыре маски лица: глаза по краям, точка двоеточия в центре."""
    left, right = FACES[_name(name)]
    return (GLYPHS[left], 0, 0, GLYPHS[right])


def face_glyphs(name):
    """Пара символов лица (для документации/тестов)."""
    return FACES[_name(name)]
