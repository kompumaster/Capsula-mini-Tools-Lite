#!/usr/bin/env python3
"""Тесты `common.archive`: zip рядом, очистка, коллизии."""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import archive  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)
        self.folder = self.dir / "parts"
        self.folder.mkdir()

    def tearDown(self):
        self._tmp.cleanup()


class Archive(Base):
    def test_files_and_dirs(self):
        (self.folder / "a.bin").write_bytes(b"a")
        (self.folder / ".hidden").write_bytes(b"h")
        sub = self.folder / "sub"
        sub.mkdir()
        (sub / "b.bin").write_bytes(b"b")

        with mock.patch.object(archive, "_stamp",
                               return_value="20260101-000000"):
            result = archive.archive_folder(self.folder, prefix="parts")

        self.assertEqual(
            result, self.dir / "parts_20260101-000000.zip")
        self.assertTrue(self.folder.is_dir())
        self.assertEqual(list(self.folder.iterdir()), [])
        with zipfile.ZipFile(result) as bundle:
            self.assertEqual(
                sorted(bundle.namelist()),
                [".hidden", "a.bin", "sub/b.bin"])
            self.assertEqual(bundle.read("sub/b.bin"), b"b")

    def test_empty(self):
        self.assertIsNone(archive.archive_folder(self.folder))

    def test_collision(self):
        (self.folder / "a.bin").write_bytes(b"a")
        self.dir.joinpath("parts_20260101-000000.zip").write_bytes(b"old")
        with mock.patch.object(archive, "_stamp",
                               return_value="20260101-000000"):
            result = archive.archive_folder(self.folder, prefix="parts")
        self.assertEqual(
            result, self.dir / "parts_20260101-000000-1.zip")

    def test_keep_files(self):
        (self.folder / "a.bin").write_bytes(b"a")
        with mock.patch.object(archive, "_stamp",
                               return_value="20260101-000000"):
            result = archive.archive_folder(
                self.folder, prefix="parts", remove=False)
        self.assertTrue(result.is_file())
        self.assertTrue((self.folder / "a.bin").is_file())

    def test_missing_folder(self):
        self.assertIsNone(archive.archive_folder(self.dir / "nope"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
