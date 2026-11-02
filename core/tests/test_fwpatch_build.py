#!/usr/bin/env python3
"""Тесты `fwpatch.build`: unpack/pack, `.bad`, проверки."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fwpatch import build  # noqa: E402
from fwpatch.errors import PatchError  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class Run(Base):
    def test_timeout_message(self):
        expired = subprocess.TimeoutExpired(["ubitar", "unpack"],
                                            build.TIMEOUT)
        with mock.patch.object(build.subprocess, "run",
                               side_effect=expired):
            with self.assertRaises(PatchError) as ctx:
                build._run(["unpack"])
        text = str(ctx.exception)
        self.assertIn("таймаут", text)
        self.assertIn(str(build.TIMEOUT), text)

    def test_start_error_message(self):
        with mock.patch.object(build.subprocess, "run",
                               side_effect=OSError("нет файла")):
            with self.assertRaises(PatchError) as ctx:
                build._run(["pack"])
        self.assertIn("не запустился", str(ctx.exception))


class Unpack(Base):
    def test_ok(self):
        image = self.dir / "system_b.bin"
        image.write_bytes(b"image")
        out = self.dir / "system_b.tar"

        def fake(args, timeout=build.TIMEOUT):
            self.assertIn("unpack", args)
            Path(args[args.index("--out") + 1]).write_bytes(b"tar")

        with mock.patch.object(build, "_run", side_effect=fake):
            result = build.unpack(image, "system_b", out)
        self.assertEqual(result, out)
        self.assertEqual(out.read_bytes(), b"tar")

    def test_missing_image(self):
        with self.assertRaises(PatchError):
            build.unpack(self.dir / "nope", "system_b",
                         self.dir / "x.tar")

    def test_existing_needs_force(self):
        image = self.dir / "system_b.bin"
        image.write_bytes(b"image")
        out = self.dir / "system_b.tar"
        out.write_bytes(b"old")
        with self.assertRaises(PatchError):
            build.unpack(image, "system_b", out)

    def test_report(self):
        image = self.dir / "system_b.bin"
        image.write_bytes(b"image")
        out = self.dir / "system_b.tar"

        def fake(args, timeout=build.TIMEOUT):
            Path(args[args.index("--out") + 1]).write_bytes(b"tar")
            return "записей: файлов 1\n"

        with mock.patch.object(build, "_run", side_effect=fake):
            result = build.unpack(image, "system_b", out, report=True)
        self.assertEqual(result, (out, "записей: файлов 1\n"))


class Pack(Base):
    def _fake(self, size=10):
        def fake(args, timeout=build.TIMEOUT):
            self.assertIn("pack", args)
            Path(args[args.index("--out") + 1]).write_bytes(b"x" * size)
        return fake

    def test_ok(self):
        tar = self.dir / "part.tar"
        tar.write_bytes(b"tar")
        out = self.dir / "part.bin"
        with mock.patch.object(build, "_run", side_effect=self._fake()):
            result = build.pack(tar, out)
        self.assertEqual(result, out)
        self.assertEqual(out.stat().st_size, 10)
        self.assertFalse(out.with_name(out.name + ".bad").exists())

    def test_missing_tar(self):
        with self.assertRaises(PatchError):
            build.pack(self.dir / "nope.tar", self.dir / "out.bin")

    def test_existing_needs_force(self):
        tar = self.dir / "part.tar"
        tar.write_bytes(b"tar")
        out = self.dir / "part.bin"
        out.write_bytes(b"old")
        with self.assertRaises(PatchError):
            build.pack(tar, out)

    def test_verify_ok(self):
        tar = self.dir / "part.tar"
        tar.write_bytes(b"tar")
        out = self.dir / "part.bin"
        expected = {"size": 10, "vol_name": "rootfs",
                    "reserved_pebs": 468, "image_seq": 1}
        with mock.patch.object(build, "_run", side_effect=self._fake()), \
             mock.patch.object(build, "read_params",
                               return_value={"vol_name": "rootfs",
                                             "reserved_pebs": 468,
                                             "image_seq": 1}):
            build.pack(tar, out, expected=expected)
        self.assertTrue(out.exists())

    def test_verify_bad_size(self):
        tar = self.dir / "part.tar"
        tar.write_bytes(b"tar")
        out = self.dir / "part.bin"
        expected = {"size": 11}
        with mock.patch.object(build, "_run", side_effect=self._fake()):
            with self.assertRaises(PatchError):
                build.pack(tar, out, expected=expected)
        self.assertFalse(out.exists())
        self.assertTrue(out.with_name(out.name + ".bad").exists())

    def test_verify_bad_params(self):
        tar = self.dir / "part.tar"
        tar.write_bytes(b"tar")
        out = self.dir / "part.bin"
        expected = {"size": 10, "vol_name": "rootfs"}
        with mock.patch.object(build, "_run", side_effect=self._fake()), \
             mock.patch.object(build, "read_params",
                               return_value={"vol_name": "data"}):
            with self.assertRaises(PatchError):
                build.pack(tar, out, expected=expected)
        self.assertFalse(out.exists())
        self.assertTrue(out.with_name(out.name + ".bad").exists())

    def test_failure_keeps_no_final(self):
        tar = self.dir / "part.tar"
        tar.write_bytes(b"tar")
        out = self.dir / "part.bin"
        with mock.patch.object(build, "_run",
                               side_effect=PatchError("boom")):
            with self.assertRaises(PatchError):
                build.pack(tar, out)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
