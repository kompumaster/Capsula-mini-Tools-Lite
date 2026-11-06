"""Интерфейс транспорта."""

from micro_tts.errors import TtsError


class Transport:
    """Обмен текстовыми и бинарными сообщениями."""

    def connect(self, url, headers=None, timeout=10.0):
        """Подключиться; вернуть себя."""
        raise TtsError("транспорт не реализует connect()")

    def send_text(self, text):
        raise TtsError("транспорт не реализует send_text()")

    def send_binary(self, data):
        raise TtsError("транспорт не реализует send_binary()")

    def recv(self, timeout=None):
        """`("text"|"binary"|"close", payload)`."""
        raise TtsError("транспорт не реализует recv()")

    def close(self):
        raise TtsError("транспорт не реализует close()")
