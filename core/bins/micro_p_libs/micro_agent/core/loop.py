"""Кооперативный цикл и таймеры.

Время всегда передаётся снаружи (`now_ms`), поэтому цикл и таймеры
детерминированы и проверяются без платы. Никаких потоков.
"""

from micro_agent.core.events import Event


def _events(value):
    if value is None:
        return []
    if isinstance(value, Event):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    raise ValueError("poll() должен вернуть Event, список или None")


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("{} должен быть положительным целым".format(name))
    return value


def _delay(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("{} должен быть целым неотрицательным".format(name))
    return value


class Scheduler:
    """Периодические и одноразовые задачи по миллисекундам."""

    def __init__(self):
        self._tasks = {}
        self._counter = 0

    def _name(self, name):
        if name is None:
            self._counter += 1
            return "task-{}".format(self._counter)
        if not isinstance(name, str) or not name:
            raise ValueError("имя задачи должно быть непустой строкой")
        if name in self._tasks:
            raise ValueError("задача {} уже есть".format(name))
        return name

    def every(self, interval_ms, callback, name=None):
        interval_ms = _positive_int(interval_ms, "interval_ms")
        if not callable(callback):
            raise ValueError("callback не вызывается")
        name = self._name(name)
        self._tasks[name] = {
            "callback": callback,
            "at": interval_ms,
            "interval": interval_ms,
            "repeat": True,
        }
        return name

    def after(self, delay_ms, callback, name=None):
        delay_ms = _delay(delay_ms, "delay_ms")
        if not callable(callback):
            raise ValueError("callback не вызывается")
        name = self._name(name)
        self._tasks[name] = {
            "callback": callback,
            "at": delay_ms,
            "interval": 0,
            "repeat": False,
        }
        return name

    def cancel(self, name):
        return self._tasks.pop(name, None) is not None

    def clear(self):
        self._tasks = {}

    def names(self):
        return sorted(self._tasks.keys())

    def poll(self, now_ms):
        """Выполнить задачи, срок которых наступил; вернуть события."""
        now_ms = _delay(now_ms, "now_ms")
        events = []
        for name, task in list(self._tasks.items()):
            if name not in self._tasks:
                continue
            if task["at"] > now_ms:
                continue
            result = task["callback"]()
            events.extend(_events(result))
            if task["repeat"]:
                # Догоняющие запуски не нужны: следующая точка — от now.
                if name in self._tasks:
                    task["at"] = now_ms + task["interval"]
            else:
                self._tasks.pop(name, None)
        return events

    def next_delay(self, now_ms):
        """Сколько миллисекунд до ближайшей задачи или None."""
        if not self._tasks:
            return None
        now_ms = _delay(now_ms, "now_ms")
        delay = None
        for task in self._tasks.values():
            value = task["at"] - now_ms
            if value < 0:
                value = 0
            if delay is None or value < delay:
                delay = value
        return delay


class Loop:
    """Модули + планировщик: один кооперативный шаг."""

    def __init__(self, scheduler=None):
        self.scheduler = scheduler if scheduler is not None else Scheduler()
        self.modules = []

    def add(self, module):
        if not hasattr(module, "poll") or not callable(module.poll):
            raise ValueError("модуль должен иметь poll(now_ms)")
        self.modules.append(module)
        return module

    def remove(self, module):
        try:
            self.modules.remove(module)
        except ValueError:
            return False
        return True

    def poll(self, now_ms):
        """Опросить модули и таймеры; вернуть список событий."""
        events = []
        for module in list(self.modules):
            events.extend(_events(module.poll(now_ms)))
        events.extend(self.scheduler.poll(now_ms))
        return events
