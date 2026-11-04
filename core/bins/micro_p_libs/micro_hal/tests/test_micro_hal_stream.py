#!/usr/bin/env python3
"""Тесты micro_hal: поток микрофонов без платы и без Pulse."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, hal_mic, lib_mic  # noqa: E402


class FakeLibrary:
    """Подмена `hal_mic._Library`."""

    def __init__(self, channels=4, window=320, frames=320):
        self.channels_value = channels
        self.window_value = window
        self.frames_value = frames
        self.error_text = ""
        self.open_result = 0
        self.read_result = window
        self.mono_result = window
        self.calls = []
        self.reads = 0
        self.monos = 0
        self.closes = 0
        self.level = 100

    def open(self, source, rate, channels, window_ms, settle_ms):
        self.calls.append((source, rate, channels, window_ms, settle_ms))
        return self.open_result

    def read(self):
        self.reads += 1
        return self.read_result

    def mono(self):
        self.monos += 1
        return self.mono_result

    def view(self, size):
        return bytearray(size)

    def mono_view(self, size):
        return bytearray(size)

    def rms(self, channel):
        return self.level + channel

    def peak(self, channel):
        return self.level * 10 + channel

    def window(self):
        return self.window_value

    def window_bytes(self):
        return self.window_value * self.channels_value * 2

    def channels(self):
        return self.channels_value

    def rate(self):
        return 16000

    def frames(self):
        return self.frames_value

    def latency(self):
        return 1234

    def close(self):
        self.closes += 1
        return 0

    def error(self):
        return self.error_text


class StreamOpen(unittest.TestCase):
    def setUp(self):
        self.lib = FakeLibrary()
        patch = mock.patch.object(hal_mic.hal_common, "require_va_stopped")
        patch.start()
        self.addCleanup(patch.stop)
        self.stream = hal_mic.Stream(channels=4, settle_ms=250, lib=self.lib)

    def test_defaults(self):
        self.assertEqual(self.stream.window_ms, 20)
        self.assertEqual(self.stream.settle_ms, 250)
        self.assertFalse(self.stream.running())

    def test_open_arguments(self):
        self.stream.open()
        self.assertEqual(self.lib.calls,
                         [("mics", 16000, 4, 20, 250)])
        self.assertTrue(self.stream.running())

    def test_open_twice(self):
        self.stream.open()
        with self.assertRaises(HalError):
            self.stream.open()

    def test_open_error(self):
        self.lib.open_result = -1
        self.lib.error_text = "No such entity"
        with self.assertRaises(HalError) as context:
            self.stream.open()
        self.assertIn("No such entity", str(context.exception))
        self.assertFalse(self.stream.running())

    def test_open_error_without_text(self):
        self.lib.open_result = -1
        with self.assertRaises(HalError):
            self.stream.open()

    def test_close(self):
        self.stream.open()
        self.assertTrue(self.stream.close())
        self.assertEqual(self.lib.closes, 1)
        self.assertFalse(self.stream.close())
        self.assertEqual(self.lib.closes, 1)

    def test_context(self):
        with hal_mic.Stream(channels=1, lib=self.lib) as stream:
            self.assertTrue(stream.running())
        self.assertFalse(self.stream.running())


class StreamRead(unittest.TestCase):
    def setUp(self):
        self.lib = FakeLibrary(channels=4, window=320)
        patch = mock.patch.object(hal_mic.hal_common, "require_va_stopped")
        patch.start()
        self.addCleanup(patch.stop)
        self.stream = hal_mic.Stream(lib=self.lib)
        self.stream.open()

    def test_read_size(self):
        data = self.stream.read()
        self.assertEqual(len(data), 320 * 4 * 2)
        self.assertEqual(self.lib.reads, 1)

    def test_read_error(self):
        self.lib.read_result = -1
        self.lib.error_text = "ошибка"
        with self.assertRaises(HalError):
            self.stream.read()

    def test_mono_size(self):
        data = self.stream.mono()
        self.assertEqual(len(data), 320 * 2)
        self.assertEqual(self.lib.monos, 1)

    def test_mono_error(self):
        self.lib.mono_result = -1
        with self.assertRaises(HalError):
            self.stream.mono()

    def test_stats(self):
        stats = self.stream.stats()
        self.assertEqual(stats["frames"], 320)
        self.assertEqual(stats["rms"], [100, 101, 102, 103])
        self.assertEqual(stats["peak"], [1000, 1001, 1002, 1003])

    def test_window(self):
        self.assertEqual(self.stream.window(), 320)
        self.assertEqual(self.stream.window_bytes(), 2560)
        self.assertEqual(self.stream.latency(), 1234)

    def test_not_open(self):
        fresh = hal_mic.Stream(lib=self.lib)
        with self.assertRaises(HalError):
            fresh.read()
        with self.assertRaises(HalError):
            fresh.mono()
        with self.assertRaises(HalError):
            fresh.stats()
        with self.assertRaises(HalError):
            fresh.latency()
        self.assertEqual(fresh.frames(), 0)


class FakeStream:
    """Подмена `hal_mic.Stream`."""

    def __init__(self, channels=1, window=320):
        self.channels = channels
        self.rate = 16000
        self._window = window
        self.opened = False
        self.level = 1000

    def open(self):
        self.opened = True
        return self

    def close(self):
        self.opened = False
        return True

    def window(self):
        return self._window

    def read(self):
        return b"\x01\x00" * self._window * self.channels

    def mono(self):
        return b"\x01\x00" * self._window

    def stats(self):
        return {"frames": self._window,
                "rms": [self.level] * self.channels,
                "peak": [self.level] * self.channels}


class MicStreamTest(unittest.TestCase):
    def make(self, **kwargs):
        stream = FakeStream(**kwargs)
        return lib_mic.MicStream(stream=stream, ring_seconds=2.0)

    def test_open(self):
        mic = self.make()
        mic.open()
        self.assertTrue(mic.running())
        self.assertEqual(mic.ring_frames, 32000)
        self.assertEqual(mic._ring_chunks, 100)

    def test_open_twice(self):
        mic = self.make()
        mic.open()
        with self.assertRaises(HalError):
            mic.open()

    def test_read_and_ring(self):
        mic = self.make()
        mic.open()
        data = mic.read()
        self.assertEqual(len(data), 640)
        self.assertEqual(mic.frames(), 320)
        self.assertEqual(len(mic._ring), 1)

    def test_ring_overflow(self):
        mic = self.make()
        mic.open()
        for _ in range(150):
            mic.read()
        self.assertEqual(len(mic._ring), 100)
        self.assertEqual(mic.frames(), 150 * 320)

    def test_snapshot_all(self):
        mic = self.make()
        mic.open()
        for _ in range(10):
            mic.read()
        data, first = mic.snapshot()
        self.assertEqual(len(data), 10 * 640)
        self.assertEqual(first, 0)

    def test_snapshot_seconds(self):
        mic = self.make()
        mic.open()
        for _ in range(10):
            mic.read()
        data, first = mic.snapshot(0.1)
        self.assertEqual(len(data), 0.1 * 16000 * 2)
        self.assertEqual(first, 10 * 320 - 1600)

    def test_snapshot_empty(self):
        mic = self.make()
        mic.open()
        self.assertEqual(mic.snapshot(), (b"", 0))

    def test_level(self):
        mic = self.make()
        mic.open()
        mic.read()
        self.assertAlmostEqual(mic.level(), lib_mic.dbfs(1000), places=6)
        self.assertEqual(len(mic.levels()), 1)

    def test_level_without_read(self):
        mic = self.make()
        mic.open()
        with self.assertRaises(HalError):
            mic.level()

    def test_raw(self):
        mic = self.make(channels=4, window=320)
        mic.open()
        mic.read()
        self.assertEqual(len(mic.read_raw()), 320 * 4 * 2)

    def test_raw_without_read(self):
        mic = self.make(channels=4, window=320)
        mic.open()
        with self.assertRaises(HalError):
            mic.read_raw()

    def test_close(self):
        mic = self.make()
        mic.open()
        mic.read()
        self.assertTrue(mic.close())
        self.assertFalse(mic.close())
        self.assertEqual(mic._ring, [])

    def test_context(self):
        mic = self.make()
        with mic:
            self.assertTrue(mic.running())
        self.assertFalse(mic.running())

    def test_chunks(self):
        mic = self.make()
        mic.open()
        chunks = []
        for index, chunk in enumerate(mic.chunks()):
            chunks.append(chunk)
            if index == 2:
                break
        self.assertEqual(len(chunks), 3)

    def test_bad_ring(self):
        with self.assertRaises(HalError):
            lib_mic.MicStream(stream=FakeStream(), ring_seconds=-1)


class Dbfs(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(lib_mic.dbfs(0), lib_mic.SILENCE_DBFS)

    def test_full_scale(self):
        self.assertAlmostEqual(lib_mic.dbfs(32768), 0.0, places=6)

    def test_half(self):
        self.assertAlmostEqual(lib_mic.dbfs(16384), -6.02, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
