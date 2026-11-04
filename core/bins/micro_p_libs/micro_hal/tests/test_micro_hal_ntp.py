#!/usr/bin/env python3
"""Тесты micro_hal: NTP без сети и без платы."""

from __future__ import annotations

import os
import shutil
import struct
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import HalError, lib_ntp  # noqa: E402


def stamp(unix):
    seconds = int(unix) + lib_ntp.NTP_EPOCH
    fraction = int((unix - int(unix)) * 4294967296.0) & 0xFFFFFFFF
    return struct.pack("!II", seconds & 0xFFFFFFFF, fraction)


def packet(t2, t3, originate=b"\x00" * 8, stratum=2, mode=4, leap=0):
    data = bytearray(48)
    data[0] = (leap << 6) | (4 << 3) | mode
    data[1] = stratum
    data[24:32] = originate
    data[32:40] = stamp(t2)
    data[40:48] = stamp(t3)
    return bytes(data)


def request_for(t1):
    return lib_ntp._build_request(t1)[0]


def answer(server, delay, offset=0.0, stratum=2):
    return {
        "server": server,
        "ip": "127.0.0.1",
        "offset": offset,
        "delay": delay,
        "stratum": stratum,
        "leap": 0,
    }


class Parsing(unittest.TestCase):
    def test_offset_and_delay(self):
        t1, t4 = 1000.0, 1000.1
        request = request_for(t1)
        data = packet(2000.0, 2000.05, originate=request[40:48])
        result = lib_ntp._parse_response(data, request, t1, t4)
        self.assertAlmostEqual(result["offset"], 999.975, places=5)
        self.assertAlmostEqual(result["delay"], 0.05, places=5)
        self.assertEqual(result["stratum"], 2)
        self.assertEqual(result["leap"], 0)

    def test_short(self):
        request = request_for(1.0)
        with self.assertRaises(HalError):
            lib_ntp._parse_response(b"\x00" * 40, request, 1.0, 1.1)

    def test_bad_mode(self):
        request = request_for(1.0)
        data = packet(2.0, 2.1, request[40:48], mode=5)
        with self.assertRaises(HalError):
            lib_ntp._parse_response(data, request, 1.0, 1.1)

    def test_kiss_of_death(self):
        request = request_for(1.0)
        data = packet(2.0, 2.1, request[40:48], stratum=0)
        with self.assertRaises(HalError):
            lib_ntp._parse_response(data, request, 1.0, 1.1)

    def test_bad_stratum(self):
        request = request_for(1.0)
        data = packet(2.0, 2.1, request[40:48], stratum=16)
        with self.assertRaises(HalError):
            lib_ntp._parse_response(data, request, 1.0, 1.1)

    def test_foreign_originate(self):
        request = request_for(1.0)
        data = packet(2.0, 2.1, b"\x01" * 8)
        with self.assertRaises(HalError):
            lib_ntp._parse_response(data, request, 1.0, 1.1)

    def test_unsynchronized(self):
        request = request_for(1.0)
        data = packet(2.0, 2.1, request[40:48], leap=3)
        with self.assertRaises(HalError):
            lib_ntp._parse_response(data, request, 1.0, 1.1)

    def test_zero_timestamp(self):
        request = request_for(1.0)
        data = bytearray(packet(2.0, 2.1, request[40:48]))
        data[32:40] = b"\x00" * 8
        with self.assertRaises(HalError):
            lib_ntp._parse_response(bytes(data), request, 1.0, 1.1)

    def test_era_wrap(self):
        value = lib_ntp._timestamp(struct.pack("!II", 0, 1))
        self.assertGreater(value, 0)
        self.assertAlmostEqual(value, 2085978496.0, places=3)


