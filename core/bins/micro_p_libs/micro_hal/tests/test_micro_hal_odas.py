#!/usr/bin/env python3
"""Тесты micro_hal: ODAS JSON без платы и без демона."""

from __future__ import annotations

import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, lib_odas  # noqa: E402

FRAME = (b'{"timeStamp": 1, "src": ['
         b'{"id": 1, "tag": "a", "x": 1.0, "y": 0.0, "z": 0.0, '
         b'"activity": 0.9}]}')


class Parsing(unittest.TestCase):
    def test_whole(self):
        objects, rest = lib_odas.parse_stream(FRAME)
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0]["src"][0]["id"], 1)
        self.assertEqual(rest, b"")

    def test_split(self):
        first = FRAME[:20]
        second = FRAME[20:]
        objects, rest = lib_odas.parse_stream(first)
        self.assertEqual(objects, [])
        self.assertEqual(rest, first)
        objects, rest = lib_odas.parse_stream(second, rest)
        self.assertEqual(len(objects), 1)
        self.assertEqual(rest, b"")

    def test_two(self):
        objects, rest = lib_odas.parse_stream(FRAME + FRAME)
        self.assertEqual(len(objects), 2)
        self.assertEqual(rest, b"")

    def test_braces_in_string(self):
        data = b'{"src": [{"tag": "a}b{c", "x": 0}]}'
        objects, rest = lib_odas.parse_stream(data)
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0]["src"][0]["tag"], "a}b{c")
        self.assertEqual(rest, b"")

    def test_garbage_before(self):
        objects, rest = lib_odas.parse_stream(b"junk" + FRAME)
        self.assertEqual(len(objects), 1)
        self.assertEqual(rest, b"")

    def test_bad_json(self):
        with self.assertRaises(HalError):
            lib_odas.parse_stream(b'{"src": [}')


class Direction(unittest.TestCase):
    def test_front(self):
        result = lib_odas.direction({"x": 0, "y": 1, "z": 0})
        self.assertAlmostEqual(result["azimuth"], 0.0)
        self.assertAlmostEqual(result["elevation"], 0.0)

    def test_right(self):
        result = lib_odas.direction({"x": 1, "y": 0, "z": 0})
        self.assertAlmostEqual(result["azimuth"], 90.0)

    def test_left(self):
        result = lib_odas.direction({"x": -1, "y": 0, "z": 0})
        self.assertAlmostEqual(result["azimuth"], -90.0)

    def test_back(self):
        result = lib_odas.direction({"x": 0, "y": -1, "z": 0})
        self.assertAlmostEqual(abs(result["azimuth"]), 180.0)

    def test_up(self):
        result = lib_odas.direction({"x": 1, "y": 0, "z": 1})
        self.assertAlmostEqual(result["azimuth"], 90.0)
        self.assertAlmostEqual(result["elevation"], 45.0)

    def test_zero(self):
        result = lib_odas.direction({})
        self.assertEqual(result["azimuth"], 0.0)
        self.assertEqual(result["elevation"], 0.0)

    def test_pots_energy(self):
        result = lib_odas.direction(
            {"x": 0, "y": 1, "E": 0.7}, energy_key="E")
        self.assertAlmostEqual(result["azimuth"], 0.0)
        self.assertAlmostEqual(result["activity"], 0.7)


