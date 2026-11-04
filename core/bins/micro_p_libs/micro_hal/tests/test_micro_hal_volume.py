#!/usr/bin/env python3
"""Тесты micro_hal: громкость без платы и без PulseAudio."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, hal_volume  # noqa: E402

SINKS = ["master", "alarm", "ring", "call"]


def pactl_text(volume="100", mute="no"):
    return (
        "Volume: front-left: 65536 / {}% / 0.00 dB, "
        "front-right: 65536 / {}% / 0.00 dB\n"
        "        balance 0.00\n"
        "Mute: {}\n".format(volume, volume, mute))


class Parsing(unittest.TestCase):
    def test_stereo_equal(self):
        self.assertEqual(
            hal_volume.parse_percent(pactl_text("100")), 100)

    def test_stereo_average(self):
        text = ("Volume: front-left: 1 / 40% / 0 dB, "
                "front-right: 1 / 60% / 0 dB")
        self.assertEqual(hal_volume.parse_percent(text), 50)

    def test_mono(self):
        self.assertEqual(
            hal_volume.parse_percent("Volume: mono: 1 / 35% / 0 dB"), 35)

    def test_no_percent(self):
        with self.assertRaises(HalError):
            hal_volume.parse_percent("Volume: нет данных")

    def test_mute_yes(self):
        self.assertTrue(hal_volume.parse_mute("Mute: yes\n"))

    def test_mute_no(self):
        self.assertFalse(hal_volume.parse_mute("Mute: no\n"))

    def test_mute_missing(self):
        with self.assertRaises(HalError):
            hal_volume.parse_mute("что-то другое\n")


class Discovery(unittest.TestCase):
    def test_available_true(self):
        with mock.patch.object(
                hal_volume.hal_common, "exists", return_value=True), \
                mock.patch.object(
                    hal_volume.hal_common, "capture",
                    return_value=(0, "Server Name: pulseaudio\n")):
            self.assertTrue(hal_volume.available())

    def test_available_no_pactl(self):
        with mock.patch.object(
                hal_volume.hal_common, "exists", return_value=False):
            self.assertFalse(hal_volume.available())

    def test_available_no_server(self):
        with mock.patch.object(
                hal_volume.hal_common, "exists", return_value=True), \
                mock.patch.object(
                    hal_volume.hal_common, "capture",
                    return_value=(1, "Connection failure\n")):
            self.assertFalse(hal_volume.available())

    def test_sinks(self):
        text = "".join(
            "{} {}\tmodule-virtual-sink.c\n".format(index, name)
            for index, name in enumerate(SINKS))
        with mock.patch.object(
                hal_volume.hal_common, "capture",
                return_value=(0, text)):
            self.assertEqual(hal_volume.sinks(), SINKS)

    def test_default_sink(self):
        text = "Server Name: pulseaudio\nDefault Sink: master\n"
        with mock.patch.object(
                hal_volume.hal_common, "capture",
                return_value=(0, text)):
            self.assertEqual(hal_volume.default_sink(), "master")

    def test_default_sink_missing(self):
        with mock.patch.object(
                hal_volume.hal_common, "capture",
                return_value=(0, "Server Name: pulseaudio\n")):
            with self.assertRaises(HalError):
                hal_volume.default_sink()


class Commands(unittest.TestCase):
    def run_with(self, sinks=None):
        return mock.patch.object(
            hal_volume, "sinks", return_value=sinks or SINKS)

    def test_get_percent(self):
        with self.run_with(), mock.patch.object(
                hal_volume, "_pactl",
                return_value=pactl_text("42")):
            self.assertEqual(hal_volume.get_percent("master"), 42)

    def test_set_percent(self):
        with self.run_with(), mock.patch.object(
                hal_volume, "_pactl", return_value="") as pactl:
            self.assertEqual(hal_volume.set_percent("master", 50), 50)
        pactl.assert_called_once_with(
            ["set-sink-volume", "master", "50%"])

    def test_set_percent_clamps_high(self):
        with self.run_with(), mock.patch.object(
                hal_volume, "_pactl", return_value=""):
            self.assertEqual(hal_volume.set_percent("master", 150), 100)

    def test_set_percent_clamps_low(self):
        with self.run_with(), mock.patch.object(
                hal_volume, "_pactl", return_value=""):
            self.assertEqual(hal_volume.set_percent("master", -5), 0)

    def test_get_mute(self):
        with self.run_with(), mock.patch.object(
                hal_volume, "_pactl", return_value="Mute: yes\n"):
            self.assertTrue(hal_volume.get_mute("master"))

    def test_set_mute(self):
        with self.run_with(), mock.patch.object(
                hal_volume, "_pactl", return_value="") as pactl:
            self.assertTrue(hal_volume.set_mute("master", True))
            self.assertFalse(hal_volume.set_mute("master", False))
        self.assertEqual(pactl.call_args_list, [
            mock.call(["set-sink-mute", "master", "1"]),
            mock.call(["set-sink-mute", "master", "0"]),
        ])

    def test_toggle_mute(self):
        with self.run_with(), mock.patch.object(
                hal_volume, "_pactl", return_value="") as pactl:
            hal_volume.toggle_mute("master")
        pactl.assert_called_once_with(["set-sink-mute", "master", "toggle"])

    def test_bad_name(self):
        with self.assertRaises(HalError):
            hal_volume._check_sink("master; reboot")

    def test_unknown_sink(self):
        with self.run_with(["master"]):
            with self.assertRaises(HalError):
                hal_volume._check_sink("no-such")


if __name__ == "__main__":
    unittest.main(verbosity=2)
