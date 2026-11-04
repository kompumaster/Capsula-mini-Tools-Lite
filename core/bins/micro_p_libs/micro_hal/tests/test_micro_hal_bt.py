#!/usr/bin/env python3
"""Тесты micro_hal: Bluetooth без платы (gdbus/pactl подменяются)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, hal_bt  # noqa: E402

ADAPTER_TEXT = """node /org/bluez/hci0 {
  interface org.bluez.Adapter1 {
    methods:
      StartDiscovery();
    properties:
      readonly s Address = '11:22:33:44:55:66';
      readonly s Name = 'BlueZ 5.65';
      readwrite s Alias = 'Capsula Mini';
      readwrite b Powered = true;
      readwrite b Discoverable = true;
      readwrite b Pairable = true;
      readonly b Discovering = false;
      readonly as UUIDs = ['0000110b-0000-1000-8000-00805f9b34fb', '0000110c-0000-1000-8000-00805f9b34fb'];
  };
};
"""

DEVICES_TEXT = """node /org/bluez/hci0 {
  interface org.bluez.Adapter1 {
    properties:
      readwrite s Alias = 'Capsula Mini';
  };
  node /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF {
    interface org.bluez.Device1 {
      properties:
        readonly s Address = 'AA:BB:CC:DD:EE:FF';
        readonly s Name = 'T1000';
        readwrite s Alias = 'T1000';
        readonly b Paired = true;
        readwrite b Trusted = true;
        readonly b Connected = true;
    };
  };
  node /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/player0 {
    interface org.bluez.MediaPlayer1 {
      properties:
        readonly s Name = 'Telephone';
    };
  };
  node /org/bluez/hci0/dev_77_88_99_AA_BB_CC {
    interface org.bluez.Device1 {
      properties:
        readonly s Address = '77:88:99:AA:BB:CC';
        readonly s Name = 'P0C0';
        readonly b Paired = true;
        readwrite b Trusted = false;
        readonly b Connected = false;
    };
  };
};
"""

MODULES_TEXT = (
    "15\tmodule-bluez5-discover\t\t\n"
    "17\tmodule-loopback\tsource=bluez_source.30_50_CE_0F_0C_7B.a2dp_source "
    "sink=master latency_msec=200\t\n"
    "4\tmodule-virtual-sink\tsink_name=master master=alsa_playback\t\n"
)

SOURCES_TEXT = (
    "11\tbluez_source.30_50_CE_0F_0C_7B.a2dp_source\t"
    "module-bluez5-device.c\ts16le 2ch 44100Hz\tSUSPENDED\n"
    "8\tmics\tmodule-alsa-source.c\ts16le 4ch 16000Hz\tSUSPENDED\n"
)

INPUTS_TEXT = """Sink Input #57
\tDriver: module-loopback.c
\tOwner Module: 17
\tClient: n/a
\tSink: 4
\tMute: no
\tVolume: front-left: 32768 /  50% / -18.06 dB,   front-right: 32768 /  50% / -18.06 dB
"""


class Adapter(unittest.TestCase):
    def test_adapter(self):
        with mock.patch.object(hal_bt, "_introspect",
                               return_value=ADAPTER_TEXT):
            values = hal_bt.adapter()
        self.assertEqual(values["address"], "11:22:33:44:55:66")
        self.assertEqual(values["alias"], "Capsula Mini")
        self.assertTrue(values["powered"])
        self.assertTrue(values["discoverable"])
        self.assertTrue(values["pairable"])
        self.assertFalse(values["discovering"])
        self.assertIn("0000110b-0000-1000-8000-00805f9b34fb", values["uuids"])

    def test_no_pbap(self):
        with mock.patch.object(hal_bt, "_introspect",
                               return_value=ADAPTER_TEXT):
            values = hal_bt.adapter()
        self.assertFalse(any(uuid.startswith("00001130")
                             for uuid in values["uuids"]))

    def test_available(self):
        with mock.patch.object(hal_bt.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_bt, "_introspect",
                                  return_value=ADAPTER_TEXT):
            self.assertTrue(hal_bt.available())
        with mock.patch.object(hal_bt.hal_common, "exists",
                               return_value=False):
            self.assertFalse(hal_bt.available())


class Setters(unittest.TestCase):
    def call(self, function, *args):
        with mock.patch.object(hal_bt, "_gdbus") as gdbus:
            function(*args)
        return gdbus.call_args[0]

    def test_power(self):
        self.assertEqual(self.call(hal_bt.power, True)[4], "<true>")
        self.assertEqual(self.call(hal_bt.power, False)[4], "<false>")

    def test_discoverable(self):
        path, method, iface, name, variant = self.call(hal_bt.discoverable,
                                                       True)
        self.assertEqual(path, hal_bt.ADAPTER)
        self.assertEqual(method, "org.freedesktop.DBus.Properties.Set")
        self.assertEqual(iface, "org.bluez.Adapter1")
        self.assertEqual(name, "Discoverable")
        self.assertEqual(variant, "<true>")

    def test_pairable(self):
        self.assertEqual(self.call(hal_bt.pairable, False)[4], "<false>")

    def test_alias(self):
        self.assertEqual(self.call(hal_bt.alias, "Capsula Mini")[4],
                         '<"Capsula Mini">')

    def test_alias_bad_chars(self):
        with self.assertRaises(HalError):
            hal_bt.alias('Capsula "Mini"')
        with self.assertRaises(HalError):
            hal_bt.alias("Capsula\\Mini")

    def test_trust(self):
        path, method, iface, name, variant = self.call(
            hal_bt.trust, "aa:bb:cc:dd:ee:ff", True)
        self.assertEqual(path, "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF")
        self.assertEqual(iface, "org.bluez.Device1")
        self.assertEqual(name, "Trusted")
        self.assertEqual(variant, "<true>")

    def test_forget(self):
        path, method, argument = self.call(
            hal_bt.forget, "aa:bb:cc:dd:ee:ff")[:3]
        self.assertEqual(path, hal_bt.ADAPTER)
        self.assertEqual(method, "org.bluez.Adapter1.RemoveDevice")
        self.assertEqual(argument,
                         "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF")

    def test_connect(self):
        path, method = self.call(hal_bt.connect, "aa:bb:cc:dd:ee:ff")[:2]
        self.assertEqual(path, "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF")
        self.assertEqual(method, "org.bluez.Device1.Connect")


class Devices(unittest.TestCase):
    def test_devices(self):
        with mock.patch.object(hal_bt, "_introspect",
                               return_value=DEVICES_TEXT):
            items = hal_bt.devices()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["address"], "AA:BB:CC:DD:EE:FF")
        self.assertTrue(items[0]["trusted"])
        self.assertTrue(items[0]["connected"])
        self.assertEqual(items[1]["name"], "P0C0")
        self.assertFalse(items[1]["connected"])

    def test_device(self):
        with mock.patch.object(hal_bt, "_introspect",
                               return_value=DEVICES_TEXT):
            item = hal_bt.device("aa:bb:cc:dd:ee:ff")
            self.assertEqual(item["alias"], "T1000")
            self.assertIsNone(hal_bt.device("00:00:00:00:00:00"))


class Pulse(unittest.TestCase):
    def test_sources(self):
        with mock.patch.object(hal_bt, "_pactl",
                               return_value=SOURCES_TEXT):
            self.assertEqual(
                hal_bt.sources(),
                ["bluez_source.30_50_CE_0F_0C_7B.a2dp_source"])

    def test_modules(self):
        with mock.patch.object(hal_bt, "_pactl",
                               return_value=MODULES_TEXT):
            self.assertEqual(hal_bt.bluez_module(), 15)
            self.assertEqual(hal_bt.loopback_module(), 17)

    def test_bluez_load(self):
        with mock.patch.object(hal_bt, "_pactl",
                               side_effect=["", "20"]) as pactl:
            self.assertEqual(hal_bt.bluez_load(), 20)
        self.assertIn("load-module", pactl.call_args[0][0])

    def test_bluez_load_existing(self):
        with mock.patch.object(hal_bt, "_pactl",
                               return_value=MODULES_TEXT) as pactl:
            self.assertEqual(hal_bt.bluez_load(), 15)
        self.assertEqual(pactl.call_count, 1)

    def test_bluez_unload(self):
        with mock.patch.object(hal_bt, "_pactl",
                               return_value=MODULES_TEXT) as pactl:
            self.assertTrue(hal_bt.bluez_unload())
        self.assertIn("unload-module 15", pactl.call_args[0][0])

    def test_bluez_unload_nothing(self):
        with mock.patch.object(hal_bt, "_pactl",
                               return_value="4\tmodule-virtual-sink\t\n"):
            self.assertFalse(hal_bt.bluez_unload())

    def test_loopback_add(self):
        with mock.patch.object(hal_bt, "_pactl",
                               return_value="18") as pactl, \
                mock.patch.object(
                    hal_bt, "sources",
                    return_value=["bluez_source.30_50_CE_0F_0C_7B.a2dp_source"]):
            self.assertEqual(hal_bt.loopback_add(), 18)
        command = pactl.call_args[0][0]
        self.assertIn("source=bluez_source.30_50_CE_0F_0C_7B.a2dp_source",
                      command)
        self.assertIn("sink=master", command)
        self.assertIn("latency_msec=200", command)

    def test_loopback_add_no_source(self):
        with mock.patch.object(hal_bt, "_pactl", return_value=""), \
                mock.patch.object(hal_bt, "sources", return_value=[]):
            with self.assertRaises(HalError):
                hal_bt.loopback_add()

    def test_loopback_remove(self):
        with mock.patch.object(hal_bt, "_pactl",
                               return_value=MODULES_TEXT) as pactl:
            self.assertTrue(hal_bt.loopback_remove())
        self.assertIn("unload-module 17", pactl.call_args[0][0])


class Input(unittest.TestCase):
    def test_input(self):
        with mock.patch.object(hal_bt, "_pactl",
                               side_effect=[MODULES_TEXT, INPUTS_TEXT]):
            self.assertEqual(hal_bt.loopback_input(), 57)

    def test_volume(self):
        with mock.patch.object(hal_bt, "_pactl",
                               side_effect=[MODULES_TEXT, INPUTS_TEXT,
                                            INPUTS_TEXT]):
            self.assertEqual(hal_bt.input_volume(), 50)

    def test_set_volume(self):
        with mock.patch.object(hal_bt, "_pactl",
                               side_effect=[MODULES_TEXT, INPUTS_TEXT,
                                            "ok"]) as pactl:
            self.assertEqual(hal_bt.set_input_volume(30), 30)
        self.assertIn("set-sink-input-volume 57 30%", pactl.call_args[0][0])

    def test_set_volume_bad(self):
        with self.assertRaises(HalError):
            hal_bt.set_input_volume(120)

    def test_mute(self):
        with mock.patch.object(hal_bt, "_pactl",
                               side_effect=[MODULES_TEXT, INPUTS_TEXT,
                                            "ok"]) as pactl:
            self.assertTrue(hal_bt.mute_input(True))
        self.assertIn("set-sink-input-mute 57 1", pactl.call_args[0][0])

    def test_mute_without_loopback(self):
        with mock.patch.object(hal_bt, "_pactl",
                               return_value="4\tmodule-virtual-sink\t\n"):
            with self.assertRaises(HalError):
                hal_bt.mute_input(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
