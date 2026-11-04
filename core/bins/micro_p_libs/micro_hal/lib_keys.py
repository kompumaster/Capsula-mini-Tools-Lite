"""Логика кнопок CSK05T поверх `hal_keys`.

Одна клавиша: дебаунс, press/release, удержание, автоповтор, клики.
Сочетания клавиш — следующий слой.
"""

import time

from micro_hal import hal_keys
from micro_hal.hal_common import HalError

__all__ = ["NAMES", "COMBOS", "Keys"]

NAMES = {
    114: "vol-",
    115: "vol+",
    164: "play",
    248: "mic",
    704: "fun",
}

COMBOS = (
    ((114, 115), "vol-+vol+"),
    ((164, 115), "play+vol+"),
    ((164, 114), "play+vol-"),
)


def _default_now():
    try:
        return time.ticks_ms()
    except AttributeError:
        return int(time.monotonic() * 1000)


def _elapsed(now, then):
    try:
        return time.ticks_diff(now, then)
    except AttributeError:
        return now - then


def _state():
    return {
        "pressed": False,
        "debouncing": False,
        "debounce_at": 0,
        "press_at": 0,
        "hold_sent": False,
        "step_at": 0,
        "step_count": 0,
        "clicks": 0,
        "release_at": 0,
        "suppressed": False,
        "combo": None,
    }


