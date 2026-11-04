#!/usr/bin/env python3
"""Тесты micro_hal: микрофоны без платы и без Pulse."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import HalError, hal_mic  # noqa: E402


class Paths(unittest.TestCase):
    def test_quote(self):
        self.assertEqual(hal_mic._quote("/tmp/a b.raw"), "'/tmp/a b.raw'")

    def test_quote_rejects(self):
        with self.assertRaises(HalError):
            hal_mic._quote("/tmp/a'b.raw")
        with self.assertRaises(HalError):
            hal_mic._quote("/tmp/a\nb.raw")


class Discovery(unittest.TestCase):
    def test_sources(self):
        text = (
            "0\talsa_playback.monitor\tmodule-alsa-sink.c\ts16le 2ch\n"
            "8\tmics\tmodule-alsa-source.c\ts16le 4ch\n"
        )
        with mock.patch.object(
                hal_mic.hal_common, "capture",
                return_value=(0, text)):
            self.assertEqual(
                hal_mic.sources(),
                ["alsa_playback.monitor", "mics"])

    def test_sources_error(self):
        with mock.patch.object(
                hal_mic.hal_common, "capture",
                return_value=(1, "")):
            with self.assertRaises(HalError):
                hal_mic.sources()

    def test_available(self):
        with mock.patch.object(
                hal_mic.hal_common, "exists", return_value=True), \
                mock.patch.object(
                    hal_mic, "sources", return_value=["mics"]):
            self.assertTrue(hal_mic.available("mics"))
        with mock.patch.object(
                hal_mic.hal_common, "exists", return_value=False):
            self.assertFalse(hal_mic.available("mics"))

    def test_unknown_source(self):
        with self.assertRaises(HalError):
            hal_mic._check_source("no-such")

    def test_missing_source(self):
        with mock.patch.object(
                hal_mic, "sources", return_value=["speex"]):
            with self.assertRaises(HalError):
                hal_mic._check_source("mics")


class StartStop(unittest.TestCase):
    def test_start_command(self):
        path = TMP / "mic-capture.raw"
        with mock.patch.object(
                hal_mic.hal_common, "require_va_stopped"), \
                mock.patch.object(
                    hal_mic, "_check_source", return_value="mics"), \
                mock.patch.object(
                    hal_mic, "running", side_effect=[None, 321]), \
                mock.patch.object(
                    hal_mic.hal_common, "run", return_value=0) as run, \
                mock.patch.object(hal_mic.time, "sleep"):
            self.assertEqual(hal_mic.start(str(path)), 321)
        command = run.call_args[0][0]
        self.assertIn("--device='mics'", command)
        self.assertIn("--rate=16000", command)
        self.assertIn("--channels=4", command)
        self.assertIn("--no-remap", command)
        self.assertIn("--client-name=micro_hal-mic", command)
        self.assertIn("> '{}'".format(path), command)
        self.assertIn("echo $! > '{}'".format(hal_mic.PID_FILE), command)

    def test_start_twice(self):
        with mock.patch.object(
                hal_mic.hal_common, "require_va_stopped"), \
                mock.patch.object(
                    hal_mic, "_check_source", return_value="mics"), \
                mock.patch.object(hal_mic, "running", return_value=100), \
                mock.patch.object(hal_mic.hal_common, "run") as run:
            with self.assertRaises(HalError):
                hal_mic.start(str(TMP / "mic.raw"))
        run.assert_not_called()

    def test_start_no_folder(self):
        with mock.patch.object(
                hal_mic.hal_common, "require_va_stopped"), \
                mock.patch.object(
                    hal_mic, "_check_source", return_value="mics"), \
                mock.patch.object(hal_mic, "running", return_value=None):
            with self.assertRaises(HalError):
                hal_mic.start(str(TMP / "no-such-dir" / "mic.raw"))

    def test_stop_not_running(self):
        with mock.patch.object(hal_mic, "running", return_value=None):
            self.assertFalse(hal_mic.stop())

    def test_stop_kills(self):
        with mock.patch.object(
                hal_mic, "running", return_value=100), \
                mock.patch.object(
                    hal_mic, "_alive", side_effect=[True, False, False]), \
                mock.patch.object(hal_mic.time, "sleep"), \
                mock.patch.object(
                    hal_mic, "_forget_pid") as forget, \
                mock.patch.object(
                    hal_mic.hal_common, "run", return_value=0) as run:
            self.assertTrue(hal_mic.stop())
        run.assert_any_call("kill 100")
        forget.assert_called_once_with()

    def test_running_stale(self):
        with mock.patch.object(hal_mic, "_read_pid", return_value=100), \
                mock.patch.object(hal_mic, "_alive", return_value=False), \
                mock.patch.object(hal_mic, "_scan", return_value=None), \
                mock.patch.object(hal_mic, "_forget_pid") as forget:
            self.assertIsNone(hal_mic.running())
        forget.assert_called_once_with()

    def test_running_wrong_process(self):
        with mock.patch.object(hal_mic, "_read_pid", return_value=100), \
                mock.patch.object(hal_mic, "_alive", return_value=True), \
                mock.patch.object(
                    hal_mic.hal_common, "read_text",
                    return_value="bash\x00"), \
                mock.patch.object(hal_mic, "_scan", return_value=None), \
                mock.patch.object(hal_mic, "_forget_pid") as forget:
            self.assertIsNone(hal_mic.running())
        forget.assert_called_once_with()

    def test_running_orphan(self):
        proc = [(555, "parec --device=mics --client-name=micro_hal-mic")]
        with mock.patch.object(hal_mic, "_read_pid", return_value=None), \
                mock.patch.object(hal_mic.hal_common, "processes",
                                  return_value=proc), \
                mock.patch.object(hal_mic.hal_common, "stale_owner",
                                  return_value=True):
            self.assertEqual(hal_mic.running(), 555)

    def test_running_orphan_live_owner(self):
        proc = [(555, "parec --device=mics --client-name=micro_hal-mic")]
        with mock.patch.object(hal_mic, "_read_pid", return_value=None), \
                mock.patch.object(hal_mic.hal_common, "processes",
                                  return_value=proc), \
                mock.patch.object(hal_mic.hal_common, "stale_owner",
                                  return_value=False):
            self.assertIsNone(hal_mic.running())


class Capture(unittest.TestCase):
    def test_capture_size(self):
        path = TMP / "mic-capture-test.raw"
        path.write_bytes(b"\x00" * 128)
        try:
            with mock.patch.object(hal_mic, "start"), \
                    mock.patch.object(hal_mic, "stop"), \
                    mock.patch.object(hal_mic.time, "sleep"):
                size = hal_mic.capture(str(path), 1)
            self.assertEqual(size, 128)
        finally:
            if path.exists():
                path.unlink()

    def test_capture_empty(self):
        path = TMP / "mic-capture-empty.raw"
        path.write_bytes(b"")
        try:
            with mock.patch.object(hal_mic, "start"), \
                    mock.patch.object(hal_mic, "stop"), \
                    mock.patch.object(hal_mic.time, "sleep"):
                with self.assertRaises(HalError):
                    hal_mic.capture(str(path), 1)
        finally:
            if path.exists():
                path.unlink()

    def test_bad_seconds(self):
        with self.assertRaises(HalError):
            hal_mic.capture(str(TMP / "mic.raw"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
