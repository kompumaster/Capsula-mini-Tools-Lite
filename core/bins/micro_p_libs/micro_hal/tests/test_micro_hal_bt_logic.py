#!/usr/bin/env python3
"""Тесты micro_hal: политика Bluetooth без платы."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, lib_bt  # noqa: E402


class Enable(unittest.TestCase):
    def test_enable_order(self):
        calls = []

        def record(name):
            def function(*args, **kwargs):
                calls.append((name,) + args)
            return function

        with mock.patch.object(lib_bt.hal_bt, "power",
                               side_effect=record("power")), \
                mock.patch.object(lib_bt.hal_bt, "bluez_load",
                                  side_effect=record("bluez_load")), \
                mock.patch.object(lib_bt.hal_bt, "alias",
                                  side_effect=record("alias")), \
                mock.patch.object(lib_bt.hal_bt, "discoverable",
                                  side_effect=record("discoverable")), \
                mock.patch.object(lib_bt.hal_bt, "pairable",
                                  side_effect=record("pairable")), \
                mock.patch.object(lib_bt, "status",
                                  return_value={"enabled": True}) as status:
            result = lib_bt.enable("Capsula")
        self.assertEqual(result, {"enabled": True})
        status.assert_called_once_with()
        self.assertEqual([call[0] for call in calls],
                         ["power", "bluez_load", "alias", "discoverable",
                          "pairable"])
        self.assertEqual(calls[0][1], True)
        self.assertEqual(calls[2][1], "Capsula")
        self.assertEqual(calls[3][1], True)

    def test_disable_order(self):
        calls = []

        def record(name):
            def function(*args, **kwargs):
                calls.append((name,) + args)
            return function

        with mock.patch.object(lib_bt, "audio_stop",
                               side_effect=record("audio_stop")), \
                mock.patch.object(lib_bt.hal_bt, "discoverable",
                                  side_effect=record("discoverable")), \
                mock.patch.object(lib_bt.hal_bt, "pairable",
                                  side_effect=record("pairable")), \
                mock.patch.object(lib_bt.hal_bt, "power",
                                  side_effect=record("power")), \
                mock.patch.object(lib_bt.hal_bt, "bluez_unload",
                                  side_effect=record("bluez_unload")), \
                mock.patch.object(lib_bt, "status",
                                  return_value={"enabled": False}):
            lib_bt.disable()
        self.assertEqual([call[0] for call in calls],
                         ["audio_stop", "discoverable", "pairable",
                          "power", "bluez_unload"])
        self.assertEqual(calls[1][1], False)
        self.assertEqual(calls[3][1], False)


class State(unittest.TestCase):
    def test_enabled(self):
        with mock.patch.object(lib_bt.hal_bt, "adapter",
                               return_value={"powered": True}):
            self.assertTrue(lib_bt.enabled())
        with mock.patch.object(lib_bt.hal_bt, "adapter",
                               return_value={"powered": False}):
            self.assertFalse(lib_bt.enabled())

    def test_enabled_without_adapter(self):
        with mock.patch.object(lib_bt.hal_bt, "adapter",
                               side_effect=HalError("нет")):
            self.assertFalse(lib_bt.enabled())
            self.assertFalse(lib_bt.visible())

    def test_visible(self):
        with mock.patch.object(lib_bt.hal_bt, "adapter",
                               return_value={"discoverable": True,
                                             "pairable": True}):
            self.assertTrue(lib_bt.visible())
        with mock.patch.object(lib_bt.hal_bt, "adapter",
                               return_value={"discoverable": True,
                                             "pairable": False}):
            self.assertFalse(lib_bt.visible())

    def test_status(self):
        device = {"address": "AA:BB:CC:DD:EE:FF", "connected": True}
        with mock.patch.object(
                lib_bt.hal_bt, "adapter",
                return_value={"powered": True, "discoverable": True,
                              "pairable": True}), \
                mock.patch.object(lib_bt.hal_bt, "devices",
                                  return_value=[{"address": "X",
                                                 "connected": False},
                                                device]), \
                mock.patch.object(lib_bt.hal_bt, "sources",
                                  return_value=["bluez_source.A"]), \
                mock.patch.object(lib_bt.hal_bt, "loopback_module",
                                  return_value=18), \
                mock.patch.object(lib_bt.hal_bt, "input_volume",
                                  return_value=50), \
                mock.patch.object(lib_bt.hal_bt, "input_muted",
                                  return_value=False):
            values = lib_bt.status()
        self.assertTrue(values["enabled"])
        self.assertTrue(values["visible"])
        self.assertEqual(values["device"], device)
        self.assertEqual(values["source"], "bluez_source.A")
        self.assertTrue(values["audio"])
        self.assertEqual(values["volume"], 50)
        self.assertFalse(values["muted"])

    def test_status_without_adapter(self):
        with mock.patch.object(lib_bt.hal_bt, "adapter",
                               side_effect=HalError("нет")):
            values = lib_bt.status()
        self.assertFalse(values["enabled"])
        self.assertIsNone(values["device"])
        self.assertFalse(values["audio"])


class Device(unittest.TestCase):
    def test_devices(self):
        with mock.patch.object(lib_bt.hal_bt, "devices",
                               return_value=[{"address": "A"}]):
            self.assertEqual(lib_bt.devices(), [{"address": "A"}])

    def test_connect_trusts(self):
        with mock.patch.object(lib_bt.hal_bt, "trust") as trust, \
                mock.patch.object(lib_bt.hal_bt, "connect") as connect:
            self.assertEqual(lib_bt.connect("aa:bb:cc:dd:ee:ff"),
                             "AA:BB:CC:DD:EE:FF")
        trust.assert_called_once_with("aa:bb:cc:dd:ee:ff", True)
        connect.assert_called_once_with("aa:bb:cc:dd:ee:ff")

    def test_trust(self):
        with mock.patch.object(lib_bt.hal_bt, "trust",
                               return_value=True) as trust:
            self.assertTrue(lib_bt.trust("A", True))
        trust.assert_called_once_with("A", True)

    def test_trust_paired(self):
        devices = [{"address": "A", "paired": True, "trusted": False},
                   {"address": "B", "paired": True, "trusted": True},
                   {"address": "C", "paired": False, "trusted": False}]
        with mock.patch.object(lib_bt.hal_bt, "devices",
                               return_value=devices), \
                mock.patch.object(lib_bt.hal_bt, "trust") as trust:
            self.assertEqual(lib_bt.trust_paired(), 1)
        trust.assert_called_once_with("A", True)

    def test_forget(self):
        with mock.patch.object(lib_bt.hal_bt, "forget",
                               return_value="A") as forget:
            self.assertEqual(lib_bt.forget("A"), "A")
        forget.assert_called_once_with("A")

    def test_disconnect(self):
        with mock.patch.object(lib_bt.hal_bt, "disconnect",
                               return_value="A") as disconnect:
            self.assertEqual(lib_bt.disconnect("A"), "A")
        disconnect.assert_called_once_with("A")


class Audio(unittest.TestCase):
    def test_audio_start_without_source(self):
        with mock.patch.object(lib_bt.hal_bt, "loopback_module",
                               return_value=None), \
                mock.patch.object(lib_bt.hal_bt, "sources",
                                  return_value=[]), \
                mock.patch.object(lib_bt.hal_bt, "loopback_add") as add:
            self.assertFalse(lib_bt.audio_start())
        add.assert_not_called()

    def test_audio_start(self):
        with mock.patch.object(lib_bt.hal_bt, "loopback_module",
                               return_value=None), \
                mock.patch.object(lib_bt.hal_bt, "sources",
                                  return_value=["bluez_source.A"]), \
                mock.patch.object(lib_bt.hal_bt, "loopback_add") as add:
            self.assertTrue(lib_bt.audio_start())
        add.assert_called_once_with(latency_msec=200)

    def test_audio_start_already(self):
        with mock.patch.object(lib_bt.hal_bt, "loopback_module",
                               return_value=18), \
                mock.patch.object(lib_bt.hal_bt, "loopback_add") as add:
            self.assertTrue(lib_bt.audio_start())
        add.assert_not_called()

    def test_audio(self):
        with mock.patch.object(lib_bt.hal_bt, "loopback_module",
                               return_value=18):
            self.assertTrue(lib_bt.audio())
        with mock.patch.object(lib_bt.hal_bt, "loopback_module",
                               return_value=None):
            self.assertFalse(lib_bt.audio())

    def test_audio_stop(self):
        with mock.patch.object(lib_bt.hal_bt, "loopback_remove",
                               return_value=True) as remove:
            self.assertTrue(lib_bt.audio_stop())
        remove.assert_called_once_with()

    def test_mute_without_loopback(self):
        with mock.patch.object(lib_bt.hal_bt, "loopback_module",
                               return_value=None), \
                mock.patch.object(lib_bt.hal_bt, "mute_input") as mute:
            self.assertFalse(lib_bt.mute(True))
        mute.assert_not_called()

    def test_mute(self):
        with mock.patch.object(lib_bt.hal_bt, "loopback_module",
                               return_value=18), \
                mock.patch.object(lib_bt.hal_bt, "mute_input",
                                  return_value=True) as mute:
            self.assertTrue(lib_bt.mute(True))
        mute.assert_called_once_with(True)

    def test_muted(self):
        with mock.patch.object(lib_bt.hal_bt, "input_muted",
                               return_value=True):
            self.assertTrue(lib_bt.muted())

    def test_volume_get(self):
        with mock.patch.object(lib_bt.hal_bt, "input_volume",
                               return_value=40):
            self.assertEqual(lib_bt.volume(), 40)

    def test_volume_set(self):
        with mock.patch.object(lib_bt.hal_bt, "set_input_volume",
                               return_value=30) as setter:
            self.assertEqual(lib_bt.volume(30), 30)
        setter.assert_called_once_with(30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
