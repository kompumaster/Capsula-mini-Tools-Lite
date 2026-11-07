"""Настройки сервера в JSON.

Файл читается при создании и пишется атомарно: временный файл и
`rename`. Пароли Wi-Fi здесь не хранятся — ими владеет система.
"""

import json
import os

from micro_server.config import DEFAULT_SETTINGS, DEFAULT_SETTINGS_PATH
from micro_server.errors import ServerError


class Store:
    """Настройки: значения по умолчанию плюс JSON-файл."""

    def __init__(self, path=DEFAULT_SETTINGS_PATH, defaults=None):
        if not isinstance(path, str) or not path.strip():
            raise ServerError("путь настроек должен быть строкой")
        self.path = path
        self._defaults = dict(
            DEFAULT_SETTINGS if defaults is None else defaults)
        self._data = dict(self._defaults)
        self.load()

    def load(self):
        """Прочитать файл; ошибка или мусор — значения по умолчанию."""
        try:
            handle = open(self.path, "r")
        except OSError:
            self._data = dict(self._defaults)
            return self.all()
        try:
            raw = handle.read()
        finally:
            handle.close()
        try:
            value = json.loads(raw)
        except Exception:
            self._data = dict(self._defaults)
            return self.all()
        if not isinstance(value, dict):
            self._data = dict(self._defaults)
            return self.all()
        data = dict(self._defaults)
        data.update(value)
        self._data = data
        return self.all()

    def all(self):
        """Копия всех настроек."""
        return dict(self._data)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        """Изменить и сразу сохранить."""
        if not isinstance(key, str) or not key.strip():
            raise ServerError("ключ настройки должен быть строкой")
        self._data[key] = value
        self.save()
        return value

    def update(self, values):
        """Изменить несколько настроек и сохранить один раз."""
        if not isinstance(values, dict):
            raise ServerError("настройки должны быть словарём")
        self._data.update(values)
        self.save()
        return self.all()

    def save(self):
        """Атомарная запись: временный файл и rename."""
        temp = self.path + ".tmp"
        try:
            handle = open(temp, "w")
            try:
                handle.write(json.dumps(self._data))
            finally:
                handle.close()
            os.rename(temp, self.path)
        except OSError as exc:
            try:
                os.remove(temp)
            except OSError:
                pass
            raise ServerError("не сохранить настройки: {}".format(exc))
        except Exception as exc:
            try:
                os.remove(temp)
            except OSError:
                pass
            raise ServerError("не сохранить настройки: {}".format(exc))
