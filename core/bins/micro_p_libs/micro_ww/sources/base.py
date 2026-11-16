"""Источники звука: общий интерфейс.

`Source` отдаёт моно-PCM `s16le`, 16 кГц, окнами по 20 мс. Источник
не знает про модель и порог: это дело `WakeWord`.
"""

from micro_ww.errors import WwError


class Source:
    """Общий интерфейс источника звука."""

    name = "source"

    def open(self):
        return self

    def read(self):
        raise NotImplementedError

    def info(self):
        return {"name": self.name}

    def close(self):
        pass

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
