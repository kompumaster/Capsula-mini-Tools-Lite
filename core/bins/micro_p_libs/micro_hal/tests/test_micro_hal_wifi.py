#!/usr/bin/env python3
"""Тесты micro_hal: Wi-Fi (wpa_cli) без платы."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, hal_wifi  # noqa: E402

STATUS = """bssid=aa:bb:cc:dd:ee:ff
freq=5180
ssid=HOME
id=0
mode=station
wifi_generation=5
pairwise_cipher=CCMP
key_mgmt=WPA2-PSK
wpa_state=COMPLETED
ip_address=192.0.2.10
address=AA:BB:CC:DD:EE:FF
"""

NETWORKS = """network id / ssid / bssid / flags
0\tHOME\tany\t[CURRENT]
1\tTEST\tany\t
"""

SCAN = """bssid / frequency / signal level / flags / ssid
aa:bb:cc:dd:ee:ff\t5180\t-46\t[WPA2-PSK-CCMP][ESS]\tHOME
11:22:33:44:55:66\t2412\t-70\t[WPA2-PSK-CCMP][ESS]\tHOME
"""

IP = """3: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
    inet 192.0.2.10/24 brd 192.0.2.255 scope global dynamic wlan0
       valid_lft 42726sec preferred_lft 37326sec
