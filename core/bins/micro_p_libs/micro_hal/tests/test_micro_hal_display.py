#!/usr/bin/env python3
"""Тесты дисплея: C-транспорт и раскладка без платы."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import hal_common, hal_display, lib_display  # noqa: E402
from micro_hal.hal_common import HalError  # noqa: E402


class Helpers(unittest.TestCase):
    def test_parse_channels(self):
        names = ["clock-led10", "foo", "clock-led2", "clock-led1"]
        self.assertEqual(hal_display.parse_channels(names),
                         ["clock-led1", "clock-led2", "clock-led10"])

    def test_channel_name(self):
        self.assertEqual(hal_display.channel_name(0), "clock-led1")
        self.assertEqual(hal_display.channel_name(29), "clock-led30")

    def test_clamp(self):
        self.assertEqual(hal_display.clamp(-1), 0)
        self.assertEqual(hal_display.clamp(0), 0)
        self.assertEqual(hal_display.clamp(255), 255)
        self.assertEqual(hal_display.clamp(999), 255)

    def test_scale_values(self):
        self.assertEqual(hal_display.scale_values([100, 200, 0], 50),
                         [50, 100, 0])
        self.assertEqual(hal_display.scale_values([255], 0), [0])
        self.assertEqual(hal_display.scale_values([255], 100), [255])


class SysfsRead(unittest.TestCase):
    def setUp(self):
        hal_display.forget()
        hal_display._channels = [
            hal_display.channel_name(i) for i in range(hal_display.COUNT)]
        self.ready = mock.patch.object(hal_display, "_ready", lambda: None)
        self.ready.start()
        self.addCleanup(self.ready.stop)
        self.addCleanup(hal_display.forget)

    def test_path(self):
        self.assertEqual(
            hal_display.path(0),
            "/sys/class/leds/clock-led1/brightness")

    def test_path_index(self):
        with self.assertRaises(HalError):
            hal_display.path(30)

    def test_get(self):
        with mock.patch.object(hal_common, "read_text", return_value="7\n"):
            self.assertEqual(hal_display.get(0), 7)

    def test_get_empty(self):
        with mock.patch.object(hal_common, "read_text", return_value=""):
            self.assertEqual(hal_display.get(0), 0)

    def test_get_bad_index(self):
        with self.assertRaises(HalError):
            hal_display.get(30)


class FakeFfi:
    def __init__(self):
        self.buffer = bytearray(hal_display.COUNT)
        self.frames = []
        self.closed = False
        self.writes = 0
        self.open_path = None
        self.device_path = None
        self.open_result = 7
        self.count_result = 30
        self.write_result = 0
        self.errno_value = 0
        self.open_error = None
        self.buffer_error = None
        self.buffer_size = None
        self.frame_pointer = 1

    def open(self, path):
        self.open_path = path
        if self.open_error is not None:
            raise self.open_error
        return FakeLib(self)

    def as_bytearray(self, pointer, size):
        self.buffer_size = size
        if self.buffer_error is not None:
            raise self.buffer_error
        return self.buffer


class FakeLib:
    def __init__(self, owner):
        self.owner = owner

    def func(self, result, name, arguments):
        return {
            "display_open": self.open_device,
            "display_count": lambda fd: self.owner.count_result,
            "display_frame": lambda: self.owner.frame_pointer,
            "display_write_frame": self.write,
            "display_close": self.close,
            "display_errno": lambda: self.owner.errno_value,
        }[name]

    def open_device(self, path):
        self.owner.device_path = path
        return self.owner.open_result

    def write(self, fd):
        self.owner.writes += 1
        self.owner.frames.append(bytes(self.owner.buffer[:hal_display.COUNT]))
        return self.owner.write_result

    def close(self, fd):
        self.owner.closed = True
        return 0


class CBackend(unittest.TestCase):
    def setUp(self):
        self.fake = FakeFfi()
        self.patches = [
            mock.patch.dict(sys.modules, {"ffi": self.fake}),
            mock.patch.object(hal_common, "require_root", lambda: None),
            mock.patch.object(hal_common, "require_va_stopped",
                              lambda what: None),
            mock.patch.object(
                hal_display, "channels",
                lambda: [hal_display.channel_name(i)
                         for i in range(hal_display.COUNT)]),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        hal_display.forget()
        self.addCleanup(hal_display.forget)

    def test_ready(self):
        hal_display._ready()
        self.assertEqual(self.fake.open_path, hal_display.LIB)
        self.assertEqual(self.fake.device_path, hal_display.DEVICE)
        self.assertEqual(self.fake.buffer_size, hal_display.COUNT)
        self.assertIsNotNone(hal_display._c)

    def test_raw(self):
        values = [10 * (index % 20) for index in range(hal_display.COUNT)]
        hal_display.raw(values)
        self.assertEqual(self.fake.frames[-1], bytes(values))
        self.assertEqual(hal_display._values, values)

    def test_raw_clamps(self):
        values = [-1] * hal_display.COUNT
        values[0] = 999
        hal_display.raw(values)
        frame = self.fake.frames[-1]
        self.assertEqual(frame[0], 255)
        self.assertEqual(frame[1], 0)

    def test_raw_length(self):
        hal_display._ready()
        with self.assertRaises(HalError):
            hal_display.raw([0] * 29)
        self.assertEqual(self.fake.writes, 0)

    def test_set_without_cache(self):
        with mock.patch.object(hal_display, "get", return_value=0):
            hal_display.set(3, 100)
        frame = self.fake.frames[-1]
        self.assertEqual(frame[3], 100)
        self.assertEqual(sum(frame), 100)
        self.assertEqual(hal_display._values[3], 100)

    def test_set_with_cache(self):
        hal_display._values = [10] * hal_display.COUNT
        hal_display.set(0, 200)
        frame = self.fake.frames[-1]
        self.assertEqual(frame[0], 200)
        self.assertEqual(frame[1], 10)

    def test_clear(self):
        hal_display.clear()
        self.assertEqual(self.fake.frames[-1], bytes(hal_display.COUNT))
        self.assertEqual(hal_display._values, [0] * hal_display.COUNT)

    def test_scale(self):
        hal_display._values = [100] * hal_display.COUNT
        hal_display.scale(50)
        self.assertEqual(self.fake.frames[-1],
                         bytes([50] * hal_display.COUNT))

    def test_forget(self):
        hal_display._ready()
        self.assertFalse(self.fake.closed)
        hal_display.forget()
        self.assertTrue(self.fake.closed)
        self.assertIsNone(hal_display._c)
        self.assertIsNone(hal_display._values)
        self.assertFalse(hal_display._ready_done)

    def test_bad_count(self):
        self.fake.count_result = 29
        with self.assertRaises(HalError):
            hal_display._ready()
        self.assertTrue(self.fake.closed)

    def test_open_error(self):
        self.fake.open_result = -1
        self.fake.errno_value = 13
        with self.assertRaises(HalError):
            hal_display._ready()

    def test_ffi_open_error(self):
        self.fake.open_error = OSError("нет библиотеки")
        with self.assertRaises(HalError):
            hal_display._ready()

    def test_buffer_error(self):
        self.fake.buffer_error = OSError("нет буфера")
        with self.assertRaises(HalError):
            hal_display._ready()
        self.assertTrue(self.fake.closed)

    def test_write_error(self):
        self.fake.write_result = -1
        self.fake.errno_value = 5
        with self.assertRaises(HalError):
            hal_display.raw([0] * hal_display.COUNT)
        self.assertEqual(self.fake.writes, 1)


class Brightness(unittest.TestCase):
    def setUp(self):
        lib_display.brightness(100, gamma=False)

    def tearDown(self):
        lib_display.brightness(100, gamma=False)

    def test_defaults(self):
        self.assertEqual(lib_display.get_brightness(), 100)
        self.assertFalse(lib_display.get_gamma())
        self.assertEqual(lib_display.level(), lib_display.STOCK_MAX)

    def test_linear(self):
        self.assertEqual(lib_display.level(0), 0)
        self.assertEqual(lib_display.level(25), 38)
        self.assertEqual(lib_display.level(50), 76)
        self.assertEqual(lib_display.level(100), 153)

    def test_gamma(self):
        self.assertEqual(lib_display.level(0, gamma=True), 0)
        self.assertEqual(lib_display.level(25, gamma=True), 7)
        self.assertEqual(lib_display.level(50, gamma=True), 26)
        self.assertEqual(lib_display.level(75, gamma=True), 70)
        self.assertEqual(lib_display.level(100, gamma=True), 153)

    def test_state(self):
        self.assertEqual(lib_display.brightness(50), 76)
        self.assertEqual(lib_display.get_brightness(), 50)
        self.assertEqual(lib_display.level(), 76)

    def test_gamma_state(self):
        lib_display.brightness(50, gamma=True)
        self.assertTrue(lib_display.get_gamma())
        self.assertEqual(lib_display.level(), 26)

    def test_clamp(self):
        self.assertEqual(lib_display.brightness(-5), 0)
        self.assertEqual(lib_display.get_brightness(), 0)
        self.assertEqual(lib_display.brightness(150), 153)
        self.assertEqual(lib_display.get_brightness(), 100)

    def test_text_uses_brightness(self):
        lib_display.brightness(50)
        with mock.patch.object(lib_display.hal_display, "raw") as raw:
            values = lib_display.text("8   ", colon=False)
        raw.assert_called_once_with(values)
        self.assertEqual(max(values), 76)
        self.assertEqual(min(values), 0)

    def test_value_override(self):
        lib_display.brightness(10)
        with mock.patch.object(lib_display.hal_display, "raw"):
            values = lib_display.text("8   ", value=100, colon=False)
        self.assertEqual(max(values), 100)


class Layout(unittest.TestCase):
    def test_stock_map_is_permutation(self):
        self.assertEqual(sorted(lib_display.STOCK_MAP),
                         list(range(hal_display.COUNT)))

    def test_layout_covers_all_channels(self):
        used = list(lib_display.COLON)
        for name in lib_display.DIGITS:
            used.extend(lib_display.LAYOUT[name].values())
        self.assertEqual(sorted(used), list(range(hal_display.COUNT)))

    def test_font(self):
        self.assertEqual(lib_display.FONT,
                         (0x3f, 0x06, 0x5b, 0x4f, 0x66,
                          0x6d, 0x7d, 0x07, 0x7f, 0x6f))

    def test_vk_digit_one(self):
        self.assertEqual(lib_display.FONT[1], 0x06)


class Frames(unittest.TestCase):
    def test_one(self):
        values = lib_display.frame("1234", value=100, colon=False)
        self.assertEqual(len(values), hal_display.COUNT)
        digit0 = lib_display.LAYOUT["digit0"]
        self.assertEqual(values[digit0["b"]], 100)
        self.assertEqual(values[digit0["c"]], 100)
        self.assertEqual(values[digit0["a"]], 0)
        self.assertEqual(values[lib_display.COLON[0]], 0)

    def test_colon(self):
        values = lib_display.frame("0000", value=80, colon=True)
        self.assertEqual(values[lib_display.COLON[0]], 80)
        self.assertEqual(values[lib_display.COLON[1]], 80)

    def test_colon_pair(self):
        values = lib_display.frame("0000", value=80, colon=(True, False))
        self.assertEqual(values[lib_display.COLON_TOP], 80)
        self.assertEqual(values[lib_display.COLON_BOTTOM], 0)

    def test_colon_channels(self):
        self.assertEqual(lib_display.COLON_TOP, 16)
        self.assertEqual(lib_display.COLON_BOTTOM, 15)
        self.assertEqual(lib_display.COLON, (16, 15))

    def test_blank(self):
        values = lib_display.frame("1 34", value=100, colon=False)
        digit1 = lib_display.LAYOUT["digit1"]
        for channel in digit1.values():
            self.assertEqual(values[channel], 0)

    def test_bad_length(self):
        with self.assertRaises(HalError):
            lib_display.frame("123")

    def test_bad_char(self):
        with self.assertRaises(HalError):
            lib_display.frame("12x4")

    def test_text_writes(self):
        with mock.patch.object(lib_display.hal_display, "raw") as raw:
            values = lib_display.text("12:34", value=100)
        raw.assert_called_once_with(values)
        self.assertEqual(len(values), hal_display.COUNT)


class Clock(unittest.TestCase):
    def test_clock(self):
        now = (2026, 11, 2, 9, 5, 0, 0, 0)
        with mock.patch.object(lib_display.time, "localtime",
                               return_value=now), \
             mock.patch.object(lib_display.hal_display, "raw") as raw:
            values = lib_display.clock(value=100)
        expected = lib_display.frame("0905", value=100, colon=True)
        self.assertEqual(values, expected)
        raw.assert_called_once_with(expected)

    def test_invalid_time(self):
        now = (1999, 1, 1, -1, 0, 0, 0, 0)
        with mock.patch.object(lib_display.time, "localtime",
                               return_value=now), \
             mock.patch.object(lib_display.hal_display, "raw") as raw:
            values = lib_display.clock()
        self.assertEqual(values, [0] * hal_display.COUNT)
        raw.assert_called_once_with([0] * hal_display.COUNT)

    def test_clock_blink(self):
        now = (2026, 11, 2, 9, 5, 0, 0, 0)
        with mock.patch.object(lib_display.time, "localtime",
                               return_value=now), \
             mock.patch.object(lib_display.hal_display, "raw") as raw, \
             mock.patch.object(lib_display.time, "sleep") as sleep:
            values = lib_display.clock(value=100, blink=True, off_ms=250)
        self.assertEqual(raw.call_count, 2)
        off = raw.call_args_list[0].args[0]
        on = raw.call_args_list[1].args[0]
        self.assertEqual(off[lib_display.COLON_TOP], 0)
        self.assertEqual(off[lib_display.COLON_BOTTOM], 0)
        self.assertEqual(on[lib_display.COLON_TOP], 100)
        self.assertEqual(on[lib_display.COLON_BOTTOM], 100)
        self.assertEqual(values, on)
        self.assertEqual(sleep.call_args_list,
                         [mock.call(0.25), mock.call(0.75)])


class Pulse(unittest.TestCase):
    def test_pulse(self):
        with mock.patch.object(lib_display.hal_display, "raw") as raw, \
             mock.patch.object(lib_display.time, "sleep") as sleep:
            values = lib_display.pulse(
                "1234", seconds=1.0, steps=4, value=100, colon=True)
        self.assertEqual(raw.call_count, 5)
        first = raw.call_args_list[0].args[0]
        self.assertEqual(first,
                         lib_display.frame("1234", value=100, colon=True))
        self.assertEqual(raw.call_args_list[-1].args[0],
                         [0] * hal_display.COUNT)
        self.assertEqual(
            raw.call_args_list[1].args[0][lib_display.LAYOUT["digit0"]["b"]],
            75)
        self.assertEqual(sleep.call_args_list, [mock.call(0.25)] * 4)
        self.assertEqual(values, [0] * hal_display.COUNT)

    def test_colon_false(self):
        with mock.patch.object(lib_display.hal_display, "raw") as raw, \
             mock.patch.object(lib_display.time, "sleep"):
            lib_display.pulse("1234", steps=1, value=100, colon=False)
        first = raw.call_args_list[0].args[0]
        self.assertEqual(first[lib_display.COLON_TOP], 0)
        self.assertEqual(first[lib_display.COLON_BOTTOM], 0)

    def test_bad_steps(self):
        with self.assertRaises(HalError):
            lib_display.pulse("1234", steps=0)

    def test_bad_seconds(self):
        with self.assertRaises(HalError):
            lib_display.pulse("1234", seconds=-1)


class Transition(unittest.TestCase):
    def test_changed_digit(self):
        with mock.patch.object(lib_display.hal_display, "raw") as raw, \
             mock.patch.object(lib_display.time, "sleep") as sleep:
            values = lib_display.transition(
                "1234", "1235", fade_out=1.0, fade_in=1.0,
                steps=4, value=100, colon=True)
        self.assertEqual(raw.call_count, 8)
        first = raw.call_args_list[0].args[0]
        last = raw.call_args_list[-1].args[0]
        self.assertEqual(last,
                         lib_display.frame("1235", value=100, colon=True))
        digit3 = lib_display.LAYOUT["digit3"]
        self.assertEqual(first[digit3["b"]], 75)
        self.assertEqual(first[digit3["a"]], 0)
        self.assertEqual(first[digit3["c"]], 100)
        self.assertEqual(first[lib_display.LAYOUT["digit0"]["b"]], 100)
        self.assertEqual(sleep.call_args_list, [mock.call(0.25)] * 8)
        self.assertEqual(values, last)

    def test_colon_none(self):
        with mock.patch.object(lib_display.hal_display, "get",
                               side_effect=[50, 60]) as get, \
             mock.patch.object(lib_display.hal_display, "raw") as raw, \
             mock.patch.object(lib_display.time, "sleep"):
            values = lib_display.transition(
                "1234", "1235", steps=2, value=100, colon=None)
        self.assertEqual(get.call_count, 2)
        for call in raw.call_args_list:
            frame = call.args[0]
            self.assertEqual(frame[lib_display.COLON_TOP], 50)
            self.assertEqual(frame[lib_display.COLON_BOTTOM], 60)
        self.assertEqual(values[lib_display.COLON_TOP], 50)
        self.assertEqual(values[lib_display.COLON_BOTTOM], 60)

    def test_same_digits(self):
        with mock.patch.object(lib_display.hal_display, "raw") as raw, \
             mock.patch.object(lib_display.time, "sleep") as sleep:
            values = lib_display.transition(
                "1234", "1234", steps=4, value=100, colon=True)
        self.assertEqual(raw.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(values,
                         lib_display.frame("1234", value=100, colon=True))

    def test_colon_pair(self):
        with mock.patch.object(lib_display.hal_display, "raw") as raw, \
             mock.patch.object(lib_display.time, "sleep"):
            lib_display.transition(
                "1234", "1235", steps=1, value=100, colon=(True, False))
        for call in raw.call_args_list:
            frame = call.args[0]
            self.assertEqual(frame[lib_display.COLON_TOP], 100)
            self.assertEqual(frame[lib_display.COLON_BOTTOM], 0)

    def test_bad_steps(self):
        with self.assertRaises(HalError):
            lib_display.transition("1234", "1235", steps=0)

    def test_bad_fade(self):
        with self.assertRaises(HalError):
            lib_display.transition("1234", "1235", fade_out=-1)


class ColonFade(unittest.TestCase):
    def test_fade(self):
        with mock.patch.object(lib_display.hal_display, "set") as set_value, \
             mock.patch.object(lib_display.time, "sleep") as sleep:
            result = lib_display.colon_fade(
                seconds=1.0, steps=4, value=100)
        expected = []
        for level in (100, 75, 50, 25, 0):
            expected.append(mock.call(lib_display.COLON_TOP, level))
            expected.append(mock.call(lib_display.COLON_BOTTOM, level))
        self.assertEqual(set_value.call_args_list, expected)
        self.assertEqual(sleep.call_args_list, [mock.call(0.25)] * 4)
        self.assertEqual(result, 0)

    def test_stop(self):
        calls = [0]

        def stop():
            calls[0] += 1
            return calls[0] > 2

        with mock.patch.object(lib_display.hal_display, "set") as set_value, \
             mock.patch.object(lib_display.time, "sleep"):
            result = lib_display.colon_fade(
                seconds=1.0, steps=4, value=100, stop=stop)
        self.assertEqual(set_value.call_count, 4)
        self.assertEqual(result, 75)

    def test_top_bottom(self):
        with mock.patch.object(lib_display.hal_display, "set") as set_value, \
             mock.patch.object(lib_display.time, "sleep"):
            lib_display.colon_fade(
                seconds=1.0, steps=1, value=100,
                top=False, bottom=True)
        self.assertEqual(set_value.call_args_list[0],
                         mock.call(lib_display.COLON_TOP, 0))
        self.assertEqual(set_value.call_args_list[1],
                         mock.call(lib_display.COLON_BOTTOM, 100))

    def test_bad_steps(self):
        with self.assertRaises(HalError):
            lib_display.colon_fade(steps=0)

    def test_bad_seconds(self):
        with self.assertRaises(HalError):
            lib_display.colon_fade(seconds=-1)


class Logical(unittest.TestCase):
    def test_map(self):
        values = list(range(hal_display.COUNT))
        physical = lib_display.map_logical(values)
        for logical, channel in enumerate(lib_display.STOCK_MAP):
            self.assertEqual(physical[channel], logical)

    def test_bad_length(self):
        with self.assertRaises(HalError):
            lib_display.map_logical([0])

    def test_raw_logical(self):
        values = [10] * hal_display.COUNT
        with mock.patch.object(lib_display.hal_display, "raw") as raw:
            lib_display.raw_logical(values)
        raw.assert_called_once_with(lib_display.map_logical(values))


class ColonAndDemo(unittest.TestCase):
    def test_colon(self):
        with mock.patch.object(lib_display.hal_display, "set") as set_value:
            lib_display.colon(top=True, bottom=False, value=50)
        self.assertEqual(set_value.call_args_list,
                         [mock.call(lib_display.COLON_TOP, 50),
                          mock.call(lib_display.COLON_BOTTOM, 0)])

    def test_demo_stock(self):
        path = TMP / "micro_hal_demo.json"
        path.write_text('[{"duration": 0.01, "brightness": [255]}]',
                        encoding="utf-8")
        try:
            with mock.patch.object(lib_display, "raw_logical") as raw, \
                 mock.patch.object(lib_display.time, "sleep"):
                count = lib_display.demo_stock(str(path))
        finally:
            path.unlink()
        self.assertEqual(count, 1)
        raw.assert_called_once_with([153])

    def test_demo_stock_raw(self):
        path = TMP / "micro_hal_demo_raw.json"
        path.write_text('[{"duration": 0.01, "brightness": [255]}]',
                        encoding="utf-8")
        try:
            with mock.patch.object(lib_display, "raw_logical") as raw, \
                 mock.patch.object(lib_display.time, "sleep"):
                lib_display.demo_stock(str(path), scale=False)
        finally:
            path.unlink()
        raw.assert_called_once_with([255])

    def test_demo_bad_speed(self):
        with self.assertRaises(HalError):
            lib_display.demo_stock("x", speed=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
