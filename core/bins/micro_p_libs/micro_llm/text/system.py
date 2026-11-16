"""Системный промпт из файла.

Читается один раз при создании сессии; не весит в памяти больше
`limit` символов.
"""

DEFAULT_SYSTEM_FILE = "/home/system.txt"
DEFAULT_SYSTEM_CHARS = 2000


def limit_text(text, limit):
    """Обрезать текст до `limit` символов с многоточием."""
    if not isinstance(text, str):
        raise ValueError("текст должен быть строкой")
    if limit is None or limit < 0:
        return text
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[:limit - 1] + "…"


def load_system(path=DEFAULT_SYSTEM_FILE, limit=DEFAULT_SYSTEM_CHARS):
    """Прочитать системный промпт; нет файла — пустая строка."""
    try:
        handle = open(path, "r")
    except OSError:
        return ""
    try:
        text = handle.read()
    finally:
        handle.close()
    return limit_text(text.strip(), limit)
