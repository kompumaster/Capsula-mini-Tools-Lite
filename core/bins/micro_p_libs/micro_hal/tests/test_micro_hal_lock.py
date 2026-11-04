#!/usr/bin/env python3
"""Тесты micro_hal: замки на ресурсы без платы."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, hal_common  # noqa: E402

LOCKS = REPO / "_tmp" / "locks"


class Locks(unittest.TestCase):
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
        patch = mock.patch.object(hal_common, "LOCK_DIR", str(LOCKS))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(hal_common._LOCKS.clear)

    def path(self, name):
        return LOCKS / "micro_hal_{}.lock".format(name)

    def make(self, name, pid):
        path = self.path(name)
        path.mkdir()
        (path / "pid").write_text(str(pid))
        return path

    def test_acquire_release(self):
        lock = hal_common.lock("display")
        self.assertTrue(self.path("display").is_dir())
        self.assertEqual((self.path("display") / "pid").read_text(),
                         str(os.getpid()))
        self.assertTrue(lock.release())
        self.assertFalse(self.path("display").exists())

    def test_busy(self):
        self.make("display", 4242)
        with mock.patch.object(hal_common, "_pid_alive",
                               return_value=True):
            with self.assertRaises(HalError) as context:
                hal_common.lock("display")
        self.assertIn("занят", str(context.exception))
        self.assertIn("4242", str(context.exception))

    def test_timeout(self):
        self.make("odas", 4242)
        with mock.patch.object(hal_common, "_pid_alive",
                               return_value=True), \
                mock.patch.object(hal_common.time, "sleep") as sleep:
            with self.assertRaises(HalError):
                hal_common.lock("odas", timeout=0.1)
        self.assertTrue(sleep.called)

    def test_stale_taken(self):
        self.make("odas", 999999)
        lock = hal_common.lock("odas")
        self.assertEqual((self.path("odas") / "pid").read_text(),
                         str(os.getpid()))
        lock.release()

    def test_junk_file_taken(self):
        self.path("display").write_text("мусор")
        lock = hal_common.lock("display")
        self.assertTrue(self.path("display").is_dir())
        lock.release()

    def test_empty_old_taken(self):
        self.path("keys").mkdir()
        with mock.patch.object(hal_common, "_lock_age", return_value=99.0):
            lock = hal_common.lock("keys")
        self.assertTrue(self.path("keys").is_dir())
        lock.release()

    def test_empty_fresh_busy(self):
        self.path("keys").mkdir()
        with mock.patch.object(hal_common, "_lock_age", return_value=1.0):
            self.assertTrue(hal_common.locked("keys"))
            with self.assertRaises(HalError) as context:
                hal_common.lock("keys")
        self.assertIn("занят", str(context.exception))

    def test_empty_old_free(self):
        self.path("keys").mkdir()
        with mock.patch.object(hal_common, "_lock_age", return_value=99.0):
            self.assertFalse(hal_common.locked("keys"))
            lock = hal_common.lock("keys")
        lock.release()

    def test_reentrant(self):
        first = hal_common.lock("ring")
        second = hal_common.lock("ring")
        self.assertNotEqual(first, second)
        first.release()
        self.assertTrue(self.path("ring").is_dir())
        second.release()
        self.assertFalse(self.path("ring").exists())

    def test_locked(self):
        self.assertFalse(hal_common.locked("keys"))
        lock = hal_common.lock("keys")
        self.assertTrue(hal_common.locked("keys"))
        lock.release()
        self.assertFalse(hal_common.locked("keys"))

    def test_stale_not_locked(self):
        self.make("keys", 999999)
        self.assertFalse(hal_common.locked("keys"))

    def test_context(self):
        with hal_common.lock("mic") as lock:
            self.assertTrue(hal_common.locked("mic"))
        self.assertFalse(hal_common.locked("mic"))
        self.assertFalse(lock.release())

    def test_release_foreign(self):
        lock = hal_common.lock("display")
        self.make("display2", 999999)
        path = self.path("display")
        (path / "pid").write_text("999999")
        lock.release()
        self.assertTrue(path.is_dir())

    def test_bad_name(self):
        for name in ("", "a b", "a/b", "a.b"):
            with self.assertRaises(HalError):
                hal_common.lock(name)

    def test_mkdir_error(self):
        with mock.patch.object(hal_common.os, "mkdir",
                               side_effect=OSError("нет каталога")):
            with self.assertRaises(HalError) as context:
                hal_common.lock("keys")
        self.assertIn("не создать", str(context.exception))

    def test_double_release(self):
        lock = hal_common.lock("display")
        self.assertTrue(lock.release())
        self.assertFalse(lock.release())


if __name__ == "__main__":
    unittest.main(verbosity=2)
