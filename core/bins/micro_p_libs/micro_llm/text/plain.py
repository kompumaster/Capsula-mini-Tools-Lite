"""Плоский текст для запросов и ответов LLM.

Переносы строк и табуляция заменяются пробелом, повторные пробелы
схлопываются. В ответе дополнительно убираются markdown-маркеры `**`
и числовые ссылки вида `[1]`.
"""

_SKIP = " \t\r\n.,;:!?()[]{}<>\"'«»-"


def _word(char):
    """Похоже ли на букву или цифру (для границы при удалении ссылки)."""
    return bool(char) and char not in _SKIP


def _strip_refs(text):
    out = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "[":
            end = index + 1
            while end < length and text[end].isdigit():
                end += 1
            if end > index + 1 and end < length and text[end] == "]":
                before = out[-1] if out else ""
                after = text[end + 1] if end + 1 < length else ""
                if _word(before) and _word(after):
                    out.append(" ")
                index = end + 1
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _strip_markers(text):
    return _strip_refs(text.replace("**", ""))


def _spaces(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ").replace("\t", " ")
    return " ".join([part for part in text.split(" ") if part])


def one_line(text):
    """Строка без переносов и лишних пробелов."""
    if not isinstance(text, str):
        raise ValueError("текст должен быть строкой")
    return _spaces(text)


def clean_answer(text):
    """Ответ без markdown-маркеров и числовых ссылок."""
    if not isinstance(text, str):
        raise ValueError("текст должен быть строкой")
    return _spaces(_strip_markers(text))


def clean_chunk(text):
    """Кусок ответа для потока: маркеры убрать, пробелы не схлопывать."""
    text = _strip_markers(text)
    text = text.replace("\r\n", " ").replace("\r", " ")
    return text.replace("\n", " ").replace("\t", " ")


class AnswerCleaner:
    """Чистит поток по кускам, удерживая недописанный маркер."""

    def __init__(self):
        self.pending = ""

    def feed(self, piece):
        self.pending += piece
        hold = 0
        if self.pending.endswith("*") and not self.pending.endswith("**"):
            hold = 1
        index = self.pending.rfind("[")
        if index >= 0:
            tail = self.pending[index + 1:]
            if not tail or tail.isdigit():
                hold = max(hold, len(self.pending) - index)
        if hold:
            safe = self.pending[:-hold]
            self.pending = self.pending[-hold:]
        else:
            safe = self.pending
            self.pending = ""
        return clean_chunk(safe)

    def finish(self):
        rest = clean_chunk(self.pending)
        self.pending = ""
        return rest
