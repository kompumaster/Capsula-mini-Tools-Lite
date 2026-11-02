#!/usr/bin/env python3
"""Тесты `backup_lite`: staging `parts_bad` и атомарная замена."""

from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import unittest
import zipfile
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup_lite  # noqa: E402
from fw_io.transport import UsbError  # noqa: E402

DATA = b"\x5a" * 4096


class FakeTransport:
    def __init__(self, error=None):
        self.error = error

    def read_partition(self, part, size, out, progress, force=False):
        if self.error is not None:
            raise self.error
        out.write_bytes(DATA)
        progress(len(DATA), size)
        return hashlib.sha256(DATA).hexdigest()

    def read_hash(self, part, size, progress):
        progress(size, size)
        return hashlib.sha256(DATA).hexdigest(), size

    def close(self):
        pass


class Backup(unittest.TestCase):
    def run_main(self, transport, directory, archive=None, wait_error=None):
        root = Path(directory)
        backup = root / "parts"
        staging = root / "parts_bad"
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(backup_lite, "BACKUP", backup))
            stack.enter_context(
                mock.patch.object(backup_lite, "STAGING", staging))
            stack.enter_context(
                mock.patch.object(backup_lite, "PARTS", ["system_a"]))
            stack.enter_context(
                mock.patch.object(backup_lite, "size_for",
                                  lambda part: len(DATA)))
            if wait_error is not None:
                stack.enter_context(mock.patch.object(
                    backup_lite.Transport, "wait",
                    side_effect=wait_error))
            else:
                stack.enter_context(mock.patch.object(
                    backup_lite.Transport, "wait",
                    return_value=transport))
            if archive is not None:
                stack.enter_context(mock.patch.object(
                    backup_lite, "archive_folder", archive))
            stack.enter_context(redirect_stdout(io.StringIO()))
            err = stack.enter_context(redirect_stderr(io.StringIO()))
            code = backup_lite.main(["--no-check-ubi"])
        return code, err.getvalue(), backup, staging

    def test_success_renames_bad_to_bin(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _err, backup, staging = self.run_main(
                FakeTransport(), directory)
            files = sorted(p.name for p in backup.iterdir())
            staging_exists = staging.exists()
        self.assertEqual(code, 0)
        self.assertEqual(files, ["system_a.bin"])
        self.assertFalse(staging_exists)

    def test_success_archives_old_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "parts"
            old.mkdir()
            (old / "old.bin").write_bytes(b"old")
            (old / "status.txt").write_text("old")
            code, _err, backup, _staging = self.run_main(
                FakeTransport(), directory)
            files = sorted(p.name for p in backup.iterdir())
            archives = list(root.glob("parts_*.zip"))
            names = []
            if archives:
                with zipfile.ZipFile(archives[0]) as bundle:
                    names = bundle.namelist()
        self.assertEqual(code, 0)
        self.assertEqual(files, ["system_a.bin"])
        self.assertEqual(len(archives), 1)
        self.assertIn("old.bin", names)
        self.assertIn("status.txt", names)

    def test_read_failure_keeps_old_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "parts"
            old.mkdir()
            (old / "old.bin").write_bytes(b"old")
            code, err, backup, staging = self.run_main(
                FakeTransport(UsbError("timeout")), directory)
            old_exists = (backup / "old.bin").exists()
            staging_exists = staging.exists()
        self.assertEqual(code, 1)
        self.assertIn("Неудачное чтение", err)
        self.assertIn("Отключите колонку", err)
        self.assertTrue(old_exists)
        self.assertFalse(staging_exists)

    def test_failure_removes_partial_bad(self):
        class Partial(FakeTransport):
            def read_partition(self, part, size, out, progress, force=False):
                out.write_bytes(DATA[:100])
                raise UsbError("обрыв")

        with tempfile.TemporaryDirectory() as directory:
            code, _err, backup, staging = self.run_main(
                Partial(), directory)
            backup_exists = backup.exists()
            staging_exists = staging.exists()
        self.assertEqual(code, 1)
        self.assertFalse(backup_exists)
        self.assertFalse(staging_exists)

    def test_stale_staging_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "parts_bad"
            staging.mkdir()
            (staging / "stale.bin").write_bytes(b"stale")
            code, _err, backup, _staging = self.run_main(
                FakeTransport(), directory)
            stale = (backup / "stale.bin").exists()
        self.assertEqual(code, 0)
        self.assertFalse(stale)

    def test_wait_failure_keeps_old_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "parts"
            old.mkdir()
            (old / "old.bin").write_bytes(b"old")
            code, _err, backup, staging = self.run_main(
                None, directory, wait_error=UsbError("нет устройства"))
            old_exists = (backup / "old.bin").exists()
            staging_exists = staging.exists()
        self.assertEqual(code, 1)
        self.assertTrue(old_exists)
        self.assertFalse(staging_exists)

    def test_archive_failure_keeps_both(self):
        def fail_archive(*args, **kwargs):
            raise OSError("нет места")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "parts"
            old.mkdir()
            (old / "old.bin").write_bytes(b"old")
            code, err, backup, staging = self.run_main(
                FakeTransport(), directory, archive=fail_archive)
            old_exists = (backup / "old.bin").exists()
            new_exists = (staging / "system_a.bin").exists()
        self.assertEqual(code, 1)
        self.assertIn("не удалось заменить", err)
        self.assertTrue(old_exists)
        self.assertTrue(new_exists)


if __name__ == "__main__":
    unittest.main(verbosity=2)
