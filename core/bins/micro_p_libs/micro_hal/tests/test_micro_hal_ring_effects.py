#!/usr/bin/env python3
"""Тесты эффектов кольца без платы."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import lib_ring  # noqa: E402
from micro_hal.hal_common import HalError  # noqa: E402


class Color(unittest.TestCase):
    def test_primary(self):
        self.assertEqual(lib_ring.hsv_to_rgb(0), (255, 0, 0))
        self.assertEqual(lib_ring.hsv_to_rgb(120), (0, 255, 0))
        self.assertEqual(lib_ring.hsv_to_rgb(240), (0, 0, 255))

    def test_secondary(self):
        self.assertEqual(lib_ring.hsv_to_rgb(60), (255, 255, 0))
        self.assertEqual(lib_ring.hsv_to_rgb(180), (0, 255, 255))
        self.assertEqual(lib_ring.hsv_to_rgb(300), (255, 0, 255))

    def test_gray(self):
        self.assertEqual(lib_ring.hsv_to_rgb(0, 0, 100), (100, 100, 100))
        self.assertEqual(lib_ring.hsv_to_rgb(200, 0, 0), (0, 0, 0))


class Frames(unittest.TestCase):
    def test_rainbow(self):
        frame = lib_ring.rainbow_frame(12, 0)
        self.assertEqual(len(frame), 12)
        self.assertEqual(frame[0], (255, 0, 0))
        self.assertNotEqual(frame[0], frame[3])

    def test_blend(self):
        self.assertEqual(lib_ring.blend((0, 0, 0), (100, 200, 50), 128),
                         (50, 100, 25))
        self.assertEqual(lib_ring.blend((1, 2, 3), (4, 5, 6), 0), (1, 2, 3))
        self.assertEqual(lib_ring.blend((1, 2, 3), (4, 5, 6), 255),
                         (4, 5, 6))

    def test_fade_color(self):
        self.assertEqual(lib_ring.fade_color((10, 20, 30), 15), (0, 5, 15))
        self.assertEqual(lib_ring.fade_color((10, 20, 30), 0), (10, 20, 30))

    def test_breathe(self):
        self.assertEqual(lib_ring.breathe_frame(3, (10, 20, 30), 0),
                         [(0, 0, 0)] * 3)
        self.assertEqual(lib_ring.breathe_frame(3, (10, 20, 30), 255),
                         [(10, 20, 30)] * 3)
        self.assertEqual(lib_ring.breathe_frame(1, (200, 0, 0), 128),
                         [(100, 0, 0)])

    def test_comet(self):
        frame = lib_ring.comet_frame(12, (255, 0, 0), 5, 4)
        self.assertEqual(frame[5], (255, 0, 0))
        self.assertNotEqual(frame[4], (0, 0, 0))
        self.assertEqual(frame[1], (0, 0, 0))
        self.assertEqual(len(frame), 12)

    def test_theater(self):
        frame = lib_ring.theater_frame(12, (0, 255, 0), 0, 3)
        self.assertEqual(frame[0], (0, 255, 0))
        self.assertEqual(frame[3], (0, 255, 0))
        self.assertEqual(frame[1], (0, 0, 0))
        self.assertEqual(sum(1 for c in frame if c != (0, 0, 0)), 4)

    def test_wipe(self):
        frame = lib_ring.wipe_frame(6, (0, 0, 255), 2)
        self.assertEqual(frame[:2], [(0, 0, 255), (0, 0, 255)])
        self.assertEqual(frame[2:], [(0, 0, 0)] * 4)
        reverse = lib_ring.wipe_frame(6, (0, 0, 255), 2, reverse=True)
        self.assertEqual(reverse[-2:], [(0, 0, 255), (0, 0, 255)])


class FakeRing:
    pixels = 12

    def __init__(self):
        self.colors = [(0, 0, 0)] * self.pixels
        self.shows = 0

    def pixel(self, index, color):
        self.colors[index] = color

    def fill(self, color):
        self.colors = [color] * self.pixels

    def clear(self):
        self.colors = [(0, 0, 0)] * self.pixels

    def show(self):
        self.shows += 1


class Effects(unittest.TestCase):
    def setUp(self):
        self.ring = FakeRing()
        lib_ring.seed(1)
        patcher = mock.patch.object(lib_ring.time, "sleep", lambda delay: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_rainbow(self):
        lib_ring.rainbow(self.ring, cycles=1, delay=0, step=120)
        self.assertEqual(self.ring.shows, 3)

    def test_breathe(self):
        lib_ring.breathe(self.ring, (0, 0, 255), cycles=1, delay=0,
                         maximum=10, step=5)
        self.assertEqual(self.ring.shows, 5)
        self.assertEqual(self.ring.colors, [(0, 0, 0)] * 12)

    def test_comet(self):
        lib_ring.comet(self.ring, (255, 0, 0), tail=3, cycles=1, delay=0)
        self.assertEqual(self.ring.shows, 12)

    def test_theater(self):
        lib_ring.theater_chase(self.ring, (0, 255, 0), cycles=1, delay=0)
        self.assertEqual(self.ring.shows, 3)

    def test_wipe(self):
        lib_ring.color_wipe(self.ring, (0, 0, 255), cycles=1, delay=0)
        self.assertEqual(self.ring.shows, 12)
        self.assertEqual(self.ring.colors, [(0, 0, 255)] * 12)

    def test_bad_cycles(self):
        with self.assertRaises(HalError):
            lib_ring.rainbow(self.ring, cycles=0)

    def test_static(self):
        lib_ring.static(self.ring, (1, 2, 3))
        self.assertEqual(self.ring.shows, 1)
        self.assertEqual(self.ring.colors, [(1, 2, 3)] * 12)

    def test_blink(self):
        lib_ring.blink(self.ring, (10, 0, 0), cycles=2, delay=0)
        self.assertEqual(self.ring.shows, 4)
        self.assertEqual(self.ring.colors, [(0, 0, 0)] * 12)

    def test_fade(self):
        lib_ring.fade(self.ring, (200, 100, 50), cycles=1, delay=0,
                      step=64)
        self.assertEqual(self.ring.shows, 5)
        self.assertEqual(self.ring.colors, [(0, 0, 0)] * 12)

    def test_twinkle(self):
        lib_ring.twinkle(self.ring, (0, 0, 255), cycles=3, delay=0, count=1)
        self.assertEqual(self.ring.shows, 4)

    def test_sparkle(self):
        lib_ring.sparkle(self.ring, (0, 255, 0), cycles=3, delay=0, count=2)
        self.assertEqual(self.ring.shows, 4)

    def test_larson(self):
        lib_ring.larson_scanner(self.ring, (255, 0, 0), cycles=1, delay=0)
        self.assertEqual(self.ring.shows, 23)

    def test_bicolor(self):
        lib_ring.bicolor_chase(self.ring, (255, 0, 0), (0, 0, 255),
                               cycles=2, delay=0)
        self.assertEqual(self.ring.shows, 4)

    def test_tricolor(self):
        lib_ring.tricolor_chase(self.ring, ((255, 0, 0), (0, 255, 0),
                                            (0, 0, 255)),
                                cycles=2, delay=0)
        self.assertEqual(self.ring.shows, 6)

    def test_running(self):
        lib_ring.running_lights(self.ring, (255, 0, 0), (0, 0, 255),
                                cycles=1, delay=0, step=4)
        self.assertEqual(self.ring.shows, 6)

    def test_fire(self):
        lib_ring.fire_flicker(self.ring, cycles=3, delay=0)
        self.assertEqual(self.ring.shows, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
