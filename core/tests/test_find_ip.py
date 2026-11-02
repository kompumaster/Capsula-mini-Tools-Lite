#!/usr/bin/env python3
"""Тесты `common.find_ip`: имена, `/info`, подсети, скан."""

from __future__ import annotations

import ipaddress
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import find_ip  # noqa: E402


class Names(unittest.TestCase):
    def test_capsula(self):
        self.assertTrue(find_ip._matches(
            "Capsula-mini-0123456789ABCDEF._spotify-connect._tcp.local."))
        self.assertTrue(find_ip._matches("Capsula-mini-0123456789ABCDEF.local."))
        self.assertTrue(find_ip._matches("capsula-mini.local"))

    def test_other(self):
        self.assertFalse(find_ip._matches("other._http._tcp.local."))
        self.assertFalse(find_ip._matches("My-Capsula-mini.local"))
        self.assertFalse(find_ip._matches(""))


class Info(unittest.TestCase):
    def test_marker(self):
        self.assertTrue(find_ip._is_capsula_info(
            {"device_id": ":c:d:capsula_mini:0123456789abcdef"}))
        self.assertTrue(find_ip._is_capsula_info(
            {"device_id": "CAPSULA_MINI"}))

    def test_not_capsula(self):
        self.assertFalse(find_ip._is_capsula_info({"device_id": "other"}))
        self.assertFalse(find_ip._is_capsula_info({}))
        self.assertFalse(find_ip._is_capsula_info([]))
        self.assertFalse(find_ip._is_capsula_info(None))


class Addresses(unittest.TestCase):
    class Info:
        def __init__(self, addresses, raw=None):
            self._addresses = addresses
            self.addresses = raw or []

        def parsed_addresses(self):
            return self._addresses

    def test_prefers_ipv4(self):
        info = self.Info(["fe80::1", "192.0.2.10"])
        self.assertEqual(find_ip._ipv4_from_addresses(info), "192.0.2.10")

    def test_only_ipv6(self):
        self.assertIsNone(find_ip._ipv4_from_addresses(
            self.Info(["fe80::1"])))

    def test_raw_addresses(self):
        info = self.Info([], [b"\xc0\x00\x02\x0a"])
        self.assertEqual(find_ip._ipv4_from_addresses(info), "192.0.2.10")


class Networks(unittest.TestCase):
    def test_24(self):
        self.assertEqual(str(find_ip._network_for("198.51.100.7", 24)),
                         "198.51.100.0/24")

    def test_wide_narrows_to_24(self):
        self.assertEqual(str(find_ip._network_for("198.51.100.7", 16)),
                         "198.51.100.0/24")

    def test_22_kept(self):
        self.assertEqual(str(find_ip._network_for("203.0.113.7", 22)),
                         "203.0.112.0/22")

    def test_skip_loopback_and_link_local(self):
        self.assertIsNone(find_ip._network_for("127.0.0.1", 8))
        self.assertIsNone(find_ip._network_for("169.254.1.1", 16))

    def test_bad(self):
        self.assertIsNone(find_ip._network_for("999.1.1.1", 24))


class Hosts(unittest.TestCase):
    def test_small(self):
        hosts = find_ip._hosts([ipaddress.IPv4Network("198.51.100.0/30")])
        self.assertEqual(hosts, ["198.51.100.1", "198.51.100.2"])

    def test_limit(self):
        hosts = find_ip._hosts([ipaddress.IPv4Network("198.51.0.0/16")])
        self.assertEqual(len(hosts), find_ip.MAX_HOSTS)


class Scan(unittest.TestCase):
    def test_first_found(self):
        with mock.patch.object(find_ip, "_local_networks",
                               return_value=[ipaddress.IPv4Network("203.0.113.0/30")]), \
             mock.patch.object(find_ip, "_probe",
                               side_effect=lambda host:
                               host if host.endswith(".2") else None):
            self.assertEqual(find_ip._find_scan(), "203.0.113.2")

    def test_nothing(self):
        with mock.patch.object(find_ip, "_local_networks",
                               return_value=[]):
            self.assertIsNone(find_ip._find_scan())


if __name__ == "__main__":
    unittest.main(verbosity=2)
