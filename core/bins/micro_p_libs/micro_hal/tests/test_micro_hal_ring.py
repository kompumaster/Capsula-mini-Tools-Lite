#!/usr/bin/env python3
"""Тесты кольца: кадры и Ring с подставным ffi."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import hal_common, hal_ring  # noqa: E402
from micro_hal.hal_common import HalError  # noqa: E402

LOCKS = REPO / "_tmp" / "ring_locks"


def clean_locks():
    """Пустой каталог замков внутри проекта (не /tmp)."""
    LOCKS.mkdir(parents=True, exist_ok=True)
    for path in LOCKS.iterdir():
        if path.is_dir():
            for item in path.iterdir():
                item.unlink()
            path.rmdir()
        else:
            path.unlink()


class Colors(unittest.TestCase):
    def test_tuple(self):
        self.assertEqual(hal_ring.parse_color((1, 2, 3)), (1, 2, 3))

    def test_int(self):
        self.assertEqual(hal_ring.parse_color(0x102030), (16, 32, 48))

    def test_clamp(self):
        self.assertEqual(hal_ring.parse_color((-1, 300, 10)), (0, 255, 10))

    def test_bad(self):
        with self.assertRaises(HalError):
            hal_ring.parse_color((1, 2))
        with self.assertRaises(HalError):
            hal_ring.parse_color(0x1000000)

    def test_scale(self):
        self.assertEqual(hal_ring.scale_color((200, 100, 50), 255),
                         (200, 100, 50))
        self.assertEqual(hal_ring.scale_color((200, 100, 50), 0), (0, 0, 0))
        self.assertEqual(hal_ring.scale_color((200, 100, 50), 128),
                         (100, 50, 25))


class Frames(unittest.TestCase):
    def test_permutation(self):
        self.assertEqual(sorted(hal_ring.STOCK_MAP),
                         list(range(hal_ring.CHANNELS)))

    def test_empty(self):
        frame = hal_ring.build_frame([(0, 0, 0)] * hal_ring.PIXELS)
        self.assertEqual(frame, [0] * hal_ring.CHANNELS)

    def test_pixel0_red(self):
        colors = [(0, 0, 0)] * hal_ring.PIXELS
        colors[0] = (200, 0, 0)
        frame = hal_ring.build_frame(colors, brightness=255)
        self.assertEqual(frame[1], 200)
        self.assertEqual(sum(frame), 200)

    def test_pixel1_green(self):
        colors = [(0, 0, 0)] * hal_ring.PIXELS
        colors[1] = (0, 200, 0)
        frame = hal_ring.build_frame(colors, brightness=255)
        self.assertEqual(frame[33], 200)
        self.assertEqual(sum(frame), 200)

    def test_brightness(self):
        colors = [(200, 100, 50)] * hal_ring.PIXELS
        frame = hal_ring.build_frame(colors, brightness=128)
        self.assertEqual(frame[1], 100)
        self.assertEqual(frame[0], 50)

    def test_count(self):
        with self.assertRaises(HalError):
            hal_ring.build_frame([(0, 0, 0)])


class FakeFfi:
    def __init__(self):
        self.buffer = bytearray(hal_ring.CHANNELS)
        self.frames = []
        self.closed = False
        self.writes = 0

    def open(self, path):
        return FakeLib(self)

    def as_bytearray(self, pointer, size):
        self.assert_size = size
        return self.buffer


class FakeLib:
    def __init__(self, owner):
        self.owner = owner

    def func(self, result, name, arguments):
        return {
            "ring_open": lambda path: 7,
            "ring_count": lambda fd: hal_ring.CHANNELS,
            "ring_frame": lambda: 1,
            "ring_write_frame": self.write,
            "ring_close": self.close,
            "ring_errno": lambda: 0,
        }[name]

    def write(self, fd, count):
        self.owner.writes += 1
        self.owner.frames.append(bytes(self.owner.buffer[:count]))
        return 0

    def close(self, fd):
        self.owner.closed = True
        return 0


class RingTest(unittest.TestCase):
    def setUp(self):
        clean_locks()
        hal_common._LOCKS.clear()
        self.addCleanup(hal_common._LOCKS.clear)
        self.fake = FakeFfi()
        self.patches = [
            mock.patch.dict(sys.modules, {"ffi": self.fake}),
            mock.patch.object(hal_common, "require_root", lambda: None),
            mock.patch.object(hal_common, "require_va_stopped", lambda what: None),
            mock.patch.object(hal_common, "LOCK_DIR", str(LOCKS)),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.ring = hal_ring.Ring()
        self.addCleanup(self.ring.close)

    def test_init(self):
        self.assertEqual(self.ring.channels, 36)
        self.assertEqual(self.ring.pixels, 12)
        self.assertEqual(self.fake.assert_size, 36)

    def test_pixel(self):
        self.ring.pixel(0, (200, 0, 0))
        self.ring.show()
        frame = self.fake.frames[-1]
        self.assertEqual(frame[1], 200)
        self.assertEqual(sum(frame), 200)

    def test_brightness(self):
        self.ring.brightness(128)
        self.ring.fill((200, 0, 0))
        self.ring.show()
        frame = self.fake.frames[-1]
        self.assertEqual(frame[1], 100)

    def test_off(self):
        self.ring.fill((10, 20, 30))
        self.ring.show()
        self.ring.off()
        self.assertEqual(self.fake.frames[-1], bytes(36))

    def test_close(self):
        self.ring.close()
        self.assertTrue(self.fake.closed)

    def test_show_closed(self):
        self.ring.close()
        with self.assertRaises(HalError):
            self.ring.show()

    def test_close_error_releases(self):
        def bad_close(fd):
            raise OSError("close error")

        self.ring._close = bad_close
        with self.assertRaises(OSError):
            self.ring.close()
        self.assertIsNone(self.ring._fd)
        self.assertFalse(hal_common.locked("ring"))

    def test_bad_index(self):
        with self.assertRaises(HalError):
            self.ring.pixel(12, (1, 2, 3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
