#!/usr/bin/env python3
"""Тесты micro_hal: подстановка `PULSE_SERVER` в команды Pulse."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import (  # noqa: E402
    HalError, hal_bt, hal_mic, hal_pulse, hal_speaker, hal_volume,
)

PREFIX = "PULSE_SERVER='unix:/tmp/pulse-x/native' "


class Volume(unittest.TestCase):
    def test_pactl_prefix(self):
        with mock.patch.object(hal_pulse, "prefix",
                               return_value=PREFIX), \
                mock.patch.object(hal_volume.hal_common, "capture",
                                  return_value=(0, "")) as capture:
            hal_volume._pactl(["info"])
        command = capture.call_args[0][0]
        self.assertEqual(command,
                         PREFIX + "/usr/bin/pactl info")

    def test_pactl_without_prefix(self):
        with mock.patch.object(hal_pulse, "prefix", return_value=""), \
                mock.patch.object(hal_volume.hal_common, "capture",
                                  return_value=(0, "")) as capture:
            hal_volume._pactl(["list", "short", "sinks"])
        self.assertEqual(capture.call_args[0][0],
                         "/usr/bin/pactl list short sinks")

    def test_available_prefix(self):
        with mock.patch.object(hal_pulse, "prefix",
                               return_value=PREFIX), \
                mock.patch.object(hal_volume.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_volume.hal_common, "capture",
                                  return_value=(0, "Server Name: x\n")
                                  ) as capture:
            self.assertTrue(hal_volume.available())
        self.assertTrue(capture.call_args[0][0].startswith(PREFIX))


class Speaker(unittest.TestCase):
    def test_play_prefix(self):
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=[None, 321]), \
                mock.patch.object(hal_speaker.hal_common, "run") as run, \
                mock.patch.object(hal_pulse, "prefix",
                                  return_value=PREFIX):
            hal_speaker.play("/tmp/a.raw", raw=True)
        self.assertTrue(run.call_args[0][0].startswith(PREFIX))


class Mic(unittest.TestCase):
    def test_sources_prefix(self):
        text = "0\tmics\tmodule-alsa-source.c\n"
        with mock.patch.object(hal_pulse, "prefix",
                               return_value=PREFIX), \
                mock.patch.object(hal_mic.hal_common, "capture",
                                  return_value=(0, text)) as capture:
            self.assertEqual(hal_mic.sources(), ["mics"])
        self.assertEqual(
            capture.call_args[0][0],
            PREFIX + "/usr/bin/pactl list short sources")

    def test_start_prefix(self):
        path = "/tmp/mic-test.raw"
        with mock.patch.object(hal_mic.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_mic, "sources",
                                  return_value=["mics"]), \
                mock.patch.object(hal_mic, "running",
                                  side_effect=[None, 321]), \
                mock.patch.object(hal_mic.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_mic.hal_common, "lock"), \
                mock.patch.object(hal_mic.hal_common, "run") as run, \
                mock.patch.object(hal_pulse, "prefix",
                                  return_value=PREFIX):
            self.assertEqual(hal_mic.start(path), 321)
        self.assertTrue(run.call_args[0][0].startswith(PREFIX))


class Bt(unittest.TestCase):
    def test_pactl_prefix(self):
        with mock.patch.object(hal_pulse, "prefix",
                               return_value=PREFIX), \
                mock.patch.object(hal_bt.hal_common, "capture",
                                  return_value=(0, "")) as capture:
            hal_bt._pactl("list short sources")
        self.assertEqual(capture.call_args[0][0],
                         PREFIX + "/usr/bin/pactl list short sources")

    def test_label_after_prefix(self):
        with mock.patch.object(hal_pulse, "prefix",
                               return_value=PREFIX), \
                mock.patch.object(hal_bt.hal_common, "capture",
                                  return_value=(1, "Connection refused")):
            with self.assertRaises(HalError) as context:
                hal_bt._pactl("info")
        self.assertTrue(str(context.exception).startswith("pactl: "))


if __name__ == "__main__":
    unittest.main()