"""


class FakeWpa:
    """Подмена `_wpa`: записывает команды и отдаёт заготовки."""

    def __init__(self, replies=None):
        self.calls = []
        self.replies = replies or {}

    def __call__(self, *args):
        self.calls.append(args)
        key = args[0]
        if key in self.replies:
            value = self.replies[key]
            return value(*args) if callable(value) else value
        return "OK\n"


class Parsing(unittest.TestCase):
    def test_status(self):
        with mock.patch.object(hal_wifi, "_wpa", return_value=STATUS):
            values = hal_wifi.status()
        self.assertEqual(values["ssid"], "HOME")
        self.assertEqual(values["id"], 0)
        self.assertEqual(values["freq"], 5180)
        self.assertEqual(values["state"], "COMPLETED")
        self.assertEqual(values["ip_address"], "192.0.2.10")

    def test_networks(self):
        with mock.patch.object(hal_wifi, "_wpa", return_value=NETWORKS):
            items = hal_wifi.networks()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["ssid"], "HOME")
        self.assertTrue(items[0]["current"])
        self.assertFalse(items[1]["current"])

    def test_saved(self):
        with mock.patch.object(hal_wifi, "_wpa", return_value=NETWORKS):
            self.assertEqual(hal_wifi.saved(), ["HOME", "TEST"])

    def test_scan_results(self):
        with mock.patch.object(hal_wifi, "_wpa", return_value=SCAN):
            items = hal_wifi.scan_results()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["ssid"], "HOME")
        self.assertEqual(items[0]["signal"], -46)
        self.assertEqual(items[1]["freq"], 2412)

    def test_scan(self):
        fake = FakeWpa({"scan": "OK\n", "scan_results": SCAN})
        with mock.patch.object(hal_wifi, "_wpa", fake), \
                mock.patch.object(hal_wifi.time, "sleep") as sleep:
            items = hal_wifi.scan()
        self.assertEqual(fake.calls[0], ("scan",))
        self.assertEqual(len(items), 2)
        sleep.assert_called_once_with(3.0)

    def test_scan_cached(self):
        fake = FakeWpa({"scan_results": SCAN})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            hal_wifi.scan(fresh=False)
        self.assertEqual(fake.calls, [("scan_results",)])

    def test_available(self):
        with mock.patch.object(hal_wifi.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_wifi, "_wpa", return_value=STATUS):
            self.assertTrue(hal_wifi.available())
        with mock.patch.object(hal_wifi.hal_common, "exists",
                               return_value=False):
            self.assertFalse(hal_wifi.available())

    def test_available_single_status(self):
        with mock.patch.object(hal_wifi.hal_common, "exists",
                               return_value=True), \
                mock.patch.object(hal_wifi, "_wpa",
                                  return_value=STATUS) as wpa:
            self.assertTrue(hal_wifi.available())
        self.assertEqual(wpa.call_count, 1)


class Commands(unittest.TestCase):
    def test_add_network(self):
        fake = FakeWpa({"add_network": "2\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            net_id = hal_wifi.add_network("HOME", "secret")
        self.assertEqual(net_id, 2)
        self.assertEqual(fake.calls[0], ("add_network",))
        self.assertIn(("set_network", "2", "ssid", '"HOME"'), fake.calls)
        self.assertIn(("set_network", "2", "psk", '"secret"'), fake.calls)
        self.assertIn(("set_network", "2", "key_mgmt", "WPA-PSK"),
                      fake.calls)

    def test_add_network_hex_psk(self):
        psk = "a" * 64
        fake = FakeWpa({"add_network": "3\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            hal_wifi.add_network("HOME", psk)
        self.assertIn(("set_network", "3", "psk", psk), fake.calls)

    def test_add_network_error_cleanup(self):
        fake = FakeWpa({"add_network": "4\n",
                        "set_network": "FAIL\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            with self.assertRaises(HalError):
                hal_wifi.add_network("HOME", "secret")
        self.assertIn(("remove_network", "4"), fake.calls)

    def test_add_network_bad_id(self):
        fake = FakeWpa({"add_network": "FAIL\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            with self.assertRaises(HalError):
                hal_wifi.add_network("HOME")

    def test_add_network_empty_ssid(self):
        with self.assertRaises(HalError):
            hal_wifi.add_network("")

    def test_add_network_open(self):
        fake = FakeWpa({"add_network": "5\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            net_id = hal_wifi.add_network("Cafe")
        self.assertEqual(net_id, 5)
        self.assertIn(("set_network", "5", "key_mgmt", "NONE"), fake.calls)
        self.assertFalse([call for call in fake.calls
                          if len(call) > 2 and call[2] == "psk"])

    def test_add_network_sae(self):
        fake = FakeWpa({"add_network": "6\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            hal_wifi.add_network("HOME", "secret", key_mgmt="SAE")
        self.assertIn(("set_network", "6", "psk", '"secret"'), fake.calls)
        self.assertIn(("set_network", "6", "key_mgmt", "SAE"), fake.calls)

    def test_add_network_open_ignores_psk(self):
        fake = FakeWpa({"add_network": "7\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            hal_wifi.add_network("Cafe", "лишний", key_mgmt="NONE")
        self.assertIn(("set_network", "7", "key_mgmt", "NONE"), fake.calls)
        self.assertFalse([call for call in fake.calls
                          if len(call) > 2 and call[2] == "psk"])

    def test_add_network_bad_key_mgmt(self):
        with self.assertRaises(HalError):
            hal_wifi.add_network("HOME", "secret", key_mgmt="WPA-EAP")

    def test_add_network_scan_ssid(self):
        fake = FakeWpa({"add_network": "8\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            hal_wifi.add_network("HOME", "secret", scan_ssid=True)
        self.assertIn(("set_network", "8", "scan_ssid", "1"), fake.calls)

    def test_add_network_no_scan_ssid(self):
        fake = FakeWpa({"add_network": "9\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            hal_wifi.add_network("HOME", "secret")
        self.assertFalse([call for call in fake.calls
                          if len(call) > 2 and call[2] == "scan_ssid"])

    def test_set_network(self):
        fake = FakeWpa()
        with mock.patch.object(hal_wifi, "_wpa", fake):
            hal_wifi.set_network(2, ssid="HOME", key_mgmt="WPA-PSK")
        self.assertEqual(fake.calls,
                         [("set_network", "2", "ssid", '"HOME"'),
                          ("set_network", "2", "key_mgmt", "WPA-PSK")])

    def test_set_network_empty(self):
        with self.assertRaises(HalError):
            hal_wifi.set_network(2)

    def test_select_remove_save(self):
        fake = FakeWpa()
        with mock.patch.object(hal_wifi, "_wpa", fake):
            hal_wifi.select_network(1)
            hal_wifi.remove_network(2)
            hal_wifi.save_config()
            hal_wifi.reconnect()
        self.assertEqual(fake.calls,
                         [("select_network", "1"),
                          ("remove_network", "2"),
                          ("save_config",),
                          ("reconnect",)])

    def test_fail(self):
        fake = FakeWpa({"select_network": "FAIL\n"})
        with mock.patch.object(hal_wifi, "_wpa", fake):
            with self.assertRaises(HalError):
                hal_wifi.select_network(1)

    def test_quote(self):
        self.assertEqual(hal_wifi._quote_value("HOME"), '"HOME"')
        with self.assertRaises(HalError):
            hal_wifi._quote_value('a"b')

    def test_shell_quoting(self):
        with mock.patch.object(hal_wifi.hal_common, "capture",
                               return_value=(0, "OK\n")) as capture:
            hal_wifi._wpa("set_network", "2", "ssid", '"HOME"')
        command = capture.call_args[0][0]
        self.assertIn("'set_network' '2' 'ssid' '\"HOME\"'", command)

    def test_shell_rejects_quote(self):
        with self.assertRaises(HalError):
            hal_wifi._shell("a'b")


class Wait(unittest.TestCase):
    def test_wait_state(self):
        fake = FakeWpa({"status": lambda *args: STATUS.replace(
            "COMPLETED", "SCANNING")})
        with mock.patch.object(hal_wifi, "_wpa", fake), \
                mock.patch.object(hal_wifi.time, "sleep"), \
                mock.patch.object(hal_wifi, "status",
                                  return_value={"state": "COMPLETED"}):
            self.assertTrue(hal_wifi.wait_state(timeout=1.0))

    def test_wait_timeout(self):
        with mock.patch.object(hal_wifi, "status",
                               return_value={"state": "SCANNING"}), \
                mock.patch.object(hal_wifi.time, "sleep"), \
                mock.patch.object(hal_wifi.time, "time",
                                  side_effect=[0.0, 0.5, 2.0]):
            self.assertFalse(hal_wifi.wait_state(timeout=1.0))

    def test_ip_address(self):
        with mock.patch.object(hal_wifi.hal_common, "capture",
                               return_value=(0, IP)):
            self.assertEqual(hal_wifi.ip_address(timeout=0), "192.0.2.10")

    def test_ip_address_timeout(self):
        with mock.patch.object(hal_wifi.hal_common, "capture",
                               return_value=(0, "нет адреса")), \
                mock.patch.object(hal_wifi.time, "sleep"), \
                mock.patch.object(hal_wifi.time, "time",
                                  side_effect=[0.0, 2.0]):
            self.assertIsNone(hal_wifi.ip_address(timeout=1.0))

    def test_dhcp_renew(self):
        with mock.patch.object(hal_wifi.hal_common, "capture",
                               return_value=(0, "")) as capture:
            self.assertTrue(hal_wifi.dhcp_renew())
        self.assertIn("dhcpcd -n wlan0", capture.call_args[0][0])

    def test_dhcp_renew_error(self):
        with mock.patch.object(hal_wifi.hal_common, "capture",
                               return_value=(1, "нет")):
            with self.assertRaises(HalError):
                hal_wifi.dhcp_renew()


if __name__ == "__main__":
    unittest.main(verbosity=2)
