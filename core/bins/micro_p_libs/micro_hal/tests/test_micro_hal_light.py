#!/usr/bin/env python3
"""Тесты micro_hal: датчик света без платы и без железа."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import HalError, hal_common, hal_light  # noqa: E402


def write_value(name, text):
    path = TMP / name
    path.write_text(text)
    return path


class Values(unittest.TestCase):
    def setUp(self):
        self.paths = []

    def tearDown(self):
        for path in self.paths:
            if path.exists():
                path.unlink()

    def make(self, name, text):
        path = write_value(name, text)
        self.paths.append(path)
        return path

    def test_integer(self):
        path = self.make("light_int.txt", "123\n")
        self.assertEqual(hal_light.read(path), 123.0)

    def test_fractional(self):
        path = self.make("light_float.txt", "12.5\n")
        self.assertEqual(hal_light.read(path), 12.5)

    def test_zero(self):
        path = self.make("light_zero.txt", "0.000000\n")
        self.assertEqual(hal_light.read(path), 0.0)

    def test_negative(self):
        path = self.make("light_negative.txt", "-5.25\n")
        self.assertEqual(hal_light.read(path), -5.25)

    def test_missing(self):
        with self.assertRaises(HalError):
            hal_light.read(TMP / "light-нет-такого.txt")

    def test_empty(self):
        for text in ("", "   \n"):
            path = self.make("light_empty.txt", text)
            with self.assertRaises(HalError):
                hal_light.read(path)

    def test_garbage(self):
        path = self.make("light_garbage.txt", "abc\n")
        with self.assertRaises(HalError):
            hal_light.read(path)

    def test_lux_alias(self):
        path = self.make("light_alias.txt", "42.25\n")
        self.assertEqual(hal_light.lux(path), hal_light.read(path))


class Availability(unittest.TestCase):
    def test_available(self):
        path = write_value("light_available.txt", "1.0\n")
        try:
            self.assertTrue(hal_light.available(path))
        finally:
            if path.exists():
                path.unlink()
        self.assertFalse(hal_light.available(TMP / "light-нет-такого.txt"))

    def test_default_path(self):
        self.assertEqual(hal_light.SYSFS, hal_common.SYSFS_LIGHT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
