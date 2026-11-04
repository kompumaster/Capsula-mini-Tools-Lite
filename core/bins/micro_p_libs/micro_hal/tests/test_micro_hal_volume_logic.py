#!/usr/bin/env python3
"""Тесты micro_hal: логика громкости без платы и без PulseAudio."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, lib_volume  # noqa: E402


class Volume(unittest.TestCase):
    def make(self, sink="master", step=5):
        return lib_volume.Volume(sink=sink, step=step)

    def test_defaults(self):
        volume = self.make()
        self.assertEqual(volume.sink, "master")
        self.assertEqual(volume.step, 5)

    def test_custom(self):
        volume = self.make("alarm", 10)
        self.assertEqual(volume.sink, "alarm")
        self.assertEqual(volume.step, 10)

    def test_bad_step(self):
        with self.assertRaises(HalError):
            self.make(step=0)

    def test_get(self):
        volume = self.make()
        with mock.patch.object(
                lib_volume.hal_volume, "get_percent",
                return_value=42) as get:
            self.assertEqual(volume.get(), 42)
        get.assert_called_once_with("master")

    def test_set(self):
        volume = self.make()
        with mock.patch.object(
                lib_volume.hal_volume, "set_percent",
                side_effect=lambda sink, value: value) as set_:
            self.assertEqual(volume.set(70), 70)
        set_.assert_called_once_with("master", 70)

    def test_up(self):
        volume = self.make()

        def set_(sink, value):
            return value

        with mock.patch.object(
                lib_volume.hal_volume, "get_percent",
                return_value=50), mock.patch.object(
                lib_volume.hal_volume, "set_percent", side_effect=set_) as set_:
            self.assertEqual(volume.up(), 55)
        set_.assert_called_once_with("master", 55)

    def test_up_clamps(self):
        volume = self.make()
        with mock.patch.object(
                lib_volume.hal_volume, "get_percent", return_value=98), \
                mock.patch.object(
                    lib_volume.hal_volume, "set_percent",
                    side_effect=lambda sink, value: value):
            self.assertEqual(volume.up(), 100)

    def test_down_clamps(self):
        volume = self.make()
        with mock.patch.object(
                lib_volume.hal_volume, "get_percent", return_value=3), \
                mock.patch.object(
                    lib_volume.hal_volume, "set_percent",
                    side_effect=lambda sink, value: value):
            self.assertEqual(volume.down(), 0)

    def test_up_custom_step(self):
        volume = self.make(step=10)
        with mock.patch.object(
                lib_volume.hal_volume, "get_percent", return_value=50), \
                mock.patch.object(
                    lib_volume.hal_volume, "set_percent",
                    side_effect=lambda sink, value: value):
            self.assertEqual(volume.up(), 60)

    def test_up_explicit_step(self):
        volume = self.make(step=10)
        with mock.patch.object(
                lib_volume.hal_volume, "get_percent", return_value=50), \
                mock.patch.object(
                    lib_volume.hal_volume, "set_percent",
                    side_effect=lambda sink, value: value):
            self.assertEqual(volume.up(2), 52)

    def test_bad_up_step(self):
        volume = self.make()
        with self.assertRaises(HalError):
            volume.up(0)
        with self.assertRaises(HalError):
            volume.down(-1)

    def test_mute(self):
        volume = self.make()
        with mock.patch.object(
                lib_volume.hal_volume, "set_mute",
                return_value=True) as set_:
            self.assertTrue(volume.mute())
        set_.assert_called_once_with("master", True)

    def test_unmute(self):
        volume = self.make()
        with mock.patch.object(
                lib_volume.hal_volume, "set_mute",
                return_value=False) as set_:
            self.assertFalse(volume.unmute())
        set_.assert_called_once_with("master", False)

    def test_muted(self):
        volume = self.make()
        with mock.patch.object(
                lib_volume.hal_volume, "get_mute",
                return_value=True) as get:
            self.assertTrue(volume.muted())
        get.assert_called_once_with("master")

    def test_toggle(self):
        volume = self.make()
        with mock.patch.object(
                lib_volume.hal_volume, "toggle_mute") as toggle, \
                mock.patch.object(
                    lib_volume.hal_volume, "get_mute",
                    return_value=True):
            self.assertTrue(volume.toggle())
        toggle.assert_called_once_with("master")


if __name__ == "__main__":
    unittest.main(verbosity=2)
