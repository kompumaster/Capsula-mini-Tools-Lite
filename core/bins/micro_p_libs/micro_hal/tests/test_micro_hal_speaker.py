#!/usr/bin/env python3
"""Тесты micro_hal: динамик без платы и без Pulse."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, hal_speaker  # noqa: E402


class Sinks(unittest.TestCase):
    def test_sinks(self):
        with mock.patch.object(hal_speaker.hal_volume, "sinks",
                               return_value=["master", "alarm"]):
            self.assertEqual(hal_speaker.sinks(), ["master", "alarm"])

    def test_default_sink(self):
        with mock.patch.object(hal_speaker.hal_volume, "default_sink",
                               return_value="master"):
            self.assertEqual(hal_speaker.default_sink(), "master")

    def test_available(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]):
            self.assertTrue(hal_speaker.available())
            self.assertFalse(hal_speaker.available("nope"))

    def test_available_without_pacat(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=False):
            self.assertFalse(hal_speaker.available())

    def test_check_sink_name(self):
        with mock.patch.object(hal_speaker, "sinks",
                               return_value=["master"]):
            with self.assertRaises(HalError):
                hal_speaker._check_sink("")
            with self.assertRaises(HalError):
                hal_speaker._check_sink("ma ster")
            with self.assertRaises(HalError):
                hal_speaker._check_sink("nope")
            self.assertEqual(hal_speaker._check_sink("master"), "master")


class Play(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(hal_speaker.hal_common,
                                  "require_va_stopped")
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master", "alarm"])
        patch.start()
        self.addCleanup(patch.stop)

    def test_raw_command(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=[None, 321]), \
                mock.patch.object(hal_speaker.hal_common, "run") as run:
            pid = hal_speaker.play("/tmp/a.raw", sink="master", raw=True,
                                   rate=16000, channels=1)
        self.assertEqual(pid, 321)
        command = run.call_args[0][0]
        self.assertIn("/usr/bin/pacat --playback", command)
        self.assertIn("--device='master'", command)
        self.assertIn("--raw", command)
        self.assertIn("--rate=16000", command)
        self.assertIn("--channels=1", command)
        self.assertIn("--format=s16le", command)
        self.assertIn("--latency-msec=100", command)
        self.assertIn("--client-name=micro_hal-spk", command)
        self.assertIn("< '/tmp/a.raw'", command)
        self.assertIn("echo $! > '{}'".format(hal_speaker.PID_FILE),
                      command)

    def test_wav_command(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=[None, 7]), \
                mock.patch.object(hal_speaker.hal_common, "run") as run:
            hal_speaker.play("/tmp/a.wav", sink="alarm")
        command = run.call_args[0][0]
        self.assertIn("/usr/bin/paplay --playback", command)
        self.assertNotIn("--raw", command)
        self.assertIn("--device='alarm'", command)

    def test_no_latency(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=[None, 7]), \
                mock.patch.object(hal_speaker.hal_common, "run") as run:
            hal_speaker.play("/tmp/a.raw", raw=True, latency_msec=None)
        self.assertNotIn("--latency-msec", run.call_args[0][0])

    def test_missing_file(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=False):
            with self.assertRaises(HalError):
                hal_speaker.play("/tmp/nope.wav")

    def test_busy(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_speaker, "running", return_value=5):
            with self.assertRaises(HalError):
                hal_speaker.play("/tmp/a.wav")

    def test_bad_rate(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_speaker, "running", return_value=None):
            with self.assertRaises(HalError):
                hal_speaker.play("/tmp/a.raw", raw=True, rate=0)

    def test_error_text(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=[None, None]), \
                mock.patch.object(hal_speaker.hal_common, "run"), \
                mock.patch.object(hal_speaker.hal_common, "read_text",
                                  return_value="Connection refused"):
            with self.assertRaises(HalError) as context:
                hal_speaker.play("/tmp/a.wav")
        self.assertIn("Connection refused", str(context.exception))

    def test_short_clip(self):
        with mock.patch.object(hal_speaker.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_speaker, "running", return_value=None), \
                mock.patch.object(hal_speaker.hal_common, "run"), \
                mock.patch.object(hal_speaker.hal_common, "read_text",
                                  return_value=""), \
                mock.patch.object(hal_speaker, "_read_pid",
                                  return_value=99):
            self.assertEqual(hal_speaker.play("/tmp/a.wav"), 99)


class Control(unittest.TestCase):
    def test_stop(self):
        with mock.patch.object(hal_speaker, "running", return_value=42), \
                mock.patch.object(hal_speaker, "_alive", return_value=False), \
                mock.patch.object(hal_speaker, "_forget_pid") as forget, \
                mock.patch.object(hal_speaker.hal_common, "run") as run:
            self.assertTrue(hal_speaker.stop())
        self.assertEqual(run.call_args[0][0], "kill 42")
        forget.assert_called_once_with()

    def test_stop_nothing(self):
        with mock.patch.object(hal_speaker, "running", return_value=None), \
                mock.patch.object(hal_speaker, "_forget_pid") as forget:
            self.assertFalse(hal_speaker.stop())
        forget.assert_called_once_with()

    def test_wait(self):
        with mock.patch.object(hal_speaker, "running",
                               side_effect=[42, 42, None]), \
                mock.patch.object(hal_speaker.time, "sleep"):
            self.assertTrue(hal_speaker.wait(1.0))

    def test_wait_timeout(self):
        with mock.patch.object(hal_speaker, "running", return_value=42), \
                mock.patch.object(hal_speaker.time, "sleep"), \
                mock.patch.object(hal_speaker.time, "time",
                                  side_effect=[0.0, 0.5, 2.0]):
            self.assertFalse(hal_speaker.wait(1.0))

    def test_wait_no_timeout(self):
        with mock.patch.object(hal_speaker, "running",
                               side_effect=[42, None]), \
                mock.patch.object(hal_speaker.time, "sleep"), \
                mock.patch.object(hal_speaker, "_forget_pid") as forget:
            self.assertTrue(hal_speaker.wait(None))
        forget.assert_called_once_with()

    def test_running_stale(self):
        with mock.patch.object(hal_speaker, "_read_pid", return_value=100), \
                mock.patch.object(hal_speaker, "_alive", return_value=False), \
                mock.patch.object(hal_speaker, "_scan", return_value=None), \
                mock.patch.object(hal_speaker, "_forget_pid") as forget:
            self.assertIsNone(hal_speaker.running())
        forget.assert_called_once_with()

    def test_running_wrong_process(self):
        with mock.patch.object(hal_speaker, "_read_pid", return_value=100), \
                mock.patch.object(hal_speaker, "_alive", return_value=True), \
                mock.patch.object(hal_speaker.hal_common, "read_text",
                                  return_value="bash\x00"), \
                mock.patch.object(hal_speaker, "_scan", return_value=None), \
                mock.patch.object(hal_speaker, "_forget_pid") as forget:
            self.assertIsNone(hal_speaker.running())
        forget.assert_called_once_with()

    def test_running_orphan(self):
        proc = [(555, "/usr/bin/pacat --client-name=micro_hal-spk")]
        with mock.patch.object(hal_speaker, "_read_pid", return_value=None), \
                mock.patch.object(hal_speaker.hal_common, "processes",
                                  return_value=proc), \
                mock.patch.object(hal_speaker.hal_common, "stale_owner",
                                  return_value=True):
            self.assertEqual(hal_speaker.running(), 555)

    def test_running_orphan_live_owner(self):
        proc = [(555, "/usr/bin/pacat --client-name=micro_hal-spk")]
        with mock.patch.object(hal_speaker, "_read_pid", return_value=None), \
                mock.patch.object(hal_speaker.hal_common, "processes",
                                  return_value=proc), \
                mock.patch.object(hal_speaker.hal_common, "stale_owner",
                                  return_value=False):
            self.assertIsNone(hal_speaker.running())

    def test_running_ok(self):
        with mock.patch.object(hal_speaker, "_read_pid", return_value=100), \
                mock.patch.object(hal_speaker, "_alive", return_value=True), \
                mock.patch.object(hal_speaker.hal_common, "read_text",
                                  return_value="/usr/bin/pacat\x00--raw\x00"):
            self.assertEqual(hal_speaker.running(), 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
