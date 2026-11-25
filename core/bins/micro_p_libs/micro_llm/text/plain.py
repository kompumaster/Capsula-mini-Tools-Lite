"""Плоский текст для запросов и ответов LLM.

Переносы строк и табуляция заменяются пробелом, повторные пробелы
схлопываются. Так текст уходит в модель и озвучивается без лишних
разрывов; пунктуация не меняется.
"""


def one_line(text):
    """Строка без переносов и лишних пробелов."""
    if not isinstance(text, str):
        raise ValueError("текст должен быть строкой")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ").replace("\t", " ")
    words = [part for part in text.split(" ") if part]
    return " ".join(words)
