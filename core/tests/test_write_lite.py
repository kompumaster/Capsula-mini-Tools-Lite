#!/usr/bin/env python3
"""Тесты `write_lite`: проверка имени тома и запись."""

from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import write_lite  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)


class FakeTransport:
    def __init__(self, image: Path):
        self.digest = hashlib.sha256(image.read_bytes()).hexdigest()
        self.closed = False
        self.written = None

    def write_partition(self, part, size, image, progress):
        self.written = (part, size, Path(image))
        progress(size, size)

    def read_hash(self, part, size, progress):
        progress(size, size)
        return self.digest, size

    def close(self):
        self.closed = True


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)
        self.image = self.dir / "system_b.bin"
        self.image.write_bytes(b"\x5a" * write_lite.PEB)
        self.transport = FakeTransport(self.image)

    def tearDown(self):
        self._tmp.cleanup()

    def run_main(self, *extra, params=None, answer="нет"):
        params = params or {"vol_name": "rootfs"}
        with mock.patch.object(write_lite, "read_ubi_params",
                               return_value=params) as read, \
             mock.patch.object(write_lite, "check_ubi",
                               return_value=5) as check, \
             mock.patch.object(write_lite.Transport, "wait",
                               return_value=self.transport) as wait, \
             mock.patch("builtins.input", return_value=answer) as ask, \
             redirect_stdout(io.StringIO()), \
             redirect_stderr(io.StringIO()) as err:
            code = write_lite.main([
                "--part", "system_b",
                "--file", str(self.image),
                "--no-confirm",
                "--no-check-size",
                *extra,
            ])
        return code, err.getvalue(), read, check, wait, ask


class Volume(Base):
    def test_ok(self):
        code, _err, read, check, wait, ask = self.run_main()
        self.assertEqual(code, 0)
        ask.assert_not_called()
        read.assert_called_once()
        check.assert_called_once()
        self.assertIs(check.call_args.args[1], read.return_value)
        wait.assert_called_once()
        self.assertTrue(self.transport.closed)

    def test_mismatch_cancel(self):
        code, err, read, check, wait, ask = self.run_main(
            params={"vol_name": "data"}, answer="нет")
        self.assertEqual(code, 1)
        self.assertIn("ОБРАЗ НЕ СООТВЕТСТВУЕТ", err)
        ask.assert_called_once()
        read.assert_called_once()
        check.assert_not_called()
        wait.assert_not_called()
        self.assertFalse(self.transport.closed)

    def test_mismatch_accept(self):
        code, _err, _read, check, wait, ask = self.run_main(
            params={"vol_name": "data"}, answer="да")
        self.assertEqual(code, 0)
        ask.assert_called_once()
        check.assert_called_once()
        wait.assert_called_once()
        self.assertTrue(self.transport.closed)

    def test_no_check_ubi(self):
        code, _err, read, check, wait, _ask = self.run_main("--no-check-ubi")
        self.assertEqual(code, 0)
        read.assert_not_called()
        check.assert_not_called()
        wait.assert_called_once()

    def test_eof_cancels(self):
        with mock.patch.object(write_lite, "read_ubi_params",
                               return_value={"vol_name": "data"}), \
             mock.patch.object(write_lite, "check_ubi") as check, \
             mock.patch.object(write_lite.Transport, "wait") as wait, \
             mock.patch("builtins.input", side_effect=EOFError), \
             redirect_stdout(io.StringIO()), \
             redirect_stderr(io.StringIO()):
            code = write_lite.main([
                "--part", "system_b",
                "--file", str(self.image),
                "--no-confirm",
                "--no-check-size",
            ])
        self.assertEqual(code, 1)
        check.assert_not_called()
        wait.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