class Keys:
    """Состояние клавиш и события `(name, action, count)`."""

    def __init__(self, device=None, debounce=40, hold=600, click=350,
                 combo=100, step=150, now=None):
        for label, value in (
                ("debounce", debounce), ("hold", hold),
                ("click", click), ("combo", combo), ("step", step)):
            if value < 0:
                raise HalError("{} не может быть отрицательным".format(label))
        if step <= 0:
            raise HalError("step должен быть больше нуля")
        self.device = device
        self.debounce = int(debounce)
        self.hold = int(hold)
        self.click = int(click)
        self.combo = int(combo)
        self.step = int(step)
        self._now = now if now is not None else _default_now
        self._states = {}
        self._active = {}
        self._pending = []

    def _state(self, code):
        if code not in NAMES:
            return None
        state = self._states.get(code)
        if state is None:
            state = _state()
            self._states[code] = state
        return state

    def _confirm(self, state, name, now):
        state["pressed"] = True
        state["debouncing"] = False
        state["press_at"] = now
        state["hold_sent"] = False
        state["step_at"] = now
        state["step_count"] = 0
        state["release_at"] = 0
        if state["suppressed"]:
            return []
        return [(name, "press", 0)]

    def _detect_combo(self, code, now):
        events = []
        for keys, name in COMBOS:
            if code not in keys or name in self._active:
                continue
            states = []
            found = True
            for key in keys:
                state = self._states.get(key)
                if (state is None
                        or not (state["pressed"] or state["debouncing"])
                        or state["suppressed"]):
                    found = False
                    break
                states.append(state)
            if not found:
                continue
            times = [state["debounce_at"] for state in states]
            if any(_elapsed(times[index], times[0]) > self.combo
                   for index in range(1, len(times))):
                continue
            self._active[name] = {
                "keys": keys,
                "since": now,
                "hold_sent": False,
            }
            for state in states:
                state["suppressed"] = True
                state["combo"] = name
                state["clicks"] = 0
                state["release_at"] = 0
                state["hold_sent"] = False
                state["step_count"] = 0
            events.append((name, "combo", 0))
            break
        return events

    def _release_suppressed(self, state, code, now):
        state["pressed"] = False
        state["debouncing"] = False
        events = []
        for name, combo in list(self._active.items()):
            if code not in combo["keys"]:
                continue
            keys = combo["keys"]
            if all(not (self._states[key]["pressed"]
                        or self._states[key]["debouncing"])
                   for key in keys):
                del self._active[name]
                for key in keys:
                    other = self._states[key]
                    other["suppressed"] = False
                    other["combo"] = None
                    other["clicks"] = 0
                    other["release_at"] = 0
                    other["hold_sent"] = False
                    other["step_count"] = 0
                events.append((name, "combo_release", 0))
        return events

    def _release(self, state, name, now):
        state["pressed"] = False
        state["debouncing"] = False
        events = [(name, "release", 0)]
        if state["hold_sent"]:
            state["clicks"] = 0
            state["release_at"] = 0
        else:
            state["clicks"] += 1
            state["release_at"] = now
        state["hold_sent"] = False
        return events

    def feed(self, kind, code, value, now=None):
        """Обработать одно evdev-событие; вернуть мгновенные события."""
        if kind != hal_keys.EV_KEY:
            return []
        state = self._state(code)
        if state is None:
            return []
        if now is None:
            now = self._now()
        name = NAMES[code]
        events = []

        if value == 1:
            if (state["pressed"] or state["debouncing"]
                    or state["suppressed"]):
                return []
            state["debouncing"] = True
            state["debounce_at"] = now
            events.extend(self._detect_combo(code, now))
            if self.debounce == 0:
                events.extend(self._confirm(state, name, now))
        elif value == 0:
            if state["suppressed"]:
                events.extend(
                    self._release_suppressed(state, code, now))
                return events
            if state["debouncing"] and not state["pressed"]:
                state["debouncing"] = False
                return []
            if state["pressed"]:
                events.extend(self._release(state, name, now))
        return events

    def tick(self, now=None):
        """Проверить таймеры и вернуть события удержания/клика."""
        if now is None:
            now = self._now()
        events = []
        for name, combo in list(self._active.items()):
            if combo["hold_sent"]:
                continue
            keys = combo["keys"]
            if not all(self._states[key]["pressed"]
                       or self._states[key]["debouncing"]
                       for key in keys):
                continue
            if _elapsed(now, combo["since"]) >= self.hold:
                combo["hold_sent"] = True
                events.append((name, "combo_hold", 0))

        for code, state in self._states.items():
            name = NAMES[code]

            if state["debouncing"] and not state["pressed"]:
                if _elapsed(now, state["debounce_at"]) >= self.debounce:
                    events.extend(self._confirm(state, name, now))

            if state["suppressed"]:
                continue

            if state["pressed"] and not state["hold_sent"]:
                if _elapsed(now, state["press_at"]) >= self.hold:
                    events.append((name, "hold", state["clicks"]))
                    state["clicks"] = 0
                    state["release_at"] = 0
                    state["hold_sent"] = True
                    state["step_at"] = now
                    state["step_count"] = 0

            if state["pressed"] and state["hold_sent"]:
                if _elapsed(now, state["step_at"]) >= self.step:
                    state["step_count"] += 1
                    events.append((name, "step", state["step_count"]))
                    state["step_at"] = now

            if (not state["pressed"] and not state["debouncing"]
                    and state["clicks"] > 0 and state["release_at"]
                    and _elapsed(now, state["release_at"]) >= self.click):
                count = state["clicks"]
                events.append((name, "click", count))
                if count == 1:
                    events.append((name, "single", 1))
                elif count == 2:
                    events.append((name, "double", 2))
                elif count == 3:
                    events.append((name, "triple", 3))
                state["clicks"] = 0
                state["release_at"] = 0
        return events

    def poll(self, timeout_ms=0):
        """Прочитать события устройства и обработать таймеры."""
        if self.device is None:
            raise HalError("устройство ввода не подключено")
        timeout_ms = max(0, int(timeout_ms))
        events = []
        if timeout_ms == 0:
            while True:
                raw = self.device.poll(0)
                if not raw:
                    break
                for event in raw:
                    events.extend(self.feed(event[2], event[3], event[4]))
            events.extend(self.tick())
            return events

        start = self._now()
        while True:
            remaining = timeout_ms - _elapsed(self._now(), start)
            if remaining <= 0:
                events.extend(self.tick())
                return events
            for event in self.device.poll(min(20, remaining)):
                events.extend(self.feed(event[2], event[3], event[4]))
            events.extend(self.tick())
            if events:
                return events

    def wait(self, timeout_ms=None):
        """Одно событие; без таймаута ждёт бесконечно.

        События из одного `poll()` не теряются: например, клик даёт
        `click` и `single`/`double` сразу, и второй вызов `wait()`
        вернёт второе событие из очереди.
        """
        if self._pending:
            return self._pending.pop(0)
        if timeout_ms is None:
            while True:
                self._pending.extend(self.poll(200))
                if self._pending:
                    return self._pending.pop(0)
        self._pending.extend(self.poll(timeout_ms))
        return self._pending.pop(0) if self._pending else None

    def pressed(self):
        """Набор подтверждённых нажатых клавиш."""
        return {NAMES[code] for code, state in self._states.items()
                if state["pressed"]}

    def reset(self):
        self._states = {}
        self._active = {}
        self._pending = []

    def close(self):
        if self.device is not None:
            self.device.close()
