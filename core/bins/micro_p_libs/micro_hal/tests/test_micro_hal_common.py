#!/usr/bin/env python3
"""Тесты micro_hal: общие функции без платы и без железа."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import HalError, __version__, check, format_check  # noqa: E402
from micro_hal import hal_common  # noqa: E402


class Paths(unittest.TestCase):
    def test_exists(self):
        self.assertTrue(hal_common.exists("/"))
        self.assertFalse(hal_common.exists("/нет-такого-пути-capsula"))

    def test_read_write(self):
        path = TMP / "micro_hal_common.txt"
        try:
            hal_common.write_text(path, "abc")
            self.assertEqual(hal_common.read_text(path), "abc")
        finally:
            if path.exists():
                path.unlink()


class Quote(unittest.TestCase):
    def test_quote(self):
        self.assertEqual(hal_common.quote("/tmp/a b.raw"),
                         "'/tmp/a b.raw'")

    def test_quote_rejects(self):
        for value in ("/tmp/a'b.raw", "/tmp/a\nb.raw", "/tmp/a\rb.raw"):
            with self.assertRaises(HalError):
                hal_common.quote(value)


class Commands(unittest.TestCase):
    def test_run_codes(self):
        self.assertEqual(hal_common.run("true"), 0)
        self.assertEqual(hal_common.run("false"), 1)

    def test_capture(self):
        path = TMP / "micro_hal_capture.txt"
        with mock.patch.object(hal_common, "CAPTURE", str(path)):
            code, text = hal_common.capture("printf abc")
        self.assertEqual(code, 0)
        self.assertIn("abc", text)
        self.assertFalse(path.exists())

    def test_capture_failure(self):
        path = TMP / "micro_hal_capture.txt"
        with mock.patch.object(hal_common, "CAPTURE", str(path)):
            code, text = hal_common.capture("false")
        self.assertEqual(code, 1)
        self.assertFalse(path.exists())

    def test_capture_pid_in_path(self):
        pattern = TMP / "micro_hal_capture.{}.out"
        path = TMP / "micro_hal_capture.4242.out"
        with mock.patch.object(hal_common, "CAPTURE", str(pattern)), \
                mock.patch.object(hal_common, "self_pid",
                                  return_value=4242):
            code, text = hal_common.capture("printf abc")
        self.assertEqual((code, text), (0, "abc"))
        self.assertFalse(path.exists())


class Root(unittest.TestCase):
    def test_matches_process(self):
        self.assertEqual(hal_common.is_root(), os.geteuid() == 0)


class VoiceAgent(unittest.TestCase):
    def test_types(self):
        self.assertIsInstance(hal_common.va_running(), bool)
        self.assertIsInstance(hal_common.va_pids(), list)

    def test_require(self):
        if hal_common.va_running():
            with self.assertRaises(HalError):
                hal_common.require_va_stopped("ring")
        else:
            hal_common.require_va_stopped("ring")


class Checks(unittest.TestCase):
    def test_items(self):
        items = check()
        names = [name for name, _value in items]
        for expected in ("root", "voice-agent", "ring", "display",
                         "keys", "light", "mic", "speaker"):
            self.assertIn(expected, names)
        for _name, value in items:
            self.assertIsInstance(value, str)
            self.assertTrue(value)

    def test_format(self):
        lines = format_check()
        self.assertEqual(len(lines), len(check()))
        for line in lines:
            self.assertIsInstance(line, str)
            self.assertIn("  ", line)

    def test_version(self):
        self.assertTrue(__version__)


if __name__ == "__main__":
    unittest.main(verbosity=2)
