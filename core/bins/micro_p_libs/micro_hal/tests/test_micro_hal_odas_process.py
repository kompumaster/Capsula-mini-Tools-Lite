#!/usr/bin/env python3
"""Тесты micro_hal: управление процессом ODAS без платы."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, hal_common, hal_odas  # noqa: E402

LOCKS = REPO / "_tmp" / "odas_process_locks"


class Process(unittest.TestCase):
    def setUp(self):
        LOCKS.mkdir(parents=True, exist_ok=True)
        for path in LOCKS.iterdir():
            if path.is_dir():
                for item in path.iterdir():
                    item.unlink()
                path.rmdir()
            else:
                path.unlink()
        hal_common._LOCKS.clear()
        hal_odas._lock = None
        patch = mock.patch.object(hal_common, "LOCK_DIR", str(LOCKS))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(hal_common._LOCKS.clear)

    def test_quote(self):
        self.assertEqual(hal_odas._quote("/tmp/a b"), "'/tmp/a b'")
        with self.assertRaises(HalError):
            hal_odas._quote("/tmp/a'b")

    def test_running_stale(self):
        with mock.patch.object(hal_odas, "_read_pid", return_value=100), \
                mock.patch.object(hal_odas, "_alive", return_value=False), \
                mock.patch.object(hal_odas, "_scan", return_value=None), \
                mock.patch.object(hal_odas, "_forget_pid") as forget:
            self.assertIsNone(hal_odas.running())
        forget.assert_called_once_with()

    def test_running_wrong_process(self):
        with mock.patch.object(hal_odas, "_read_pid", return_value=100), \
                mock.patch.object(hal_odas, "_alive", return_value=True), \
                mock.patch.object(
                    hal_odas.hal_common, "read_text",
                    return_value="bash\x00"), \
                mock.patch.object(hal_odas, "_scan", return_value=None), \
                mock.patch.object(hal_odas, "_forget_pid") as forget:
            self.assertIsNone(hal_odas.running())
        forget.assert_called_once_with()

    def test_running_orphan(self):
        proc = [(777, "/usr/bin/odaslive -c /home/microp/odas/x.cfg")]
        with mock.patch.object(hal_odas, "_read_pid", return_value=None), \
                mock.patch.object(hal_odas.hal_common, "processes",
                                  return_value=proc), \
                mock.patch.object(hal_odas.hal_common, "stale_owner",
                                  return_value=True):
            self.assertEqual(hal_odas.running(), 777)

    def test_running_orphan_live_owner(self):
        proc = [(777, "/usr/bin/odaslive -c /home/microp/odas/x.cfg")]
        with mock.patch.object(hal_odas, "_read_pid", return_value=None), \
                mock.patch.object(hal_odas.hal_common, "processes",
                                  return_value=proc), \
                mock.patch.object(hal_odas.hal_common, "stale_owner",
                                  return_value=False):
            self.assertIsNone(hal_odas.running())

    def test_available(self):
        with mock.patch.object(
                hal_odas, "_is_exec", return_value=True), \
                mock.patch.object(
                    hal_odas.hal_common, "exists", return_value=True):
            self.assertTrue(hal_odas.available())
        with mock.patch.object(
                hal_odas.hal_common, "exists", return_value=False):
            self.assertFalse(hal_odas.available())

    def test_start_command(self):
        with mock.patch.object(
                hal_odas.hal_common, "require_va_stopped"), \
                mock.patch.object(
                    hal_odas, "running", side_effect=[None, 321]), \
                mock.patch.object(
                    hal_odas, "_is_exec", return_value=True), \
                mock.patch.object(
                    hal_odas.hal_common, "exists", return_value=True), \
                mock.patch.object(
                    hal_odas.hal_common, "run", return_value=0) as run, \
                mock.patch.object(hal_odas.time, "sleep"), \
                mock.patch.object(
                    hal_odas.hal_common, "write_text"):
            self.assertEqual(hal_odas.start(), 321)
        command = run.call_args[0][0]
        self.assertIn("LD_LIBRARY_PATH='{}'".format(hal_odas.LIBDIR),
                      command)
        self.assertIn(hal_odas.ODASLIVE, command)
        self.assertIn("-c '{}'".format(hal_odas.CONFIG), command)
        self.assertIn("> '/dev/null'", command)
        self.assertNotIn(hal_odas.LOG, command)
        self.assertIn("echo $! > '{}'".format(hal_odas.PID_FILE), command)

    def test_start_flags(self):
        with mock.patch.object(
                hal_odas.hal_common, "require_va_stopped"), \
                mock.patch.object(
                    hal_odas, "running", side_effect=[None, 321]), \
                mock.patch.object(
                    hal_odas, "_is_exec", return_value=True), \
                mock.patch.object(
                    hal_odas.hal_common, "exists", return_value=True), \
                mock.patch.object(
                    hal_odas.hal_common, "run", return_value=0) as run, \
                mock.patch.object(hal_odas.time, "sleep"), \
                mock.patch.object(
                    hal_odas.hal_common, "write_text"):
            hal_odas.start(single=True, verbose=True)
        command = run.call_args[0][0]
        self.assertIn("-c '{}' -s -v".format(hal_odas.CONFIG), command)
        self.assertIn("> '{}'".format(hal_odas.LOG), command)

    def test_start_twice(self):
        with mock.patch.object(
                hal_odas.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_odas, "running", return_value=100), \
                mock.patch.object(hal_odas.hal_common, "run") as run:
            with self.assertRaises(HalError):
                hal_odas.start()
        run.assert_not_called()

    def test_start_missing_binary(self):
        with mock.patch.object(
                hal_odas.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_odas, "running", return_value=None), \
                mock.patch.object(
                    hal_odas.hal_common, "exists", return_value=False):
            with self.assertRaises(HalError):
                hal_odas.start()

    def test_stop_not_running(self):
        with mock.patch.object(hal_odas, "running", return_value=None):
            self.assertFalse(hal_odas.stop())

    def test_stop_kills(self):
        with mock.patch.object(
                hal_odas, "running", return_value=100), \
                mock.patch.object(
                    hal_odas, "_alive", side_effect=[True, False, False]), \
                mock.patch.object(hal_odas.time, "sleep"), \
                mock.patch.object(
                    hal_odas, "_forget_pid") as forget, \
                mock.patch.object(
                    hal_odas.hal_common, "run", return_value=0) as run:
            self.assertTrue(hal_odas.stop())
        run.assert_any_call("kill 100")
        forget.assert_called_once_with()

    def test_log_tail(self):
        text = "a\nb\nc\n"
        with mock.patch.object(
                hal_odas.hal_common, "read_text", return_value=text):
            self.assertEqual(hal_odas.log_tail(2), "b\nc")

    def test_log_missing(self):
        with mock.patch.object(
                hal_odas.hal_common, "read_text",
                side_effect=OSError("нет")):
            self.assertEqual(hal_odas.log_tail(), "")

    def test_restart(self):
        with mock.patch.object(hal_odas, "stop") as stop, \
                mock.patch.object(hal_odas, "start", return_value=7) as start:
            self.assertEqual(hal_odas.restart(single=True), 7)
        stop.assert_called_once_with()
        start.assert_called_once_with(
            config=hal_odas.CONFIG, single=True, verbose=False)

    def test_status(self):
        with mock.patch.object(
                hal_odas, "available", return_value=True), \
                mock.patch.object(hal_odas, "running", return_value=5):
            result = hal_odas.status()
        self.assertTrue(result["available"])
        self.assertEqual(result["running"], 5)
        self.assertEqual(result["config"], hal_odas.CONFIG)


if __name__ == "__main__":
    unittest.main(verbosity=2)
