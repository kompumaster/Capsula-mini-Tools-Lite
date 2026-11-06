#!/usr/bin/env python3
"""Тесты micro_hal: поиск сокета Pulse без платы и без Pulse."""

from __future__ import annotations

import os
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import HalError, hal_pulse  # noqa: E402


def _entry(moment):
    """Кортеж `os.stat()` с заданным `mtime` (индекс 8)."""
    return (0o140000, 0, 0, 1, 0, 0, 0, 0, moment, 0)


class Base(unittest.TestCase):
    def setUp(self):
        hal_pulse.forget()
        self.addCleanup(hal_pulse.forget)
        patch = mock.patch.dict(os.environ, {}, clear=True)
        patch.start()
        self.addCleanup(patch.stop)


class Env(Base):
    def test_env_wins(self):
        with mock.patch.dict(os.environ,
                             {"PULSE_SERVER": "unix:/tmp/x/native"}), \
                mock.patch.object(hal_pulse, "_socket") as check, \
                mock.patch.object(hal_pulse.os, "listdir") as scan:
            self.assertEqual(hal_pulse.server(), "unix:/tmp/x/native")
        check.assert_not_called()
        scan.assert_not_called()

    def test_env_tcp_passed(self):
        with mock.patch.dict(os.environ,
                             {"PULSE_SERVER": "tcp:host:4713"}):
            self.assertEqual(hal_pulse.server(), "tcp:host:4713")

    def test_proc_env(self):
        text = "A=1\x00PULSE_SERVER=unix:/tmp/e/native\x00B=2\x00"
        with mock.patch.object(hal_pulse.hal_common, "read_text",
                               return_value=text):
            self.assertEqual(hal_pulse._proc_env("PULSE_SERVER"),
                             "unix:/tmp/e/native")
            self.assertIsNone(hal_pulse._proc_env("NOPE"))

    def test_proc_env_missing(self):
        with mock.patch.object(hal_pulse.hal_common, "read_text",
                               side_effect=OSError):
            self.assertIsNone(hal_pulse._proc_env("PULSE_SERVER"))


class Runtime(Base):
    def test_xdg(self):
        with mock.patch.dict(os.environ,
                             {"XDG_RUNTIME_DIR": "/run/x/"}), \
                mock.patch.object(
                    hal_pulse, "_socket",
                    side_effect=lambda path: path
                    == "/run/x/pulse/native"):
            self.assertEqual(hal_pulse.server(),
                             "unix:/run/x/pulse/native")

    def test_run_user(self):
        def listing(path):
            if path == "/run/user":
                return ["1000", "не-uid"]
            raise OSError

        with mock.patch.object(hal_pulse.os, "listdir",
                               side_effect=listing), \
                mock.patch.object(
                    hal_pulse, "_socket",
                    side_effect=lambda path: path
                    == "/run/user/1000/pulse/native"):
            self.assertEqual(hal_pulse.server(),
                             "unix:/run/user/1000/pulse/native")

    def test_tmp_newest(self):
        def listing(path):
            if path == "/tmp":
                return ["pulse-a", "pulse-b", "other"]
            raise OSError

        def stat(path):
            if path.endswith("pulse-a/native"):
                return _entry(100)
            if path.endswith("pulse-b/native"):
                return _entry(200)
            raise OSError

        with mock.patch.object(hal_pulse.os, "listdir",
                               side_effect=listing), \
                mock.patch.object(hal_pulse.os, "stat",
                                  side_effect=stat):
            self.assertEqual(hal_pulse.server(),
                             "unix:/tmp/pulse-b/native")

    def test_tmp_mode(self):
        def listing(path):
            if path == "/tmp":
                return ["pulse-a"]
            raise OSError

        with mock.patch.object(hal_pulse.os, "listdir",
                               side_effect=listing), \
                mock.patch.object(hal_pulse.os, "stat",
                                  return_value=_entry(1)):
            self.assertEqual(hal_pulse.server(),
                             "unix:/tmp/pulse-a/native")

        with mock.patch.object(hal_pulse.os, "listdir",
                               side_effect=listing), \
                mock.patch.object(hal_pulse.os, "stat",
                                  return_value=(0o100000, 0, 0, 1,
                                                0, 0, 0, 0, 1, 0)):
            hal_pulse.forget()
            self.assertIsNone(hal_pulse.server())

    def test_no_pulse(self):
        with mock.patch.object(hal_pulse.os, "listdir",
                               side_effect=OSError):
            self.assertIsNone(hal_pulse.server())