class Address(unittest.TestCase):
    def test_bytes_ipv4(self):
        raw = b"\x02\x00\x00\x7b\xc0\x00\x02\x0a" + b"\x00" * 8
        self.assertEqual(lib_ntp._sockaddr_ip(2, raw), "192.0.2.10")

    def test_tuple(self):
        self.assertEqual(
            lib_ntp._sockaddr_ip(2, ("127.0.0.1", 123)), "127.0.0.1")


class Selection(unittest.TestCase):
    def setUp(self):
        lib_ntp.forget()

    def run_select(self, replies, max_delay=0.15):
        def fake(server, timeout):
            value = replies[server]
            if isinstance(value, Exception):
                raise value
            return answer(server, value)
        with mock.patch.object(lib_ntp, "_query_one", side_effect=fake):
            return lib_ntp.query(
                servers=tuple(replies), timeout=1.0, max_delay=max_delay)

    def test_first_fast(self):
        result = self.run_select({"a": 0.01, "b": 0.02})
        self.assertEqual(result["server"], "a")
        self.assertEqual(result["tried"], ["a"])

    def test_skips_slow(self):
        result = self.run_select({"a": 0.5, "b": 0.02})
        self.assertEqual(result["server"], "b")
        self.assertEqual(result["tried"], ["a", "b"])

    def test_best_when_all_slow(self):
        result = self.run_select({"a": 0.4, "b": 0.2, "c": 0.9})
        self.assertEqual(result["server"], "b")
        self.assertEqual(result["tried"], ["a", "b", "c"])

    def test_skips_errors(self):
        result = self.run_select({
            "a": HalError("нет"),
            "b": 0.02,
        })
        self.assertEqual(result["server"], "b")
        self.assertEqual(result["tried"], ["a", "b"])

    def test_all_fail(self):
        with self.assertRaises(HalError):
            self.run_select({
                "a": HalError("нет"),
                "b": HalError("таймаут"),
            })

    def test_default_list(self):
        seen = []

        def fake(server, timeout):
            seen.append(server)
            return answer(server, 0.01)

        with mock.patch.object(lib_ntp, "_query_one", side_effect=fake):
            result = lib_ntp.query()
        self.assertEqual(seen, [lib_ntp.DEFAULT[0]])
        self.assertEqual(result["server"], lib_ntp.MOSCOW[0])

    def test_empty_list(self):
        with self.assertRaises(HalError):
            lib_ntp.query(servers=())

    def test_bad_timeout(self):
        with self.assertRaises(HalError):
            lib_ntp.query(servers=("a",), timeout=0)

    def test_explicit_server(self):
        seen = []

        def fake(server, timeout):
            seen.append(server)
            return answer(server, 0.01)

        with mock.patch.object(lib_ntp, "_query_one", side_effect=fake):
            result = lib_ntp.query(server="only")
        self.assertEqual(seen, ["only"])
        self.assertEqual(result["tried"], ["only"])
        self.assertIsNone(lib_ntp.cached())

    def test_server_and_servers_conflict(self):
        with self.assertRaises(HalError):
            lib_ntp.query(server="a", servers=("b",))


class Scanning(unittest.TestCase):
    def setUp(self):
        lib_ntp.forget()

    def scan(self, replies):
        def fake(server, timeout):
            value = replies[server]
            if isinstance(value, Exception):
                raise value
            return answer(server, value)

        with mock.patch.object(lib_ntp, "_query_one", side_effect=fake):
            return lib_ntp.scan(servers=tuple(replies), timeout=1.0)

    def test_sorted_by_delay(self):
        results = self.scan({
            "a": 0.05,
            "b": 0.01,
            "c": HalError("нет"),
        })
        self.assertEqual([item["server"] for item in results],
                         ["b", "a", "c"])
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[2]["ok"])
        self.assertIn("error", results[2])

    def test_all_fail(self):
        results = self.scan({"a": HalError("нет"), "b": HalError("нет")})
        self.assertEqual(len(results), 2)
        self.assertTrue(all(not item["ok"] for item in results))

    def test_empty_list(self):
        with self.assertRaises(HalError):
            lib_ntp.scan(servers=())

    def test_fastest(self):
        def fake(server, timeout):
            return answer(server, {"a": 0.05, "b": 0.01}[server])

        with mock.patch.object(lib_ntp, "_query_one", side_effect=fake):
            result = lib_ntp.fastest(servers=("a", "b"), timeout=1.0)
        self.assertEqual(result["server"], "b")

    def test_fastest_fail(self):
        def fake(server, timeout):
            raise HalError("нет")

        with mock.patch.object(lib_ntp, "_query_one", side_effect=fake):
            with self.assertRaises(HalError):
                lib_ntp.fastest(servers=("a",), timeout=1.0)


