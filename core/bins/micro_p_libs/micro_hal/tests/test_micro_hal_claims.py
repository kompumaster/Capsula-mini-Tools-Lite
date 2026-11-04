#!/usr/bin/env python3
"""Тесты micro_hal: замки ресурсов в hal_* без платы."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import (  # noqa: E402
    HalError, hal_common, hal_display, hal_keys, hal_mic, hal_odas, hal_ring,
)

LOCKS = REPO / "_tmp" / "claims"


class Base(unittest.TestCase):
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
        hal_mic._lock = None
        hal_odas._lock = None
        hal_display._lock = None
        hal_display._c = None
        patch = mock.patch.object(hal_common, "LOCK_DIR", str(LOCKS))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(hal_common._LOCKS.clear)

    def foreign(self, name):
        path = LOCKS / "micro_hal_{}.lock".format(name)
        path.mkdir()
        (path / "pid").write_text("999999")

    def busy(self):
        return mock.patch.object(hal_common, "_pid_alive", return_value=True)

    def assert_free(self, name):
        """Ресурс свободен и его можно снова взять."""
        self.assertFalse(hal_common.locked(name))
        lock = hal_common.lock(name)
        lock.release()


class Mic(Base):
    def test_busy(self):
        self.foreign("mic")
        with self.busy(), \
                mock.patch.object(hal_mic.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_mic, "sources",
                                  return_value=["mics"]), \
                mock.patch.object(hal_mic, "running", return_value=None):
            with self.assertRaises(HalError) as context:
                hal_mic.start("/tmp/a.raw")
        self.assertIn("mic", str(context.exception))

    def test_release_on_stop(self):
        with mock.patch.object(hal_mic.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_mic, "sources",
                                  return_value=["mics"]), \
                mock.patch.object(hal_mic, "running",
                                  side_effect=[None, 123, 123]), \
                mock.patch.object(hal_mic.hal_common, "run"):
            hal_mic.start("/tmp/a.raw")
        self.assertTrue(hal_common.locked("mic"))
        with mock.patch.object(hal_mic, "running", return_value=123), \
                mock.patch.object(hal_mic, "_alive", return_value=False):
            self.assertTrue(hal_mic.stop())
        self.assertFalse(hal_common.locked("mic"))
        self.assertIsNone(hal_mic._lock)


class Odas(Base):
    def test_busy(self):
        self.foreign("odas")
        with self.busy(), \
                mock.patch.object(hal_odas.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_odas, "available", return_value=True), \
                mock.patch.object(hal_odas, "running", return_value=None):
            with self.assertRaises(HalError) as context:
                hal_odas.start()
        self.assertIn("odas", str(context.exception))

    def test_release_on_stop(self):
        with mock.patch.object(hal_odas.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_odas, "available", return_value=True), \
                mock.patch.object(hal_odas, "_is_exec", return_value=True), \
                mock.patch.object(hal_odas.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_odas, "running",
                                  side_effect=[None, 321, 321]), \
                mock.patch.object(hal_odas.hal_common, "run"), \
                mock.patch.object(hal_odas.hal_common, "write_text"), \
                mock.patch.object(hal_odas.time, "sleep"):
            self.assertEqual(hal_odas.start(), 321)
        self.assertTrue(hal_common.locked("odas"))
        with mock.patch.object(hal_odas, "running", return_value=321), \
                mock.patch.object(hal_odas, "_alive", return_value=False):
            self.assertTrue(hal_odas.stop())
        self.assertFalse(hal_common.locked("odas"))


class Devices(Base):
    def test_ring_busy(self):
        self.foreign("ring")
        with self.busy(), \
                mock.patch.object(hal_ring.hal_common, "require_root"), \
                mock.patch.object(hal_ring.hal_common,
                                  "require_va_stopped"):
            with self.assertRaises(HalError):
                hal_ring.Ring()

    def test_keys_busy(self):
        self.foreign("keys")
        with self.busy(), \
                mock.patch.object(hal_keys.hal_common, "require_root"):
            with self.assertRaises(HalError):
                hal_keys.KeysDevice()

    def test_display_busy(self):
        self.foreign("display")
        with self.busy():
            with self.assertRaises(HalError):
                hal_display._open_c()

    def test_display_forget_releases(self):
        with mock.patch.object(hal_display, "_open_c") as open_c, \
                mock.patch.object(hal_display, "_close_c"):
            hal_display._lock = hal_common.lock("display")
            open_c.return_value = None
            hal_display.forget()
        self.assertFalse(hal_common.locked("display"))


class InitErrors(Base):
    """Ошибка инициализации не должна оставлять замок."""

    class BadFfi:
        @staticmethod
        def open(path):
            raise OSError("нет библиотеки")

    def test_ring_error_releases(self):
        with mock.patch.dict(sys.modules, {"ffi": self.BadFfi}), \
                mock.patch.object(hal_ring.hal_common, "require_root"), \
                mock.patch.object(hal_ring.hal_common,
                                  "require_va_stopped"):
            with self.assertRaises(HalError):
                hal_ring.Ring()
        self.assert_free("ring")

    def test_keys_error_releases(self):
        with mock.patch.object(hal_keys.hal_common, "require_root"), \
                mock.patch.object(hal_keys, "find_device",
                                  side_effect=HalError("нет устройства")):
            with self.assertRaises(HalError):
                hal_keys.KeysDevice()
        self.assert_free("keys")

    def test_display_error_releases(self):
        with mock.patch.dict(sys.modules, {"ffi": self.BadFfi}):
            with self.assertRaises(HalError):
                hal_display._open_c()
        self.assert_free("display")

    def test_odas_missing_binary_no_lock(self):
        with mock.patch.object(hal_odas.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_odas, "running", return_value=None), \
                mock.patch.object(hal_odas, "_is_exec", return_value=False):
            with self.assertRaises(HalError):
                hal_odas.start()
        self.assert_free("odas")

    def test_odas_started_error_releases(self):
        with mock.patch.object(hal_odas.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_odas, "running", return_value=None), \
                mock.patch.object(hal_odas, "_is_exec", return_value=True), \
                mock.patch.object(hal_odas.hal_common, "exists",
                                  return_value=True), \
                mock.patch.object(hal_odas.hal_common, "write_text",
                                  side_effect=OSError("нет места")):
            with self.assertRaises(OSError):
                hal_odas.start()
        self.assert_free("odas")

    def test_mic_quote_error_no_lock(self):
        with mock.patch.object(hal_mic.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_mic, "sources",
                                  return_value=["mics"]), \
                mock.patch.object(hal_mic, "running", return_value=None):
            with self.assertRaises(HalError):
                hal_mic.start("/tmp/a'b.raw")
        self.assert_free("mic")

    def test_mic_run_error_releases(self):
        with mock.patch.object(hal_mic.hal_common, "require_va_stopped"), \
                mock.patch.object(hal_mic, "sources",
                                  return_value=["mics"]), \
                mock.patch.object(hal_mic, "running", return_value=None), \
                mock.patch.object(hal_mic.hal_common, "run",
                                  side_effect=OSError("нет shell")):
            with self.assertRaises(OSError):
                hal_mic.start("/tmp/a.raw")
        self.assert_free("mic")


if __name__ == "__main__":
    unittest.main(verbosity=2)
