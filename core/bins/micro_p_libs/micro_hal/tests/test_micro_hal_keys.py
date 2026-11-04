#!/usr/bin/env python3
"""Тесты hal_keys: поиск устройства и разбор input_event."""

from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import hal_common, hal_keys  # noqa: E402
from micro_hal.hal_common import HalError  # noqa: E402


def pack_event(sec=1, usec=2, kind=1, code=115, value=1):
    return struct.pack("<qqHHi", sec, usec, kind, code, value)


class FindDevice(unittest.TestCase):
    def test_find_csk05t(self):
        with mock.patch.object(
                hal_keys.os, "listdir",
                return_value=["event0", "event1", "mouse0"]), \
             mock.patch.object(
                hal_common, "read_text",
                side_effect=["csk05t\n", "aml_vkeypad\n"]):
            self.assertEqual(hal_keys.find_device(),
                             "/dev/input/event0")

    def test_fallback_event0(self):
        with mock.patch.object(hal_keys.os, "listdir",
                               return_value=[]), \
             mock.patch.object(hal_common, "exists",
                               return_value=True):
            self.assertEqual(hal_keys.find_device(),
                             hal_common.DEV_INPUT)

    def test_missing(self):
        with mock.patch.object(hal_keys.os, "listdir",
                               return_value=[]), \
             mock.patch.object(hal_common, "exists",
                               return_value=False):
            with self.assertRaises(HalError):
                hal_keys.find_device()

    def test_device_name(self):
        with mock.patch.object(hal_common, "read_text",
                               return_value="csk05t\n"):
            self.assertEqual(
                hal_keys.device_name("/dev/input/event0"), "csk05t")

    def test_device_name_missing(self):
        with mock.patch.object(hal_common, "read_text",
                               side_effect=OSError):
            self.assertEqual(
                hal_keys.device_name("/dev/input/event0"), "")


class Device(unittest.TestCase):
    def make(self, payload):
        path = TMP / "hal_keys_events.bin"
        path.write_bytes(payload)
        self.addCleanup(lambda: path.exists() and path.unlink())
        return path

    def open(self, path):
        patches = [
            mock.patch.object(hal_common, "require_root", lambda: None),
            mock.patch.object(hal_keys, "device_name",
                              lambda _path: "csk05t"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        device = hal_keys.KeysDevice(str(path))
        self.addCleanup(device.close)
        return device

    def test_constants(self):
        self.assertEqual(hal_keys.EVENT_SIZE, 24)
        self.assertEqual(hal_keys.EV_SYN, 0)
        self.assertEqual(hal_keys.EV_KEY, 1)

    def test_poll_and_read(self):
        payload = pack_event(1, 2, 1, 115, 1) + \
            pack_event(3, 4, 1, 115, 0)
        device = self.open(self.make(payload))
        self.assertEqual(device.name, "csk05t")
        self.assertEqual(device.poll(0),
                         [(1, 2, 1, 115, 1)])
        self.assertEqual(device.read(), (3, 4, 1, 115, 0))
        self.assertIsNone(device.read())

    def test_empty(self):
        device = self.open(self.make(b""))
        self.assertEqual(device.poll(0), [])
        self.assertIsNone(device.read())

    def test_short(self):
        device = self.open(self.make(b"\x01\x02"))
        with self.assertRaises(HalError):
            device.poll(0)

    def test_closed(self):
        device = self.open(self.make(pack_event()))
        device.close()
        with self.assertRaises(HalError):
            device.poll(0)
        device.close()

    def test_two_devices_refcount(self):
        path = self.make(pack_event())
        locks = TMP / "keys_locks"
        locks.mkdir(exist_ok=True)
        hal_common._LOCKS.clear()
        self.addCleanup(hal_common._LOCKS.clear)
        with mock.patch.object(hal_common, "LOCK_DIR", str(locks)), \
                mock.patch.object(hal_common, "require_root", lambda: None), \
                mock.patch.object(hal_keys, "device_name",
                                  lambda _path: "csk05t"):
            first = hal_keys.KeysDevice(str(path))
            second = hal_keys.KeysDevice(str(path))
            first.close()
            self.assertTrue(hal_common.locked("keys"))
            second.close()
            self.assertFalse(hal_common.locked("keys"))

    def test_context(self):
        payload = pack_event(5, 6, 1, 164, 1)
        path = self.make(payload)
        with mock.patch.object(hal_common, "require_root",
                               lambda: None), \
             mock.patch.object(hal_keys, "device_name",
                               lambda _path: "csk05t"):
            with hal_keys.KeysDevice(str(path)) as device:
                self.assertEqual(device.read(), (5, 6, 1, 164, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