class Caching(unittest.TestCase):
    def setUp(self):
        lib_ntp.forget()

    def test_scan_remembers_best(self):
        def fake(server, timeout):
            return answer(server, {"a": 0.05, "b": 0.01}[server])

        with mock.patch.object(lib_ntp, "_query_one", side_effect=fake):
            lib_ntp.scan(servers=("a", "b"), timeout=1.0)
        self.assertEqual(lib_ntp.cached(), "b")

    def test_cached_first(self):
        lib_ntp._cached = "b"
        seen = []

        def fake(server, timeout):
            seen.append(server)
            return answer(server, 0.01)

        with mock.patch.object(lib_ntp, "_query_one", side_effect=fake):
            result = lib_ntp.query()
        self.assertEqual(seen, ["b"])
        self.assertEqual(result["server"], "b")

    def test_failed_cached_dropped(self):
        lib_ntp._cached = "a"

        def fake(server, timeout):
            if server == "a":
                raise HalError("нет")
            return answer(server, 0.01)

        with mock.patch.object(lib_ntp, "_query_one", side_effect=fake):
            result = lib_ntp.query(servers=("a", "b"))
        self.assertEqual(result["server"], "b")
        self.assertEqual(lib_ntp.cached(), "b")

    def test_forget(self):
        lib_ntp._cached = "b"
        lib_ntp.forget()
        self.assertIsNone(lib_ntp.cached())

    def test_default_alive_only(self):
        dead = (
            "ntp5.vniiftri.ru",
            "ntp.sstf.nsk.ru",
            "timesstf.sstf.nsk.ru",
            "vniiftri1.khv.ru",
            "ntp.kam.vniiftri.net",
        )
        for name in dead:
            self.assertNotIn(name, lib_ntp.DEFAULT)


class Sync(unittest.TestCase):
    def setUp(self):
        lib_ntp.forget()

    def test_sync_sets_time(self):
        captured = []

        with mock.patch.object(
                lib_ntp, "query", return_value=answer("a", 0.01, 1.5)), \
                mock.patch.object(lib_ntp, "set_time",
                                  side_effect=captured.append), \
                mock.patch.object(lib_ntp.time, "time", return_value=1000.0):
            offset = lib_ntp.sync(servers=("a",))
        self.assertEqual(offset, 1.5)
        self.assertEqual(captured, [1001.5])

    def test_sync_explicit_server(self):
        with mock.patch.object(
                lib_ntp, "query",
                return_value=answer("x", 0.01, 0.5)) as q, \
                mock.patch.object(lib_ntp, "set_time"), \
                mock.patch.object(lib_ntp.time, "time", return_value=1000.0):
            lib_ntp.sync(server="x")
        q.assert_called_once_with(
            "x", None, lib_ntp.TIMEOUT, lib_ntp.MAX_DELAY)

    def test_set_time_command(self):
        timestamp = 1700000000.0
        expected = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.gmtime(timestamp))
        with mock.patch.object(lib_ntp.hal_common, "require_root"), \
                mock.patch.object(lib_ntp.hal_common, "run",
                                  return_value=0) as run:
            lib_ntp.set_time(timestamp)
        run.assert_called_once_with(
            "date -u -s '{}' >/dev/null 2>&1".format(expected))

    def test_set_time_failure(self):
        with mock.patch.object(lib_ntp.hal_common, "require_root"), \
                mock.patch.object(lib_ntp.hal_common, "run",
                                  return_value=1):
            with self.assertRaises(HalError):
                lib_ntp.set_time(0.0)


