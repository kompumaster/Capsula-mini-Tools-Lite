#!/usr/bin/env python3
"""Тесты micro_hal: мост `lib_mic` → `lib_odas` без платы."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, lib_mic, lib_odas  # noqa: E402


class FakeServer:
    """Подмена `lib_odas.Server`."""

    def __init__(self, tracks=None, direction=None, grow=True):
        self.tracks_value = [] if tracks is None else tracks
        self.direction_value = direction
        self.listening = False
        self.polls = []
        self.waits = []
        self.closed = False
        self.frames_value = 0
        self.grow = grow

    def listen(self):
        self.listening = True

    def poll(self, timeout_ms=0):
        self.polls.append(timeout_ms)
        if self.grow:
            self.frames_value += 1
        return []

    def wait(self, timeout_ms=1000):
        self.waits.append(timeout_ms)
        self.frames_value += 1
        return {"timeStamp": self.frames_value}

    def frames(self):
        return self.frames_value

    def tracks(self):
        return list(self.tracks_value)

    def direction(self):
        return self.direction_value

    def close(self):
        self.closed = True


class FakeAudio:
    """Подмена `lib_odas.AudioServer`."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.listening = False
        self.closed = False

    def listen(self):
        self.listening = True

    def poll(self, timeout_ms=0):
        return []

    def close(self):
        self.closed = True


class Bundle(unittest.TestCase):
    def setUp(self):
        lib_mic._odas = None
        self.addCleanup(self._reset)

    def _reset(self):
        if lib_mic._odas is not None:
            lib_mic._odas.close()
        lib_mic._odas = None

    def test_open_odas(self):
        with mock.patch.object(lib_odas, "Server",
                               side_effect=lambda **kw: FakeServer()) as make:
            odas = lib_mic.open_odas()
        self.assertTrue(odas.tracks.listening)
        self.assertTrue(odas.pots.listening)
        self.assertTrue(odas.categories.listening)
        ports = [call[1].get("port") for call in make.call_args_list]
        self.assertEqual(ports, [lib_odas.PORT, lib_odas.POT_PORT,
                                 lib_odas.CATEGORY_PORT])
        self.assertIs(lib_mic.open_odas(), odas)

    def test_open_odas_pots_energy(self):
        with mock.patch.object(lib_odas, "Server",
                               side_effect=lambda **kw: FakeServer()) as make:
            lib_mic.open_odas()
        keys = [call[1].get("energy_key") for call in make.call_args_list]
        self.assertEqual(keys, [None, "E", None])

    def test_open_odas_sss(self):
        with mock.patch.object(lib_odas, "Server",
                               side_effect=lambda **kw: FakeServer()), \
                mock.patch.object(lib_odas, "AudioServer",
                                  side_effect=lambda **kw: FakeAudio(**kw)) as audio:
            odas = lib_mic.open_odas(sss=True)
        self.assertIsNotNone(odas.separated)
        self.assertIsNotNone(odas.postfiltered)
        ports = [call[1].get("port") for call in audio.call_args_list]
        self.assertEqual(ports, [lib_odas.SEPARATED_PORT,
                                 lib_odas.POSTFILTERED_PORT])
        self.assertEqual(len(odas.servers()), 5)
        self.assertTrue(odas.separated.listening)

    def test_close_odas(self):
        with mock.patch.object(lib_odas, "Server",
                               side_effect=lambda **kw: FakeServer()):
            odas = lib_mic.open_odas()
        self.assertTrue(lib_mic.close_odas())
        self.assertTrue(odas.tracks.closed)
        self.assertTrue(odas.categories.closed)
        self.assertFalse(lib_mic.close_odas())

    def test_open_odas_sss_conflict(self):
        with mock.patch.object(lib_odas, "Server",
                               side_effect=lambda **kw: FakeServer()):
            lib_mic.open_odas()
        with self.assertRaises(HalError) as context:
            lib_mic.open_odas(sss=True)
        self.assertIn("close_odas", str(context.exception))

    def test_open_odas_plain_conflict(self):
        with mock.patch.object(lib_odas, "Server",
                               side_effect=lambda **kw: FakeServer()), \
                mock.patch.object(lib_odas, "AudioServer",
                                  side_effect=lambda **kw: FakeAudio(**kw)):
            lib_mic.open_odas(sss=True)
        with self.assertRaises(HalError) as context:
            lib_mic.open_odas()
        self.assertIn("close_odas", str(context.exception))

    def test_tracks(self):
        odas = mock.Mock(spec=lib_mic.Odas)
        odas.tracks = FakeServer(tracks=[{"id": 7}])
        self.assertEqual(lib_mic.tracks(odas=odas), [{"id": 7}])
        odas.poll.assert_called_once_with(0)

    def test_tracks_timeout_stops_on_frame(self):
        odas = mock.Mock(spec=lib_mic.Odas)
        odas.tracks = FakeServer()
        result = lib_mic.tracks(timeout=0.05, odas=odas)
        self.assertEqual(result, [])
        self.assertTrue(odas.poll.called)

    def test_wait_ready(self):
        odas = mock.Mock(spec=lib_mic.Odas)
        odas.tracks = FakeServer()
        odas.poll.side_effect = lambda timeout_ms=0: odas.tracks.poll(timeout_ms)
        self.assertTrue(lib_mic.wait_ready(timeout=0.5, odas=odas))
        self.assertTrue(odas.poll.called)

    def test_wait_ready_false(self):
        odas = mock.Mock(spec=lib_mic.Odas)
        odas.tracks = FakeServer(grow=False)
        self.assertFalse(lib_mic.wait_ready(timeout=0.1, odas=odas))

    def test_tracks_nothing_without_timeout(self):
        odas = mock.Mock(spec=lib_mic.Odas)
        odas.tracks = FakeServer(grow=False)
        lib_mic.tracks(odas=odas)
        self.assertEqual(odas.poll.call_count, 1)


class Single(unittest.TestCase):
    def setUp(self):
        lib_mic._odas = None
        self.addCleanup(self._reset)

    def _reset(self):
        lib_mic._odas = None

    def test_tracks_server(self):
        server = FakeServer(tracks=[{"id": 1}])
        self.assertEqual(lib_mic.tracks(odas=server), [{"id": 1}])
        self.assertEqual(server.polls, [0])

    def test_tracks_server_timeout(self):
        server = FakeServer(tracks=[{"id": 2}])
        lib_mic.tracks(timeout=0.5, odas=server)
        self.assertEqual(server.waits, [500])

    def test_direction(self):
        value = {"azimuth": 10.0, "elevation": 5.0,
                 "activity": 1.0, "id": 3}
        server = FakeServer(direction=value)
        self.assertEqual(lib_mic.direction(odas=server), value)

    def test_direction_no_data(self):
        with self.assertRaises(HalError):
            lib_mic.direction(odas=FakeServer(direction=None))

    def test_direction_singleton(self):
        server = FakeServer(direction={"azimuth": 1.0})
        with mock.patch.object(lib_odas, "Server",
                               side_effect=lambda **kw: server):
            value = lib_mic.direction(timeout=0.2)
        self.assertEqual(value["azimuth"], 1.0)


class Separate(unittest.TestCase):
    def test_message(self):
        with self.assertRaises(HalError) as context:
            lib_mic.separate()
        self.assertIn("AudioServer", str(context.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
