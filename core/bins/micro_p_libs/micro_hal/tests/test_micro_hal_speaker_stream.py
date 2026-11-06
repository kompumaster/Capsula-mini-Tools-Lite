#!/usr/bin/env python3
"""Тесты micro_hal: поток PCM и пауза динамика без Pulse."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, hal_speaker  # noqa: E402

SINK = "master"


class FakeHandle:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, data):
        self.data += data
        return len(data)

    def close(self):
        self.closed = True


def _running_after_open():
    """`running()`: сначала пусто (перед запуском), потом 321."""
    calls = {"n": 0}

    def value():
        calls["n"] += 1
        return None if calls["n"] == 1 else 321
    return value


class Pause(unittest.TestCase):
    def setUp(self):
        hal_speaker._PAUSED = False
        hal_speaker._ACTIVE_SINK = "master"
        self.addCleanup(setattr, hal_speaker, "_PAUSED", False)
        self.addCleanup(setattr, hal_speaker, "_ACTIVE_SINK", "master")

    def test_pause(self):
        with mock.patch.object(hal_speaker, "running",
                               return_value=42), \
                mock.patch.object(hal_speaker, "_suspend_sink",
                                  return_value=True) as suspend:
            self.assertTrue(hal_speaker.pause())
        suspend.assert_called_once_with("master", True)
        self.assertTrue(hal_speaker._PAUSED)

    def test_pause_not_playing(self):
        with mock.patch.object(hal_speaker, "running",
                               return_value=None):
            self.assertFalse(hal_speaker.pause())

    def test_pause_twice(self):
        hal_speaker._PAUSED = True
        with mock.patch.object(hal_speaker, "running",
                               return_value=42), \
                mock.patch.object(hal_speaker, "_suspend_sink",
                                  return_value=True) as suspend:
            self.assertFalse(hal_speaker.pause())
        suspend.assert_not_called()

    def test_pause_fails(self):
        with mock.patch.object(hal_speaker, "running",
                               return_value=42), \
                mock.patch.object(hal_speaker, "_suspend_sink",
                                  return_value=False):
            self.assertFalse(hal_speaker.pause())
        self.assertFalse(hal_speaker._PAUSED)

    def test_resume(self):
        hal_speaker._PAUSED = True
        with mock.patch.object(hal_speaker, "running",
                               return_value=42), \
                mock.patch.object(hal_speaker, "_suspend_sink",
                                  return_value=True) as suspend:
            self.assertTrue(hal_speaker.resume())
        suspend.assert_called_once_with("master", False)
        self.assertFalse(hal_speaker._PAUSED)

    def test_resume_not_paused(self):
        with mock.patch.object(hal_speaker, "running",
                               return_value=42), \
                mock.patch.object(hal_speaker, "_suspend_sink",
                                  return_value=True) as suspend:
            self.assertFalse(hal_speaker.resume())
        suspend.assert_not_called()

    def test_paused(self):
        hal_speaker._PAUSED = True
        with mock.patch.object(hal_speaker, "running",
                               return_value=42):
            self.assertTrue(hal_speaker.paused())

    def test_paused_not_playing(self):
        hal_speaker._PAUSED = True
        with mock.patch.object(hal_speaker, "running",
                               return_value=None):
            self.assertFalse(hal_speaker.paused())


class Open(unittest.TestCase):
    def test_open(self):
        handle = FakeHandle()
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=_running_after_open()), \
                mock.patch.object(hal_speaker.hal_common, "run",
                                  return_value=0) as run, \
                mock.patch.object(hal_speaker, "_open_fifo",
                                  return_value=handle):
            stream = hal_speaker.Stream(rate=24000)
            self.assertIs(stream.open(), stream)
            self.assertTrue(stream.running())
        command = run.call_args_list[0][0][0]
        self.assertIn("mkfifo", command)
        launch = run.call_args_list[1][0][0]
        self.assertIn("/usr/bin/pacat --playback", launch)
        self.assertIn("--raw", launch)
        self.assertIn("--rate=24000", launch)
        self.assertIn("--channels=1", launch)
        self.assertIn("--format=s16le", launch)
        self.assertIn("< {}".format(
            hal_speaker.hal_common.quote(hal_speaker.FIFO)), launch)
        self.assertEqual(stream.pid(), 321)
        self.assertEqual(hal_speaker._ACTIVE_SINK, "master")

    def test_process_before_fifo(self):
        events = []
        handle = FakeHandle()

        def run(command):
            events.append("run")
            return 0

        def open_fifo():
            events.append("open")
            return handle

        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=_running_after_open()), \
                mock.patch.object(hal_speaker.hal_common, "run",
                                  side_effect=run), \
                mock.patch.object(hal_speaker, "_open_fifo",
                                  side_effect=open_fifo):
            hal_speaker.Stream().open()
        self.assertEqual(events, ["run", "run", "open"])

    def test_died_after_fifo(self):
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=[None, 321, None, None]), \
                mock.patch.object(hal_speaker.hal_common, "run",
                                  return_value=0), \
                mock.patch.object(hal_speaker, "_open_fifo",
                                  return_value=FakeHandle()), \
                mock.patch.object(hal_speaker, "_remove_fifo"), \
                mock.patch.object(hal_speaker, "_halt"):
            with self.assertRaises(HalError):
                hal_speaker.Stream().open()

    def test_play_sets_sink(self):
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master", "alarm"]), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=[None, 321]), \
                mock.patch.object(hal_speaker.hal_common, "run"):
            hal_speaker.play("/tmp/a.raw", sink="alarm", raw=True)
        self.assertEqual(hal_speaker._ACTIVE_SINK, "alarm")

    def test_open_busy(self):
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker, "running",
                                  return_value=100):
            with self.assertRaises(HalError):
                hal_speaker.Stream().open()

    def test_open_without_pacat(self):
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker, "running",
                                  return_value=None), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=False):
            with self.assertRaises(HalError):
                hal_speaker.Stream().open()

    def test_open_mkfifo_fails(self):
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker, "running",
                                  return_value=None), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker.hal_common, "run",
                                  return_value=1), \
                mock.patch.object(hal_speaker, "_remove_fifo") as remove:
            with self.assertRaises(HalError):
                hal_speaker.Stream().open()
        remove.assert_called()

    def test_open_pacat_fails(self):
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker, "running",
                                  return_value=None), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker.hal_common, "run",
                                  return_value=0), \
                mock.patch.object(hal_speaker, "_open_fifo",
                                  return_value=FakeHandle()), \
                mock.patch.object(hal_speaker, "_error_text",
                                  return_value="Connection refused"), \
                mock.patch.object(hal_speaker, "_halt"), \
                mock.patch.object(hal_speaker, "_remove_fifo"):
            with self.assertRaises(HalError) as context:
                hal_speaker.Stream().open()
        self.assertIn("Connection refused", str(context.exception))


class Write(unittest.TestCase):
    def opened(self):
        handle = FakeHandle()
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=_running_after_open()), \
                mock.patch.object(hal_speaker.hal_common, "run",
                                  return_value=0), \
                mock.patch.object(hal_speaker, "_open_fifo",
                                  return_value=handle):
            stream = hal_speaker.Stream()
            stream.open()
        return stream, handle

    def test_write(self):
        stream, handle = self.opened()
        with mock.patch.object(hal_speaker, "running",
                               return_value=321):
            self.assertEqual(stream.write(b"\x01\x02"), 2)
        self.assertEqual(handle.data, b"\x01\x02")

    def test_write_odd(self):
        stream, _handle = self.opened()
        with mock.patch.object(hal_speaker, "running",
                               return_value=321):
            with self.assertRaises(HalError):
                stream.write(b"\x01")

    def test_write_not_bytes(self):
        stream, _handle = self.opened()
        with mock.patch.object(hal_speaker, "running",
                               return_value=321):
            with self.assertRaises(HalError):
                stream.write("abc")

    def test_write_closed(self):
        stream, _handle = self.opened()
        stream._opened = False
        with self.assertRaises(HalError):
            stream.write(b"\x00\x00")

    def test_write_process_gone(self):
        stream, _handle = self.opened()
        with mock.patch.object(hal_speaker, "running",
                               return_value=None):
            with self.assertRaises(HalError):
                stream.write(b"\x00\x00")


class Close(unittest.TestCase):
    def opened(self):
        handle = FakeHandle()
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=_running_after_open()), \
                mock.patch.object(hal_speaker.hal_common, "run",
                                  return_value=0), \
                mock.patch.object(hal_speaker, "_open_fifo",
                                  return_value=handle):
            stream = hal_speaker.Stream()
            stream.open()
        return stream, handle

    def test_close(self):
        stream, handle = self.opened()
        with mock.patch.object(hal_speaker, "wait",
                               return_value=True), \
                mock.patch.object(hal_speaker, "_remove_fifo") as remove:
            self.assertTrue(stream.close())
            self.assertFalse(stream.close())
        self.assertTrue(handle.closed)
        remove.assert_called()

    def test_close_halts(self):
        stream, _handle = self.opened()
        with mock.patch.object(hal_speaker, "wait",
                               return_value=False), \
                mock.patch.object(hal_speaker, "_halt") as halt, \
                mock.patch.object(hal_speaker, "_remove_fifo"):
            self.assertTrue(stream.close())
        halt.assert_called()

    def test_stop(self):
        stream, _handle = self.opened()
        with mock.patch.object(hal_speaker, "_halt") as halt, \
                mock.patch.object(hal_speaker, "running",
                                  return_value=321), \
                mock.patch.object(hal_speaker, "_remove_fifo"):
            self.assertTrue(stream.stop())
            self.assertFalse(stream.stop())
        halt.assert_called_once()

    def test_stop_not_opened(self):
        stream = hal_speaker.Stream()
        with mock.patch.object(hal_speaker, "_halt") as halt:
            self.assertFalse(stream.stop())
        halt.assert_not_called()

    def test_context(self):
        handle = FakeHandle()
        with mock.patch.object(hal_speaker.hal_common,
                               "require_va_stopped"), \
                mock.patch.object(hal_speaker, "sinks",
                                  return_value=["master"]), \
                mock.patch.object(hal_speaker.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_speaker, "running",
                                  side_effect=_running_after_open()), \
                mock.patch.object(hal_speaker.hal_common, "run",
                                  return_value=0), \
                mock.patch.object(hal_speaker, "_open_fifo",
                                  return_value=handle), \
                mock.patch.object(hal_speaker, "wait",
                                  return_value=True), \
                mock.patch.object(hal_speaker, "_remove_fifo"):
            with hal_speaker.Stream() as stream:
                self.assertTrue(stream.running())
        self.assertTrue(handle.closed)


if __name__ == "__main__":
    unittest.main()