class Server(unittest.TestCase):
    def test_tcp(self):
        server = lib_odas.Server(port=0)
        server.listen()
        client = socket.create_connection(
            (lib_odas.HOST, server.port), timeout=2)
        try:
            client.sendall(FRAME)
            frames = []
            for _ in range(20):
                frames.extend(server.poll(100))
                if frames:
                    break
            self.assertEqual(len(frames), 1)
            self.assertEqual(server.frames(), 1)
            self.assertEqual(server.timestamp(), 1)
            self.assertEqual(server.latest_frame()["src"][0]["id"], 1)
            self.assertEqual(server.tracks()[0]["id"], 1)
            result = server.direction()
            self.assertAlmostEqual(result["azimuth"], 90.0)
            self.assertAlmostEqual(result["activity"], 0.9)
        finally:
            client.close()
            server.close()

    def test_empty(self):
        server = lib_odas.Server(port=0)
        server.listen()
        try:
            self.assertEqual(server.latest(), [])
            self.assertIsNone(server.direction())
        finally:
            server.close()

    def test_not_listening(self):
        server = lib_odas.Server(port=0)
        with self.assertRaises(HalError):
            server.poll(0)

    def test_listen_busy(self):
        server = lib_odas.Server(port=0)
        fake = mock.Mock()
        fake.bind.side_effect = OSError("Address already in use")
        with mock.patch.object(lib_odas.socket, "socket",
                               return_value=fake):
            with self.assertRaises(HalError) as context:
                server.listen()
        self.assertIn("порт", str(context.exception))
        fake.close.assert_called_once_with()
        self.assertIsNone(server._sock)

    def test_categories_and_wait(self):
        server = lib_odas.Server(port=0)
        server.listen()
        client = socket.create_connection(
            (lib_odas.HOST, server.port), timeout=2)
        try:
            client.sendall(b'{"timeStamp": 3, "src": [{"category": "speech"}]}')
            frame = server.wait(500)
            self.assertEqual(frame["timeStamp"], 3)
            self.assertEqual(server.categories()[0]["category"], "speech")
        finally:
            client.close()
            server.close()

    def test_context(self):
        with lib_odas.Server(port=0) as server:
            server.listen()
            self.assertIsNotNone(server._sock)
        self.assertIsNone(server._sock)


class Audio(unittest.TestCase):
    def test_chunks(self):
        server = lib_odas.AudioServer(port=0, channels=2, hop=2, width=2)
        server.listen()
        client = socket.create_connection(
            (lib_odas.HOST, server.port), timeout=2)
        try:
            client.sendall(b"a" * 20)
            chunks = []
            for _ in range(20):
                chunks.extend(server.poll(100))
                if len(chunks) >= 2:
                    break
            self.assertEqual(len(chunks), 2)
            self.assertEqual(len(chunks[0]), 8)
            self.assertEqual(server.latest(), chunks[-1])
            self.assertEqual(server.count(), 2)
        finally:
            client.close()
            server.close()

    def test_not_listening(self):
        server = lib_odas.AudioServer(port=0)
        with self.assertRaises(HalError):
            server.poll(0)

    def test_listen_busy(self):
        server = lib_odas.AudioServer(port=0, channels=2, hop=2, width=2)
        fake = mock.Mock()
        fake.bind.side_effect = OSError("Address already in use")
        with mock.patch.object(lib_odas.socket, "socket",
                               return_value=fake):
            with self.assertRaises(HalError) as context:
                server.listen()
        self.assertIn("порт", str(context.exception))
        fake.close.assert_called_once_with()
        self.assertIsNone(server._sock)

    def test_channel(self):
        server = lib_odas.AudioServer(port=0, channels=4, hop=2, width=2)
        server._latest = bytes(range(16))
        self.assertEqual(server.channel(1), bytes([2, 3, 10, 11]))
        self.assertEqual(server.channel(3, server._latest), bytes([6, 7, 14, 15]))

    def test_channel_bad(self):
        server = lib_odas.AudioServer(port=0, channels=4)
        with self.assertRaises(HalError):
            server.channel(4)
        with self.assertRaises(HalError):
            server.channel(-1)

    def test_split(self):
        server = lib_odas.AudioServer(port=0, channels=4, hop=2, width=2)
        parts = server.split(bytes(range(16)))
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[2], bytes([4, 5, 12, 13]))

    def test_pick(self):
        tracks = [{"activity": 0.1}, {"activity": 0.9},
                  {"activity": 0.5}, {"activity": 0.0}]
        self.assertEqual(lib_odas.AudioServer.pick(tracks), 1)
        self.assertEqual(
            lib_odas.AudioServer.pick([{"E": 2.0}, {"E": 5.0}], "E"), 1)

    def test_read_and_frames(self):
        server = lib_odas.AudioServer(port=0, channels=2, hop=2, width=2)
        server.listen()
        client = socket.create_connection(
            (lib_odas.HOST, server.port), timeout=2)
        try:
            client.sendall(b"b" * 16)
            first = None
            for _ in range(20):
                first = server.read(100)
                if first is not None:
                    break
            self.assertEqual(len(first), 8)
            self.assertEqual(len(server.read(0)), 8)
            self.assertEqual(server.frames(), 2)
        finally:
            client.close()
            server.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
