"""Русский текст: пробелы, пунктуация, предложения и чанки.

Полная нормализация чисел, дат и сокращений — отдельная задача.
Здесь только структура, достаточная для синтеза.
"""

from micro_tts.errors import TtsError
from micro_tts.text.base import Normalizer

# Сокращения, после которых точка не завершает предложение.
_ABBREVIATIONS = frozenset((
    "т.е.", "т.д.", "т.п.", "т.к.", "т.н.",
    "г.", "гг.", "ул.", "др.", "см.", "рис.", "стр.",
    "мин.", "сек.", "руб.", "коп.", "млн.", "млрд.", "тыс.",
    "проф.", "акад.", "п.", "пп.", "кв.", "им.", "пр.",
))

_TERMINATORS = ".!?…"
_CLOSERS = '")]}»”’'


def _normalize(text):
    """Пробелы, тире и кавычки к простому виду."""
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    for char in ("\t", "\r", "\n"):
        text = text.replace(char, " ")
    for dash in ("\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
        text = text.replace(dash, "-")
    for quote in ("\u00ab", "\u00bb", "\u201c", "\u201d",
                  "\u201e", "\u2018", "\u2019"):
        text = text.replace(quote, '"')
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def _token_before(text, index):
    """Слово перед точкой, без самой точки."""
    start = index
    while start > 0:
        char = text[start - 1]
        if char.isspace() or char in '([{"':
            break
        start -= 1
    return text[start:index]


def _is_initials(token):
    """`И.` или `А.С.` — инициалы, а не конец предложения."""
    body = token[:-1] if token.endswith(".") else token
    if len(body) == 1 and body.isalpha() and body.isupper():
        return True
    if "." in body:
        parts = body.split(".")
        return all(len(part) == 1 and part.isalpha() and part.isupper()
                   for part in parts)
    return False


def _is_decimal(text, index, end):
    return (index > 0 and text[index - 1].isdigit()
            and end < len(text) and text[end].isdigit())


def _sentence_end(text, start, end):
    """Завершает ли пунктуация `text[start:end]` предложение."""
    run = text[start:end]
    if len(run) > 1 or run == "…":
        return True
    if run in ("!", "?"):
        return True
    if run != ".":
        return True

    token = _token_before(text, start) + "."
    if token.lower() in _ABBREVIATIONS:
        return False
    if _is_decimal(text, start, end):
        return False
    if _is_initials(token):
        return False
    return True


def _sentences(text):
    """Разбить текст на предложения."""
    result = []
    start = 0
    index = 0
    total = len(text)
    while index < total:
        if text[index] not in _TERMINATORS:
            index += 1
            continue

        run_start = index
        while index < total and text[index] in _TERMINATORS:
            index += 1
        run_end = index

        close_end = index
        while close_end < total and text[close_end] in _CLOSERS:
            close_end += 1

        if not _sentence_end(text, run_start, run_end):
            index = close_end
            continue

        next_index = close_end
        while next_index < total and text[next_index].isspace():
            next_index += 1
        if next_index >= total:
            sentence = text[start:close_end].strip()
            if sentence:
                result.append(sentence)
            start = total
            break

        next_char = text[next_index]
        if next_char.islower() or next_char.isdigit():
            index = close_end
            continue

        sentence = text[start:close_end].strip()
        if sentence:
            result.append(sentence)
        start = next_index
        index = next_index

    if start < total:
        sentence = text[start:].strip()
        if sentence:
            result.append(sentence)
    return result


def _split_long(sentence, limit):
    """Разбить слишком длинное предложение, не превышая `limit`."""
    if len(sentence) <= limit:
        return [sentence]
    chunks = []
    rest = sentence
    while len(rest) > limit:
        window = rest[:limit]
        cut = -1
        for mark in (",", ";", ":"):
            position = window.rfind(mark)
            if position > cut:
                cut = position
        if cut > 0:
            chunk = rest[:cut + 1].strip()
            if chunk:
                chunks.append(chunk)
            rest = rest[cut + 1:].strip()
            continue
        cut = window.rfind(" ")
        if cut > 0:
            chunk = rest[:cut].strip()
            if chunk:
                chunks.append(chunk)
            rest = rest[cut:].strip()
            continue
        chunk = rest[:limit].strip()
        if chunk:
            chunks.append(chunk)
        rest = rest[limit:].strip()
    if rest:
        chunks.append(rest)
    return [chunk for chunk in chunks if chunk]


class RussianNormalizer(Normalizer):
    """Нормализатор русского текста по умолчанию."""

    language = "ru"
    version = "1"

    def prepare(self, text, limit=200):
        if not isinstance(text, str):
            raise TtsError("текст должен быть строкой")
        if (isinstance(limit, bool) or not isinstance(limit, int)
                or limit <= 0):
            raise TtsError("limit должен быть положительным целым")
        text = _normalize(text)
        if not text:
            raise TtsError("текст пустой")
        sentences = _sentences(text)
        if not sentences:
            raise TtsError("текст пустой")
        chunks = []
        for sentence in sentences:
            chunks.extend(_split_long(sentence, limit))
        result = [chunk.strip() for chunk in chunks if chunk.strip()]
        if not result:
            raise TtsError("текст пустой")
        return result