class Cache(Base):
    def test_scan_once(self):
        with mock.patch.object(hal_pulse, "_socket",
                               return_value=True), \
                mock.patch.object(hal_pulse.os, "listdir",
                                  return_value=["pulse-a"]) as scan, \
                mock.patch.object(hal_pulse.os, "stat",
                                  return_value=_entry(1)):
            first = hal_pulse.server()
            second = hal_pulse.server()
        self.assertEqual(first, "unix:/tmp/pulse-a/native")
        self.assertEqual(first, second)
        # Первый вызов: /run/user и /tmp; второй — из кэша.
        self.assertEqual(scan.call_count, 2)

    def test_forget_rescans(self):
        with mock.patch.object(hal_pulse, "_socket",
                               return_value=True), \
                mock.patch.object(hal_pulse.os, "listdir",
                                  return_value=["pulse-a"]) as scan, \
                mock.patch.object(hal_pulse.os, "stat",
                                  return_value=_entry(1)):
            hal_pulse.server()
            hal_pulse.forget()
            hal_pulse.server()
        self.assertEqual(scan.call_count, 4)

    def test_vanished_path_rescans(self):
        state = {"dead": False}

        def check(path):
            if path == "/tmp/pulse-a/native":
                return not state["dead"]
            return path == "/tmp/pulse-b/native"

        def listing(path):
            if path == "/tmp":
                if state["dead"]:
                    return ["pulse-a", "pulse-b"]
                return ["pulse-a"]
            raise OSError

        def stat(path):
            if path.endswith("pulse-a/native"):
                return _entry(100)
            if path.endswith("pulse-b/native"):
                return _entry(200)
            raise OSError

        with mock.patch.object(hal_pulse, "_socket",
                               side_effect=check), \
                mock.patch.object(hal_pulse.os, "listdir",
                                  side_effect=listing), \
                mock.patch.object(hal_pulse.os, "stat",
                                  side_effect=stat):
            self.assertEqual(hal_pulse.server(),
                             "unix:/tmp/pulse-a/native")
            state["dead"] = True
            self.assertEqual(hal_pulse.server(),
                             "unix:/tmp/pulse-b/native")


class Prefix(Base):
    def test_prefix(self):
        with mock.patch.object(
                hal_pulse, "server",
                return_value="unix:/tmp/pulse-x/native"):
            self.assertEqual(
                hal_pulse.prefix(),
                "PULSE_SERVER='unix:/tmp/pulse-x/native' ")

    def test_prefix_empty(self):
        with mock.patch.object(hal_pulse, "server", return_value=None):
            self.assertEqual(hal_pulse.prefix(), "")

    def test_prefix_rejects_quote(self):
        with mock.patch.object(
                hal_pulse, "server",
                return_value="unix:/tmp/a'b"):
            with self.assertRaises(HalError):
                hal_pulse.prefix()


class Socket(Base):
    def test_socket_check(self):
        path = str(TMP / "pulse-test.sock")
        try:
            os.unlink(path)
        except OSError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(path)
        finally:
            server.close()
        try:
            self.assertTrue(hal_pulse._socket(path))

            regular = TMP / "pulse-regular.txt"
            regular.write_text("x")
            try:
                self.assertFalse(hal_pulse._socket(str(regular)))
            finally:
                regular.unlink()
            self.assertFalse(hal_pulse._socket(str(TMP / "нет-пути")))
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
