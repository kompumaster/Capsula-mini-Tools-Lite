"""Интерфейс кеша."""

from micro_tts.errors import TtsError


class Cache:
    """Хранилище готового аудио по ключу."""

    def get(self, key, text=None):
        """`(pcm, rate, meta)` или `None`; `text` — проверка коллизии."""
        raise TtsError("кеш не реализует get()")

    def put(self, key, pcm, rate, meta=None):
        """Сохранить; ошибка не должна ломать синтез."""
        raise TtsError("кеш не реализует put()")

    def info(self):
        """Записи, байты, попадания и промахи."""
        raise TtsError("кеш не реализует info()")

    def clear(self):
        """Удалить всё; повторный вызов безопасен."""
        raise TtsError("кеш не реализует clear()")