class Timezone(unittest.TestCase):
    def setUp(self):
        self.root = TMP / "ntp_tz"
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self):
        if self.root.exists():
            shutil.rmtree(self.root)

    def zone_file(self, zone):
        path = self.root / "zoneinfo" / zone
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
        return path

    def test_get_from_file(self):
        path = self.root / "timezone"
        path.write_text("Europe/Moscow\n")
        with mock.patch.object(lib_ntp, "TIMEZONE_FILE", str(path)):
            self.assertEqual(lib_ntp.get_timezone(), "Europe/Moscow")

    def test_get_from_symlink(self):
        zone = self.zone_file("Europe/Moscow")
        link = self.root / "localtime"
        os.symlink(str(zone), str(link))
        with mock.patch.object(
                lib_ntp, "TIMEZONE_FILE", str(self.root / "нет")), \
                mock.patch.object(lib_ntp, "LOCALTIME", str(link)):
            self.assertEqual(lib_ntp.get_timezone(), "Europe/Moscow")

    def test_get_empty(self):
        with mock.patch.object(
                lib_ntp, "TIMEZONE_FILE", str(self.root / "нет")), \
                mock.patch.object(
                    lib_ntp, "LOCALTIME", str(self.root / "нет")):
            self.assertEqual(lib_ntp.get_timezone(), "")

    def test_set_success(self):
        zone = self.zone_file("Europe/Moscow")
        localtime = self.root / "localtime"
        tzfile = self.root / "timezone"
        with mock.patch.object(
                lib_ntp, "ZONEINFO", str(self.root / "zoneinfo")), \
                mock.patch.object(lib_ntp, "LOCALTIME", str(localtime)), \
                mock.patch.object(lib_ntp, "TIMEZONE_FILE", str(tzfile)), \
                mock.patch.object(lib_ntp.hal_common, "require_root"), \
                mock.patch.object(lib_ntp.hal_common, "run",
                                  return_value=0) as run:
            result = lib_ntp.set_timezone("Europe/Moscow")
        self.assertEqual(result, "Europe/Moscow")
        run.assert_called_once_with(
            "ln -sf '{}' '{}'".format(zone, localtime))
        self.assertEqual(tzfile.read_text().strip(), "Europe/Moscow")

    def test_set_failure(self):
        self.zone_file("Europe/Moscow")
        tzfile = self.root / "timezone"
        with mock.patch.object(
                lib_ntp, "ZONEINFO", str(self.root / "zoneinfo")), \
                mock.patch.object(lib_ntp, "LOCALTIME",
                                  str(self.root / "localtime")), \
                mock.patch.object(lib_ntp, "TIMEZONE_FILE", str(tzfile)), \
                mock.patch.object(lib_ntp.hal_common, "require_root"), \
                mock.patch.object(lib_ntp.hal_common, "run",
                                  return_value=1):
            with self.assertRaises(HalError):
                lib_ntp.set_timezone("Europe/Moscow")
        self.assertFalse(tzfile.exists())

    def test_invalid(self):
        self.zone_file("Europe/Moscow")
        with mock.patch.object(
                lib_ntp, "ZONEINFO", str(self.root / "zoneinfo")), \
                mock.patch.object(lib_ntp.hal_common, "require_root"):
            for zone in ("/Europe/Moscow", "../etc/passwd",
                         "Bad Zone", "No/Such"):
                with self.assertRaises(HalError):
                    lib_ntp.set_timezone(zone)


if __name__ == "__main__":
    unittest.main(verbosity=2)
