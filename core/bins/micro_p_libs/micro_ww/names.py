"""Имя помощника по имени файла модели ключевого слова.

Имя модели обычно выглядит как `<префикс>_<имя>.json`; берём последний
кусок после `_`. Например, `hey_jarvis.json` даёт `Jarvis`,
`окей_валера.json` даёт `Валера`, `hola_amigo_alice.json` даёт
`Alice`.
"""

_SUFFIXES = (".json", ".tflite")

_UPPER = {
    "а": "А", "б": "Б", "в": "В", "г": "Г", "д": "Д", "е": "Е",
    "ё": "Ё", "ж": "Ж", "з": "З", "и": "И", "й": "Й", "к": "К",
    "л": "Л", "м": "М", "н": "Н", "о": "О", "п": "П", "р": "Р",
    "с": "С", "т": "Т", "у": "У", "ф": "Ф", "х": "Х", "ц": "Ц",
    "ч": "Ч", "ш": "Ш", "щ": "Щ", "ъ": "Ъ", "ы": "Ы", "ь": "Ь",
    "э": "Э", "ю": "Ю", "я": "Я",
}


def _capitalize(text):
    """Первая буква заглавная; кириллицу MicroPython не поднимает."""
    if not text:
        return text
    first = text[0]
    upper = _UPPER.get(first)
    if upper is None:
        upper = first.upper()
    return upper + text[1:]


def model_name(path):
    """Имя из пути к модели; пустая строка, если не разобрать."""
    if not isinstance(path, str):
        return ""
    text = path.strip().replace("\\", "/")
    if not text:
        return ""
    name = text.split("/")[-1]
    lower = name.lower()
    for suffix in _SUFFIXES:
        if lower.endswith(suffix):
            name = name[:-len(suffix)]
            break
    word = name.split("_")[-1].strip()
    if not word:
        return ""
    return _capitalize(word)
