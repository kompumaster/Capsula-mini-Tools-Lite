#!/usr/bin/env python3
"""Тесты `common.reboot`: SSH, ADB и выбор способа."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import reboot  # noqa: E402


def result(code=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


class Ssh(unittest.TestCase):
    def test_no_client(self):
        logs = []
        with mock.patch.object(reboot.shutil, "which", return_value=None):
            self.assertFalse(reboot.ssh_reboot("192.0.2.1", logs.append))
        self.assertIn("не найден", logs[-1])

    def test_success(self):
        logs = []
        commands = []

        def which(name):
            return "/usr/bin/ssh" if name == "ssh" else None

        def run(command, **kwargs):
            commands.append(command)
            return result()

        with mock.patch.object(reboot.shutil, "which", side_effect=which), \
                mock.patch.object(reboot, "_run", side_effect=run):
            self.assertTrue(reboot.ssh_reboot("192.0.2.1", logs.append))
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][-1], "true")
        self.assertEqual(commands[1][-1], reboot.REMOTE_REBOOT)
        self.assertIn("-o", commands[0])

    def test_sshpass(self):
        commands = []

        def which(name):
            return {"ssh": "/usr/bin/ssh",
                    "sshpass": "/usr/bin/sshpass"}.get(name)

        def run(command, **kwargs):
            commands.append(command)
            return result()

        with mock.patch.object(reboot.shutil, "which", side_effect=which), \
                mock.patch.object(reboot, "_run", side_effect=run):
            self.assertTrue(reboot.ssh_reboot("192.0.2.1", lambda _: None))
        self.assertEqual(commands[0][:4],
                         ["/usr/bin/sshpass", "-p", reboot.SSH_PASSWORD,
                          "ssh"])
        self.assertNotIn("BatchMode=yes", commands[0])

    def test_rejected(self):
        logs = []
        with mock.patch.object(
                reboot.shutil, "which",
                side_effect=lambda name: "/usr/bin/ssh"
                if name == "ssh" else None), \
                mock.patch.object(
                    reboot, "_run",
                    return_value=result(1, stderr="Permission denied")):
            self.assertFalse(reboot.ssh_reboot("192.0.2.1", logs.append))
        self.assertIn("Permission denied", logs[-1])


class FakeSocket:
    def __init__(self, packets):
        self.packets = list(packets)
        self.buffer = b""
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        while not self.buffer and self.packets:
            self.buffer += self.packets.pop(0)
        if not self.buffer:
            return b""
        chunk, self.buffer = self.buffer[:size], self.buffer[size:]
        return chunk


class Adb(unittest.TestCase):
    def test_no_client(self):
        logs = []
        with mock.patch.object(reboot, "_find_adb", return_value=None), \
                mock.patch.object(reboot, "_adb_raw_reboot",
                                  return_value=False):
            self.assertFalse(reboot.adb_reboot("192.0.2.1", logs.append))
        self.assertIn("не найден", " ".join(logs))

    def test_success(self):
        commands = []
        responses = [
            result(0, stdout="connected to 192.0.2.1:5555"),
            result(0),
        ]

        def run(command, **kwargs):
            commands.append(command)
            return responses.pop(0)

        with mock.patch.object(reboot, "_find_adb",
                               return_value="/usr/bin/adb"), \
                mock.patch.object(reboot, "_run", side_effect=run):
            self.assertTrue(reboot.adb_reboot("192.0.2.1", lambda _: None))
        self.assertEqual(commands[0], ["/usr/bin/adb", "connect",
                                      "192.0.2.1:5555"])
        self.assertEqual(commands[1], ["/usr/bin/adb", "-s",
                                      "192.0.2.1:5555", "reboot"])

    def test_connect_failed(self):
        logs = []
        with mock.patch.object(reboot, "_find_adb",
                               return_value="/usr/bin/adb"), \
                mock.patch.object(
                    reboot, "_run",
                    return_value=result(0, stdout="failed to connect")), \
                mock.patch.object(reboot, "_adb_raw_reboot",
                                  return_value=False):
            self.assertFalse(reboot.adb_reboot("192.0.2.1", logs.append))
        self.assertIn("failed to connect", " ".join(logs))

    def test_raw_without_client(self):
        hello = reboot._adb_packet(reboot.ADB_CNXN, reboot.ADB_VERSION,
                                   reboot.ADB_MAXDATA, b"device::x")
        okay = reboot._adb_packet(reboot.ADB_OKAY, 1, 1)
        fake = FakeSocket([hello, okay])
        with mock.patch.object(reboot, "_find_adb", return_value=None), \
                mock.patch.object(reboot.socket, "create_connection",
                                  return_value=fake):
            self.assertTrue(reboot.adb_reboot("192.0.2.1", lambda _: None))
        self.assertIn(b"reboot:\0", b"".join(fake.sent))

    def test_raw_auth(self):
        auth = reboot._adb_packet(reboot.ADB_AUTH, 1, 0, b"token")
        fake = FakeSocket([auth])
        logs = []
        with mock.patch.object(reboot.socket, "create_connection",
                               return_value=fake):
            self.assertFalse(reboot._adb_raw_reboot("192.0.2.1",
                                                    logs.append))
        self.assertIn("авторизацию", logs[-1])


class Reboot(unittest.TestCase):
    def test_not_found(self):
        logs = []
        with mock.patch.object(reboot, "find_capsula", return_value=None):
            self.assertEqual(reboot.reboot(log=logs.append), 1)
        self.assertIn("не найдена", logs[-1])

    def test_ssh_wins(self):
        logs = []
        with mock.patch.object(reboot, "find_capsula",
                               return_value="192.0.2.1"), \
                mock.patch.object(reboot, "ssh_reboot",
                                  return_value=True) as ssh, \
                mock.patch.object(reboot, "adb_reboot") as adb:
            self.assertEqual(reboot.reboot(log=logs.append), 0)
        ssh.assert_called_once()
        adb.assert_not_called()
        self.assertIn("SSH", logs[-1])

    def test_adb_fallback(self):
        logs = []
        with mock.patch.object(reboot, "ssh_reboot",
                               return_value=False), \
                mock.patch.object(reboot, "adb_reboot",
                                  return_value=True) as adb:
            self.assertEqual(reboot.reboot("192.0.2.1", logs.append), 0)
        adb.assert_called_once()
        self.assertIn("ADB", logs[-1])

    def test_both_fail(self):
        logs = []
        with mock.patch.object(reboot, "ssh_reboot",
                               return_value=False), \
                mock.patch.object(reboot, "adb_reboot",
                                  return_value=False):
            self.assertEqual(reboot.reboot("192.0.2.1", logs.append), 1)
        self.assertIn("не удалось", logs[-1])


if __name__ == "__main__":
    unittest.main()
