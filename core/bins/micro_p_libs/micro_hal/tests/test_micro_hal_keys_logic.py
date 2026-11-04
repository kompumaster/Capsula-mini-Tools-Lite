#!/usr/bin/env python3
"""Тесты lib_keys: одна клавиша, удержание, клики, автоповтор."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import hal_keys, lib_keys  # noqa: E402
from micro_hal.hal_common import HalError  # noqa: E402

VOL_UP = 115
VOL_DOWN = 114
PLAY = 164
MIC = 248
FUN = 704


def press(keys, code, now):
    return keys.feed(hal_keys.EV_KEY, code, 1, now)


def release(keys, code, now):
    return keys.feed(hal_keys.EV_KEY, code, 0, now)


class Params(unittest.TestCase):
    def test_names(self):
        self.assertEqual(lib_keys.NAMES[VOL_UP], "vol+")
        self.assertEqual(lib_keys.NAMES[VOL_DOWN], "vol-")
        self.assertEqual(lib_keys.NAMES[PLAY], "play")
        self.assertEqual(lib_keys.NAMES[MIC], "mic")
        self.assertEqual(lib_keys.NAMES[FUN], "fun")

    def test_bad_params(self):
        with self.assertRaises(HalError):
            lib_keys.Keys(step=0)
        with self.assertRaises(HalError):
            lib_keys.Keys(debounce=-1)


class OneKey(unittest.TestCase):
    def keys(self, **kwargs):
        params = dict(debounce=10, hold=100, click=50, step=20)
        params.update(kwargs)
        return lib_keys.Keys(**params)

    def test_press_debounce(self):
        keys = self.keys()
        self.assertEqual(press(keys, VOL_UP, 0), [])
        self.assertEqual(keys.tick(5), [])
        self.assertEqual(keys.tick(10), [("vol+", "press", 0)])
        self.assertEqual(keys.pressed(), {"vol+"})

    def test_debounce_cancel(self):
        keys = self.keys()
        press(keys, VOL_UP, 0)
        self.assertEqual(release(keys, VOL_UP, 5), [])
        self.assertEqual(keys.tick(10), [])
        self.assertEqual(keys.pressed(), set())

    def test_debounce_zero(self):
        keys = self.keys(debounce=0)
        self.assertEqual(press(keys, VOL_UP, 0), [("vol+", "press", 0)])
        self.assertEqual(keys.tick(0), [])

    def test_click(self):
        keys = self.keys()
        press(keys, VOL_UP, 0)
        keys.tick(10)
        self.assertEqual(release(keys, VOL_UP, 30), [("vol+", "release", 0)])
        self.assertEqual(keys.tick(79), [])
        self.assertEqual(keys.tick(80),
                         [("vol+", "click", 1), ("vol+", "single", 1)])

    def test_double(self):
        keys = self.keys()
        press(keys, PLAY, 0)
        keys.tick(10)
        release(keys, PLAY, 30)
        press(keys, PLAY, 50)
        keys.tick(60)
        release(keys, PLAY, 80)
        self.assertEqual(keys.tick(129), [])
        self.assertEqual(keys.tick(130),
                         [("play", "click", 2), ("play", "double", 2)])

    def test_triple(self):
        keys = self.keys()
        press(keys, PLAY, 0)
        keys.tick(10)
        release(keys, PLAY, 30)
        press(keys, PLAY, 50)
        keys.tick(60)
        release(keys, PLAY, 80)
        press(keys, PLAY, 100)
        keys.tick(110)
        release(keys, PLAY, 130)
        self.assertEqual(keys.tick(180),
                         [("play", "click", 3), ("play", "triple", 3)])

    def test_four_clicks(self):
        keys = self.keys()
        now = 0
        for _index in range(4):
            press(keys, PLAY, now)
            keys.tick(now + 10)
            release(keys, PLAY, now + 20)
            now += 40
        events = keys.tick(now + 60)
        self.assertIn(("play", "click", 4), events)
        self.assertNotIn(("play", "triple", 4), events)

    def test_hold_and_step(self):
        keys = self.keys()
        press(keys, VOL_UP, 0)
        keys.tick(10)
        self.assertEqual(keys.tick(109), [])
        self.assertEqual(keys.tick(110), [("vol+", "hold", 0)])
        self.assertEqual(keys.tick(129), [])
        self.assertEqual(keys.tick(130), [("vol+", "step", 1)])
        self.assertEqual(keys.tick(150), [("vol+", "step", 2)])
        self.assertEqual(release(keys, VOL_UP, 160),
                         [("vol+", "release", 0)])
        self.assertEqual(keys.tick(220), [])

    def test_hold_after_click(self):
        keys = self.keys()
        press(keys, VOL_UP, 0)
        keys.tick(10)
        release(keys, VOL_UP, 30)
        press(keys, VOL_UP, 40)
        keys.tick(50)
        self.assertEqual(keys.tick(150), [("vol+", "hold", 1)])
        release(keys, VOL_UP, 160)
        self.assertEqual(keys.tick(220), [])

    def test_hold_zero(self):
        keys = self.keys(hold=0, debounce=0)
        press(keys, MIC, 0)
        self.assertEqual(keys.tick(0), [("mic", "hold", 0)])

    def test_click_zero(self):
        keys = self.keys(click=0)
        press(keys, MIC, 0)
        keys.tick(10)
        release(keys, MIC, 30)
        self.assertEqual(keys.tick(30),
                         [("mic", "click", 1), ("mic", "single", 1)])

    def test_value_two_ignored(self):
        keys = self.keys()
        self.assertEqual(
            keys.feed(hal_keys.EV_KEY, VOL_UP, 2, 0), [])

    def test_syn_ignored(self):
        keys = self.keys()
        self.assertEqual(keys.feed(hal_keys.EV_SYN, 0, 0, 0), [])

    def test_unknown_ignored(self):
        keys = self.keys()
        self.assertEqual(keys.feed(hal_keys.EV_KEY, 999, 1, 0), [])

    def test_reset(self):
        keys = self.keys()
        press(keys, VOL_UP, 0)
        keys.tick(10)
        keys.reset()
        self.assertEqual(keys.pressed(), set())
        self.assertEqual(keys.tick(20), [])


class Combos(unittest.TestCase):
    def keys(self, **kwargs):
        params = dict(debounce=10, hold=100, click=50, step=20,
                      combo=100)
        params.update(kwargs)
        return lib_keys.Keys(**params)

    def test_vol_pair(self):
        keys = self.keys()
        self.assertEqual(press(keys, VOL_DOWN, 0), [])
        self.assertEqual(press(keys, VOL_UP, 10),
                         [("vol-+vol+", "combo", 0)])
        self.assertEqual(keys.tick(10), [])
        self.assertEqual(keys.tick(20), [])
        self.assertEqual(keys.tick(110),
                         [("vol-+vol+", "combo_hold", 0)])
        self.assertEqual(keys.tick(200), [])
        self.assertEqual(release(keys, VOL_DOWN, 210), [])
        self.assertEqual(release(keys, VOL_UP, 211),
                         [("vol-+vol+", "combo_release", 0)])
        self.assertEqual(keys.tick(300), [])

    def test_all_names(self):
        for codes, name in lib_keys.COMBOS:
            keys = self.keys()
            press(keys, codes[0], 0)
            self.assertEqual(press(keys, codes[1], 5),
                             [(name, "combo", 0)])

    def test_window(self):
        keys = self.keys(hold=1000)
        press(keys, VOL_DOWN, 0)
        self.assertEqual(keys.tick(10), [("vol-", "press", 0)])
        self.assertEqual(press(keys, VOL_UP, 200), [])
        self.assertEqual(keys.tick(210), [("vol+", "press", 0)])
        self.assertEqual(keys.tick(300), [])

    def test_window_zero(self):
        keys = self.keys(combo=0)
        press(keys, VOL_DOWN, 0)
        self.assertEqual(press(keys, VOL_UP, 0),
                         [("vol-+vol+", "combo", 0)])

    def test_extra_key(self):
        keys = self.keys()
        press(keys, VOL_DOWN, 0)
        press(keys, VOL_UP, 10)
        self.assertEqual(press(keys, PLAY, 20), [])
        self.assertEqual(keys.tick(30), [("play", "press", 0)])

    def test_no_click_after_combo(self):
        keys = self.keys()
        press(keys, PLAY, 0)
        press(keys, VOL_UP, 10)
        keys.tick(20)
        release(keys, PLAY, 30)
        release(keys, VOL_UP, 31)
        self.assertEqual(keys.tick(500), [])

    def test_partial_release(self):
        keys = self.keys()
        press(keys, PLAY, 0)
        press(keys, VOL_UP, 10)
        keys.tick(20)
        self.assertEqual(release(keys, PLAY, 30), [])
        self.assertEqual(keys.tick(500), [])
        self.assertEqual(release(keys, VOL_UP, 510),
                         [("play+vol+", "combo_release", 0)])

    def test_hold_once(self):
        keys = self.keys()
        press(keys, PLAY, 0)
        press(keys, VOL_UP, 10)
        self.assertEqual(keys.tick(110),
                         [("play+vol+", "combo_hold", 0)])
        self.assertEqual(keys.tick(120), [])
        self.assertEqual(keys.tick(300), [])

    def test_reset(self):
        keys = self.keys()
        press(keys, VOL_DOWN, 0)
        press(keys, VOL_UP, 10)
        keys.reset()
        self.assertEqual(keys.pressed(), set())
        self.assertEqual(press(keys, VOL_DOWN, 20), [])
        self.assertEqual(keys.tick(30), [("vol-", "press", 0)])


class FakeDevice:
    def __init__(self, events):
        self.events = list(events)
        self.closed = False

    def poll(self, timeout_ms=0):
        if not self.events:
            return []
        return [self.events.pop(0)]

    def close(self):
        self.closed = True


class DevicePoll(unittest.TestCase):
    def test_poll(self):
        fake = FakeDevice([
            (0, 0, hal_keys.EV_KEY, VOL_UP, 1),
            (0, 0, hal_keys.EV_SYN, 0, 0),
            (0, 0, hal_keys.EV_KEY, VOL_UP, 0),
        ])
        keys = lib_keys.Keys(device=fake, debounce=0, hold=100,
                             click=50, step=20, now=lambda: 0)
        self.assertEqual(
            keys.poll(0),
            [("vol+", "press", 0), ("vol+", "release", 0)])
        self.assertEqual(keys.poll(0), [])

    def test_no_device(self):
        keys = lib_keys.Keys()
        with self.assertRaises(HalError):
            keys.poll(0)

    def test_wait_keeps_events(self):
        now = [0]
        keys = lib_keys.Keys(device=FakeDevice([]), debounce=0, hold=100,
                             click=50, step=20, now=lambda: now[0])
        press(keys, VOL_UP, 10)
        release(keys, VOL_UP, 10)
        now[0] = 60
        self.assertEqual(keys.wait(0), ("vol+", "click", 1))
        self.assertEqual(keys.wait(0), ("vol+", "single", 1))
        self.assertIsNone(keys.wait(0))

    def test_wait_none(self):
        keys = lib_keys.Keys(device=FakeDevice([]), now=lambda: 0)
        self.assertIsNone(keys.wait(0))

    def test_close(self):
        fake = FakeDevice([])
        keys = lib_keys.Keys(device=fake)
        keys.close()
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
