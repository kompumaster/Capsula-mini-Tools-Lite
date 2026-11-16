"""Нормализация короткого текста для прямых команд."""

PUNCTUATION = ".,!?;:…---\"'()[]{}«»/\\"


def _lower_char(char):
    """Опустить кириллицу: MicroPython `str.lower()` её не трогает."""
    code = ord(char)
    if 0x410 <= code <= 0x42F:      # А…Я
        return chr(code + 0x20)
    if code == 0x401:               # Ё
        return "ё"
    return char


def normalize(text):
    """Строчные, без пунктуации, ё → е, один пробел между словами."""
    if not isinstance(text, str):
        return ""
    value = "".join(_lower_char(char) for char in text.lower())
    value = value.replace("ё", "е")
    chars = []
    for char in value:
        chars.append(" " if char in PUNCTUATION else char)
    return " ".join("".join(chars).split())


def has_word(text, word):
    return word in text.split()


def has_any(text, words):
    for word in words:
        if word in text:
            return True
    return False
