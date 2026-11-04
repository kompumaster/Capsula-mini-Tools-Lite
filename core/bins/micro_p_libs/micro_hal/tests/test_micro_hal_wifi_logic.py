#!/usr/bin/env python3
"""Тесты micro_hal: политика Wi-Fi и сторож без платы."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, lib_wifi  # noqa: E402

TMP = REPO / "_tmp" / "wifi"


class Guard(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        for path in TMP.iterdir():
            path.unlink()
        self.guard = str(TMP / "guard.sh")
        self.ok = str(TMP / "ok")
        self.log = str(TMP / "guard.log")
        self.state = str(TMP / "guard.state")
        for name, value in (("GUARD", self.guard), ("OK", self.ok),
                            ("GUARD_LOG", self.log),
                            ("GUARD_STATE", self.state)):
            patch = mock.patch.object(lib_wifi, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def test_script(self):
        text = lib_wifi._script_text()
        self.assertTrue(text.startswith("#!/bin/sh"))
        self.assertIn("remove_network", text)
        self.assertIn("select_network", text)
        self.assertIn("reconnect", text)
        self.assertIn("sleep", text)
        self.assertIn('token="$5"', text)
        self.assertIn(self.ok, text)
        self.assertIn(self.log, text)
        self.assertIn(self.state, text)

    def test_write(self):
        path = lib_wifi.guard_write()
        self.assertEqual(path, self.guard)
        self.assertTrue(Path(path).exists())
        self.assertTrue(Path(path).stat().st_mode & 0o100)

    def test_start(self):
        with mock.patch.object(lib_wifi.hal_common, "run") as run:
            command = lib_wifi.guard_start(5, 0, timeout=45, dry_run=True)
        self.assertIn("nohup /bin/sh", command)
        self.assertIn("5 0 45 1", command)
        run.assert_called_once_with(command)

    def test_start_live(self):
        with mock.patch.object(lib_wifi.hal_common, "run") as run:
            lib_wifi.guard_start(5, 0, timeout=45)
        self.assertIn("5 0 45 0", run.call_args[0][0])

    def test_start_token(self):
        with mock.patch.object(lib_wifi.hal_common, "run") as run:
            lib_wifi.guard_start(5, 0, timeout=45)
        token = Path(self.state).read_text()
        self.assertTrue(token)
        self.assertIn(" {} ".format(token), run.call_args[0][0])

    def test_ok(self):
        lib_wifi.guard_ok()
        self.assertTrue(Path(self.ok).exists())

    def test_log(self):
        Path(self.log).write_text("a\nb\nc\n")
        self.assertEqual(lib_wifi.guard_log(2), "b\nc")

    def test_log_empty(self):
        self.assertEqual(lib_wifi.guard_log(), "")


class Status(unittest.TestCase):
    def test_status(self):
        with mock.patch.object(
                lib_wifi.hal_wifi, "status",
                return_value={"ssid": "HOME", "state": "COMPLETED",
                              "bssid": "aa:bb", "freq": 5180, "id": 0}), \
                mock.patch.object(lib_wifi.hal_wifi, "ip_address",
                                  return_value="192.0.2.10"), \
                mock.patch.object(
                    lib_wifi.hal_wifi, "scan_results",
                    return_value=[{"bssid": "aa:bb", "signal": -46}]):
            values = lib_wifi.status()
        self.assertEqual(values["ssid"], "HOME")
        self.assertEqual(values["ip"], "192.0.2.10")
        self.assertEqual(values["signal"], -46)

    def test_status_without_signal(self):
        with mock.patch.object(
                lib_wifi.hal_wifi, "status",
                return_value={"ssid": "HOME", "bssid": "cc"}), \
                mock.patch.object(lib_wifi.hal_wifi, "ip_address",
                                  return_value=None), \
                mock.patch.object(lib_wifi.hal_wifi, "scan_results",
                                  return_value=[]):
            self.assertIsNone(lib_wifi.status()["signal"])

    def test_status_skips_ip_without_network(self):
        with mock.patch.object(
                lib_wifi.hal_wifi, "status",
                return_value={"ssid": "HOME", "state": "SCANNING"}), \
                mock.patch.object(lib_wifi.hal_wifi, "ip_address") as ip:
            values = lib_wifi.status()
        self.assertIsNone(values["ip"])
        ip.assert_not_called()


class Scan(unittest.TestCase):
    def test_dedupe_and_sort(self):
        items = [
            {"ssid": "A", "signal": -70},
            {"ssid": "B", "signal": -40},
            {"ssid": "A", "signal": -50},
            {"ssid": "", "signal": -30},
        ]
        with mock.patch.object(lib_wifi.hal_wifi, "scan_results",
                               return_value=items):
            result = lib_wifi.scan()
        self.assertEqual([item["ssid"] for item in result], ["B", "A"])
        self.assertEqual(result[1]["signal"], -50)

    def test_fresh(self):
        with mock.patch.object(lib_wifi.hal_wifi, "scan",
                               return_value=[]) as scan:
            lib_wifi.scan(fresh=True, wait=5.0)
        scan.assert_called_once_with(wait=5.0)


class Forget(unittest.TestCase):
    def test_current_refused(self):
        networks = [{"id": 0, "ssid": "HOME", "current": True}]
        with mock.patch.object(lib_wifi.hal_wifi, "networks",
                               return_value=networks):
            with self.assertRaises(HalError) as context:
                lib_wifi.forget("HOME")
        self.assertIn("текущую", str(context.exception))

    def test_other_removed(self):
        networks = [{"id": 0, "ssid": "HOME", "current": True},
                    {"id": 1, "ssid": "TEST", "current": False}]
        with mock.patch.object(lib_wifi.hal_wifi, "networks",
                               return_value=networks), \
                mock.patch.object(lib_wifi.hal_wifi, "remove_network") as rm, \
                mock.patch.object(lib_wifi.hal_wifi, "save_config") as save:
            self.assertTrue(lib_wifi.forget("TEST"))
        rm.assert_called_once_with(1)
        save.assert_called_once_with()

    def test_missing(self):
        with mock.patch.object(lib_wifi.hal_wifi, "networks",
                               return_value=[]):
            with self.assertRaises(HalError):
                lib_wifi.forget("NOPE")

    def test_duplicates_removed(self):
        networks = [{"id": 1, "ssid": "TEST", "current": False},
                    {"id": 2, "ssid": "TEST", "current": False}]
        with mock.patch.object(lib_wifi.hal_wifi, "networks",
                               return_value=networks), \
                mock.patch.object(lib_wifi.hal_wifi, "remove_network") as rm, \
                mock.patch.object(lib_wifi.hal_wifi, "save_config") as save:
            self.assertTrue(lib_wifi.forget("TEST"))
        self.assertEqual([call[0][0] for call in rm.call_args_list], [1, 2])
        save.assert_called_once_with()


class Disconnect(unittest.TestCase):
    def test_lock_busy(self):
        with mock.patch.object(lib_wifi.hal_common, "lock",
                               side_effect=HalError("занято")):
            with self.assertRaises(HalError):
                lib_wifi.disconnect(allow=True)

    def test_forget_lock_busy(self):
        with mock.patch.object(lib_wifi.hal_common, "lock",
                               side_effect=HalError("занято")):
            with self.assertRaises(HalError):
                lib_wifi.forget("TEST")

    def test_requires_allow(self):
        with self.assertRaises(HalError):
            lib_wifi.disconnect()

    def test_allow(self):
        with mock.patch.object(lib_wifi.hal_wifi, "disconnect",
                               return_value=True) as disconnect:
            self.assertTrue(lib_wifi.disconnect(allow=True))
        disconnect.assert_called_once_with()


class Connect(unittest.TestCase):
    def patches(self, calls, **options):
        networks = options.get("networks", [
            {"id": 0, "ssid": "MYNET", "current": True},
        ])
        scan = options.get("scan", [{"ssid": "HOME", "signal": -50,
                                     "flags": "[WPA2-PSK-CCMP][ESS]"}])
        state = options.get("state", "COMPLETED")
        status = options.get("status", {"state": state, "id": 0,
                                        "ssid": "MYNET"})
        wait = options.get("wait", True)
        ip = options.get("ip", "192.0.2.10")

        def record(name, result):
            def function(*args, **kwargs):
                calls.append((name,) + args)
                return result
            return function

        items = [
            mock.patch.object(lib_wifi.hal_wifi, "networks",
                              side_effect=record("networks", networks)),
            mock.patch.object(lib_wifi.hal_wifi, "status",
                              side_effect=record("status", status)),
            mock.patch.object(lib_wifi.hal_wifi, "scan_results",
                              side_effect=record("scan", scan)),
            mock.patch.object(lib_wifi.hal_wifi, "scan",
                              side_effect=record("fresh", scan)),
            mock.patch.object(lib_wifi.hal_wifi, "select_network",
                              side_effect=record("select", True)),
            mock.patch.object(lib_wifi.hal_wifi, "remove_network",
                              side_effect=record("remove", True)),
            mock.patch.object(lib_wifi.hal_wifi, "reconnect",
                              side_effect=record("reconnect", True)),
            mock.patch.object(lib_wifi.hal_wifi, "save_config",
                              side_effect=record("save", True)),
            mock.patch.object(lib_wifi.hal_wifi, "wait_state",
                              side_effect=record("wait", wait)),
            mock.patch.object(lib_wifi.hal_wifi, "ip_address",
                              side_effect=record("ip", ip)),
            mock.patch.object(lib_wifi, "guard_start",
                              side_effect=record("guard", None)),
            mock.patch.object(lib_wifi, "guard_ok",
                              side_effect=record("ok", True)),
        ]
        if options.get("add", True):
            items.insert(3, mock.patch.object(
                lib_wifi.hal_wifi, "add_network",
                side_effect=record("add", 5)))
        return items

    def test_success(self):
        calls = []
        patches = self.patches(calls)
        with mock.patch.object(lib_wifi.time, "time",
                               side_effect=[10.0, 10.1, 12.5]):
            for patch in patches:
                patch.start()
                self.addCleanup(patch.stop)
            result = lib_wifi.connect("HOME", "secret")
        self.assertTrue(result["changed"])
        self.assertEqual(result["ip"], "192.0.2.10")
        names = [call[0] for call in calls]
        self.assertEqual(names, ["networks", "status", "scan", "add",
                                 "guard", "select", "wait", "ip", "ok",
                                 "save"])

    def test_noop(self):
        calls = []
        patches = self.patches(calls, networks=[
            {"id": 0, "ssid": "HOME", "current": True}],
            scan=[{"ssid": "HOME", "signal": -46, "flags": ""}])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        result = lib_wifi.connect("HOME")
        self.assertFalse(result["changed"])
        self.assertNotIn("add", [call[0] for call in calls])

    def test_not_visible(self):
        calls = []
        patches = self.patches(calls, scan=[])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with self.assertRaises(HalError):
            lib_wifi.connect("HOME", "secret")
        self.assertIn("fresh", [call[0] for call in calls])

    def test_stale_cache_rescans(self):
        add = mock.Mock(return_value=5)
        patches = self.patches([], add=False, scan=[])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        results = [
            [],
            [{"ssid": "HOME", "signal": -50,
              "flags": "[WPA2-PSK-CCMP][ESS]"}],
        ]
        with mock.patch.object(lib_wifi.hal_wifi, "scan_results",
                               side_effect=results), \
                mock.patch.object(lib_wifi.hal_wifi, "scan") as scan, \
                mock.patch.object(lib_wifi.hal_wifi, "add_network", add):
            result = lib_wifi.connect("HOME", "secret")
        self.assertTrue(result["changed"])
        scan.assert_called_once_with(fresh=True, wait=lib_wifi.SCAN_WAIT)
        add.assert_called_once_with("HOME", "secret", key_mgmt="WPA-PSK",
                                    scan_ssid=False)

    def test_scan_busy_uses_cache(self):
        add = mock.Mock(return_value=5)
        patches = self.patches([], add=False, scan=[])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        results = [
            [],
            [{"ssid": "HOME", "signal": -50,
              "flags": "[WPA2-PSK-CCMP][ESS]"}],
        ]
        with mock.patch.object(lib_wifi.hal_wifi, "scan_results",
                               side_effect=results), \
                mock.patch.object(lib_wifi.hal_wifi, "scan",
                                  side_effect=HalError("busy")), \
                mock.patch.object(lib_wifi.hal_wifi, "add_network", add):
            result = lib_wifi.connect("HOME", "secret")
        self.assertTrue(result["changed"])
        add.assert_called_once_with("HOME", "secret", key_mgmt="WPA-PSK",
                                    scan_ssid=False)

    def test_hidden(self):
        calls = []
        patches = self.patches(calls, scan=[])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.assertTrue(lib_wifi.connect("HOME", "secret",
                                         hidden=True)["changed"])

    def test_psk_required(self):
        calls = []
        patches = self.patches(calls)
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with self.assertRaises(HalError):
            lib_wifi.connect("HOME")

    def test_no_current(self):
        calls = []
        patches = self.patches(calls, networks=[])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with self.assertRaises(HalError):
            lib_wifi.connect("HOME", "secret")

    def test_allow_no_rollback(self):
        calls = []
        patches = self.patches(calls, networks=[])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.assertTrue(lib_wifi.connect(
            "HOME", "secret", allow_no_rollback=True)["changed"])
        self.assertNotIn("guard", [call[0] for call in calls])

    def test_failure_rollback(self):
        calls = []
        patches = self.patches(calls, wait=False)
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with self.assertRaises(HalError):
            lib_wifi.connect("HOME", "secret")
        names = [call[0] for call in calls]
        self.assertIn("select", names)
        self.assertIn("remove", names)
        self.assertIn("reconnect", names)
        self.assertNotIn("save", names)

    def test_rollback_waits_for_old_network(self):
        calls = []
        patches = self.patches(calls, wait=False)
        statuses = [
            {"state": "COMPLETED", "id": 0, "ssid": "HOME"},
            {"state": "COMPLETED", "id": 5, "ssid": "HOME"},
            {"state": "COMPLETED", "id": 0, "ssid": "HOME"},
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with mock.patch.object(lib_wifi.hal_wifi, "status",
                               side_effect=statuses), \
                mock.patch.object(lib_wifi, "guard_ok") as ok, \
                mock.patch.object(lib_wifi.time, "sleep"):
            with self.assertRaises(HalError) as context:
                lib_wifi.connect("HOME", "secret")
        ok.assert_called_once_with()
        self.assertIn("вернул прежнюю сеть", str(context.exception))

    def test_rollback_timeout_keeps_guard(self):
        calls = []
        patches = self.patches(calls, wait=False)
        statuses = [
            {"state": "COMPLETED", "id": 0, "ssid": "HOME"},
            {"state": "COMPLETED", "id": 5, "ssid": "HOME"},
            {"state": "COMPLETED", "id": 5, "ssid": "HOME"},
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with mock.patch.object(lib_wifi.hal_wifi, "status",
                               side_effect=statuses), \
                mock.patch.object(lib_wifi, "guard_ok") as ok, \
                mock.patch.object(lib_wifi.time, "sleep"), \
                mock.patch.object(lib_wifi.time, "time",
                                  side_effect=[0.0, 0.0, 0.0, 20.0]):
            with self.assertRaises(HalError) as context:
                lib_wifi.connect("HOME", "secret")
        ok.assert_not_called()
        self.assertIn("вернуть не удалось", str(context.exception))

    def test_same_network_reconnects(self):
        calls = []
        patches = self.patches(
            calls,
            networks=[{"id": 0, "ssid": "HOME", "current": True}],
            status={"state": "DISCONNECTED", "id": 0, "ssid": "HOME"})
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        result = lib_wifi.connect("HOME")
        names = [call[0] for call in calls]
        self.assertIn("reconnect", names)
        self.assertNotIn("add", names)
        self.assertFalse(result["changed"])
        self.assertEqual(result["ip"], "192.0.2.10")

    def test_same_network_reconnect_failure(self):
        calls = []
        patches = self.patches(
            calls,
            networks=[{"id": 0, "ssid": "HOME", "current": True}],
            status={"state": "DISCONNECTED", "id": 0, "ssid": "HOME"},
            wait=False)
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with self.assertRaises(HalError):
            lib_wifi.connect("HOME")
        self.assertNotIn("add", [call[0] for call in calls])

    def test_save_failure_keeps_connection(self):
        patches = self.patches([])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with mock.patch.object(lib_wifi.hal_wifi, "save_config",
                               side_effect=HalError("нет места")):
            result = lib_wifi.connect("HOME", "secret")
        self.assertTrue(result["changed"])
        self.assertFalse(result["saved"])

    def test_dry_run(self):
        calls = []
        patches = self.patches(calls)
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        plan = lib_wifi.connect("HOME", "secret", dry_run=True)
        self.assertEqual(plan["ssid"], "HOME")
        self.assertEqual(plan["old_id"], 0)
        self.assertEqual(plan["key_mgmt"], "WPA-PSK")
        self.assertNotIn("add", [call[0] for call in calls])

    def _connect_with(self, scan, ssid, psk=None, **kwargs):
        """Запустить connect с отдельной подменой add_network."""
        patches = self.patches([], add=False, scan=scan)
        add = mock.Mock(return_value=5)
        with mock.patch.object(lib_wifi.hal_wifi, "add_network", add):
            for patch in patches:
                patch.start()
                self.addCleanup(patch.stop)
            lib_wifi.connect(ssid, psk, **kwargs)
        return add

    def test_open_network(self):
        add = self._connect_with(
            [{"ssid": "CAFE", "signal": -60, "flags": "[ESS]"}], "CAFE")
        add.assert_called_once_with("CAFE", None, key_mgmt="NONE",
                                    scan_ssid=False)

    def test_open_network_ignores_psk(self):
        add = self._connect_with(
            [{"ssid": "CAFE", "signal": -60, "flags": "[ESS]"}],
            "CAFE", "лишний")
        add.assert_called_once_with("CAFE", None, key_mgmt="NONE",
                                    scan_ssid=False)

    def test_wpa3_sae(self):
        add = self._connect_with(
            [{"ssid": "HOME", "signal": -50,
              "flags": "[WPA3-SAE-CCMP][ESS]"}], "HOME", "secret")
        add.assert_called_once_with("HOME", "secret", key_mgmt="SAE",
                                    scan_ssid=False)

    def test_transition_psk_sae(self):
        add = self._connect_with(
            [{"ssid": "HOME", "signal": -50,
              "flags": "[WPA2-PSK+SAE-CCMP][ESS]"}], "HOME", "secret")
        add.assert_called_once_with("HOME", "secret", key_mgmt="WPA-PSK",
                                    scan_ssid=False)

    def test_sae_needs_psk(self):
        patches = self.patches([], add=False, scan=[
            {"ssid": "HOME", "signal": -50,
             "flags": "[WPA3-SAE-CCMP][ESS]"}])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with self.assertRaises(HalError):
            lib_wifi.connect("HOME")

    def test_enterprise_refused(self):
        patches = self.patches([], add=False, scan=[
            {"ssid": "CORP", "signal": -50,
             "flags": "[WPA-EAP-CCMP][ESS]"}])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with self.assertRaises(HalError) as context:
            lib_wifi.connect("CORP", "secret")
        self.assertIn("802.1X", str(context.exception))

    def test_key_mgmt_override(self):
        add = self._connect_with([], "HOME", "secret", hidden=True,
                                 key_mgmt="SAE")
        add.assert_called_once_with("HOME", "secret", key_mgmt="SAE",
                                    scan_ssid=True)

    def test_hidden_sets_scan_ssid(self):
        add = self._connect_with([], "HOME", "secret", hidden=True)
        add.assert_called_once_with("HOME", "secret", key_mgmt="WPA-PSK",
                                    scan_ssid=True)

    def test_bad_key_mgmt(self):
        patches = self.patches([], add=False, scan=[
            {"ssid": "HOME", "signal": -50,
             "flags": "[WPA2-PSK-CCMP][ESS]"}])
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with self.assertRaises(HalError):
            lib_wifi.connect("HOME", "secret", key_mgmt="WPA-EAP")

    def test_wifi_lock_busy(self):
        patches = self.patches([], add=False)
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with mock.patch.object(lib_wifi.hal_common, "lock",
                               side_effect=HalError("занято")):
            with self.assertRaises(HalError):
                lib_wifi.connect("HOME", "secret")

    def test_wifi_lock_released(self):
        lock = mock.Mock()
        patches = self.patches([])
        with mock.patch.object(lib_wifi.hal_common, "lock",
                               return_value=lock):
            for patch in patches:
                patch.start()
                self.addCleanup(patch.stop)
            result = lib_wifi.connect("HOME", "secret")
        self.assertTrue(result["changed"])
        lock.release.assert_called_once_with()

    def test_wifi_lock_released_on_failure(self):
        lock = mock.Mock()
        patches = self.patches([], wait=False)
        with mock.patch.object(lib_wifi.hal_common, "lock",
                               return_value=lock):
            for patch in patches:
                patch.start()
                self.addCleanup(patch.stop)
            with self.assertRaises(HalError):
                lib_wifi.connect("HOME", "secret")
        lock.release.assert_called_once_with()


class Saved(unittest.TestCase):
    def test_saved(self):
        with mock.patch.object(lib_wifi.hal_wifi, "saved",
                               return_value=["HOME", "TEST"]):
            self.assertEqual(lib_wifi.saved(), ["HOME", "TEST"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
