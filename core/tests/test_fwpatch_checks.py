#!/usr/bin/env python3
"""Тесты `fwpatch.checks`: размер, том, UBI, порог 10 %."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fwpatch import checks  # noqa: E402
from fwpatch.errors import PatchError  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

APPROX_SIZE = checks.APPROX["system_b"]


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def image(self, size: int) -> Path:
        path = self.dir / "system_b.bin"
        path.touch()
        os.truncate(path, size)
        return path


class Volumes(unittest.TestCase):
    def test_known(self):
        self.assertEqual(checks.expected_volume("system_b"), "rootfs")
        self.assertEqual(checks.expected_volume("data"), "data")

    def test_unknown(self):
        with self.assertRaises(PatchError):
            checks.expected_volume("system_a")


class Validate(Base):
    def test_ok(self):
        path = self.image(2 * checks.PEB)
        with mock.patch.object(checks, "read_params",
                               return_value={"vol_name": "rootfs"}), \
             mock.patch.object(checks, "check_ubi", return_value=7):
            result = checks.validate_image(
                path, "system_b", no_check_size=True)
        self.assertEqual(result["vol_name"], "rootfs")
        self.assertEqual(result["records"], 7)
        self.assertEqual(result["size"], 2 * checks.PEB)

    def test_missing(self):
        with self.assertRaises(PatchError):
            checks.validate_image(self.dir / "nope.bin", "system_b")

    def test_not_peb(self):
        path = self.image(1234)
        with self.assertRaises(PatchError):
            checks.validate_image(path, "system_b")

    def test_wrong_volume(self):
        path = self.image(checks.PEB)
        with mock.patch.object(checks, "read_params",
                               return_value={"vol_name": "data"}):
            with self.assertRaises(PatchError):
                checks.validate_image(
                    path, "system_b", no_check_size=True)

    def test_check_ubi_gets_params(self):
        path = self.image(checks.PEB)
        with mock.patch.object(checks, "read_params",
                               return_value={"vol_name": "rootfs"}), \
             mock.patch.object(checks, "check_ubi",
                               return_value=3) as check:
            checks.validate_image(path, "system_b", no_check_size=True)
        self.assertEqual(check.call_args.args[1]["vol_name"], "rootfs")

    def test_broken_ubi(self):
        path = self.image(checks.PEB)
        with mock.patch.object(checks, "read_params",
                               return_value={"vol_name": "rootfs"}), \
             mock.patch.object(checks, "check_ubi",
                               side_effect=RuntimeError("bad index")):
            with self.assertRaises(PatchError):
                checks.validate_image(
                    path, "system_b", no_check_size=True)

    def test_size_prompt_declined(self):
        path = self.image(2 * checks.PEB)
        asked = []

        def ask(question, default):
            asked.append((question, default))
            return False

        with mock.patch.object(checks, "read_params",
                               return_value={"vol_name": "rootfs"}), \
             mock.patch.object(checks, "check_ubi", return_value=1):
            with self.assertRaises(PatchError):
                checks.validate_image(path, "system_b", ask=ask)
        self.assertEqual(len(asked), 1)
        self.assertIn("отличается от типичного", asked[0][0])
        self.assertFalse(asked[0][1])

    def test_size_prompt_accepted(self):
        path = self.image(2 * checks.PEB)
        with mock.patch.object(checks, "read_params",
                               return_value={"vol_name": "rootfs"}), \
             mock.patch.object(checks, "check_ubi", return_value=1):
            result = checks.validate_image(
                path, "system_b", ask=lambda q, d: True)
        self.assertEqual(result["vol_name"], "rootfs")

    def test_size_prompt_default_n(self):
        path = self.image(2 * checks.PEB)
        with mock.patch.object(checks, "read_params",
                               return_value={"vol_name": "rootfs"}), \
             mock.patch.object(checks, "check_ubi", return_value=1):
            with self.assertRaises(PatchError):
                checks.validate_image(path, "system_b")

    def test_no_check_size(self):
        path = self.image(2 * checks.PEB)
        asked = []
        with mock.patch.object(checks, "read_params",
                               return_value={"vol_name": "rootfs"}), \
             mock.patch.object(checks, "check_ubi", return_value=1):
            checks.validate_image(
                path, "system_b", no_check_size=True,
                ask=lambda q, d: asked.append(q) or False)
        self.assertEqual(asked, [])

    def test_size_ok_no_prompt(self):
        path = self.image(APPROX_SIZE)
        asked = []
        with mock.patch.object(checks, "read_params",
                               return_value={"vol_name": "rootfs"}), \
             mock.patch.object(checks, "check_ubi", return_value=1):
            checks.validate_image(
                path, "system_b",
                ask=lambda q, d: asked.append(q) or False)
        self.assertEqual(asked, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
