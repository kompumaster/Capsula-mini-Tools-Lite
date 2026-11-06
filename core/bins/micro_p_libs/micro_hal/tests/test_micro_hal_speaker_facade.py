#!/usr/bin/env python3
"""Тесты micro_hal: фасад `lib_speaker` без платы и Pulse."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import HalError, lib_speaker  # noqa: E402

RAW = str(TMP / "facade.raw")
WAV = TMP / "facade.wav"


class PlayPcm(unittest.TestCase):
    def tearDown(self):
        for path in (RAW,):
            try:
                Path(path).unlink()
            except OSError:
                pass

    def test_play_pcm(self):
        with mock.patch.object(lib_speaker, "RAW", RAW), \
                mock.patch.object(lib_speaker.hal_speaker, "play") as play:
            path = lib_speaker.play_pcm(b"\x01\x00" * 800,
                                        rate=24000, channels=1)
        self.assertEqual(path, RAW)
        self.assertEqual(Path(RAW).read_bytes(), b"\x01\x00" * 800)
        play.assert_called_once()
        kwargs = play.call_args[1]
        self.assertTrue(kwargs["raw"])
        self.assertEqual(kwargs["rate"], 24000)
        self.assertEqual(kwargs["channels"], 1)
        self.assertEqual(kwargs["sink"], "master")

    def test_play_pcm_wait(self):
        with mock.patch.object(lib_speaker, "RAW", RAW), \
                mock.patch.object(lib_speaker.hal_speaker, "play"), \
                mock.patch.object(lib_speaker.hal_speaker, "wait") as wait:
            lib_speaker.play_pcm(b"\x00\x00" * 2400, rate=24000, wait=True)
        wait.assert_called_once()
        self.assertFalse(Path(RAW).exists())

    def test_play_pcm_sink(self):
        with mock.patch.object(lib_speaker, "RAW", RAW), \
                mock.patch.object(lib_speaker.hal_speaker, "play") as play:
            lib_speaker.play_pcm(b"\x00\x00" * 10, sink="alarm")
        self.assertEqual(play.call_args[1]["sink"], "alarm")

    def test_play_pcm_odd(self):
        with self.assertRaises(HalError):
            lib_speaker.play_pcm(b"\x01")

    def test_play_pcm_not_bytes(self):
        with self.assertRaises(HalError):
            lib_speaker.play_pcm("abc")

    def test_play_pcm_bad_rate(self):
        with self.assertRaises(HalError):
            lib_speaker.play_pcm(b"\x00\x00", rate=0)


class PlayRaw(unittest.TestCase):
    def test_play_raw(self):
        with mock.patch.object(lib_speaker.hal_speaker, "play",
                               return_value=77) as play, \
                mock.patch.object(lib_speaker.hal_speaker, "wait") as wait:
            pid = lib_speaker.play_raw("/tmp/a.raw", rate=16000,
                                       channels=2)
        self.assertEqual(pid, 77)
        self.assertTrue(play.call_args[1]["raw"])
        self.assertEqual(play.call_args[1]["rate"], 16000)
        self.assertEqual(play.call_args[1]["channels"], 2)
        wait.assert_not_called()

    def test_play_raw_wait(self):
        with mock.patch.object(lib_speaker.hal_speaker, "play",
                               return_value=77), \
                mock.patch.object(lib_speaker.hal_speaker, "wait") as wait:
            lib_speaker.play_raw("/tmp/a.raw", wait=True)
        wait.assert_called_once_with(None)


class Stream(unittest.TestCase):
    def test_stream(self):
        with mock.patch.object(lib_speaker.hal_speaker, "Stream") as stream:
            stream.return_value = "stream"
            result = lib_speaker.stream(sink="alarm", rate=16000,
                                        channels=2)
        self.assertEqual(result, "stream")
        kwargs = stream.call_args[1]
        self.assertEqual(kwargs["sink"], "alarm")
        self.assertEqual(kwargs["rate"], 16000)
        self.assertEqual(kwargs["channels"], 2)


class WriteWav(unittest.TestCase):
    def tearDown(self):
        try:
            WAV.unlink()
        except OSError:
            pass

    def test_write(self):
        pcm = b"\x01\x00" * 100
        with mock.patch.object(lib_speaker.lib_wav, "wav_header",
                               return_value=b"H" * 44):
            self.assertEqual(lib_speaker.write_wav(str(WAV), pcm,
                                                   rate=24000), str(WAV))
        self.assertEqual(WAV.read_bytes(), b"H" * 44 + pcm)

    def test_header(self):
        pcm = b"\x00\x00" * 100
        lib_speaker.write_wav(str(WAV), pcm, rate=16000)
        data = WAV.read_bytes()
        self.assertEqual(data[:4], b"RIFF")
        self.assertEqual(data[8:12], b"WAVE")
        self.assertEqual(len(data), 44 + len(pcm))

    def test_bad_frames(self):
        with self.assertRaises(HalError):
            lib_speaker.write_wav(str(WAV), b"\x00\x00\x00",
                                  channels=2)


class FakeVolume:
    last = None

    def __init__(self, sink, step=5):
        FakeVolume.last = self
        self.sink = sink
        self.value = 50
        self.muted = False

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        return value

    def mute(self):
        self.muted = True
        return True

    def unmute(self):
        self.muted = False
        return False

    def toggle(self):
        self.muted = not self.muted
        return self.muted


class Volume(unittest.TestCase):
    def setUp(self):
        FakeVolume.last = None
        patch = mock.patch.object(lib_speaker.lib_volume, "Volume",
                                  FakeVolume)
        patch.start()
        self.addCleanup(patch.stop)

    def test_get(self):
        self.assertEqual(lib_speaker.get_volume(), 50)
        self.assertEqual(FakeVolume.last.sink, "master")

    def test_set(self):
        self.assertEqual(lib_speaker.set_volume(30), 30)
        self.assertEqual(FakeVolume.last.sink, "master")

    def test_sink(self):
        lib_speaker.set_volume(10, sink="alarm")
        self.assertEqual(FakeVolume.last.sink, "alarm")

    def test_mute(self):
        self.assertTrue(lib_speaker.mute(True))
        self.assertFalse(lib_speaker.mute(False))

    def test_toggle(self):
        self.assertTrue(lib_speaker.toggle_mute())


class StopTemp(unittest.TestCase):
    def test_stop_removes_raw(self):
        path = str(TMP / "facade-stop.raw")
        Path(path).write_bytes(b"x")
        with mock.patch.object(lib_speaker, "RAW", path), \
                mock.patch.object(lib_speaker.hal_speaker, "stop",
                                  return_value=True):
            self.assertTrue(lib_speaker.stop())
        self.assertFalse(Path(path).exists())


class Control(unittest.TestCase):
    def test_delegates(self):
        with mock.patch.object(lib_speaker.hal_speaker, "pause",
                               return_value=True), \
                mock.patch.object(lib_speaker.hal_speaker, "resume",
                                  return_value=True), \
                mock.patch.object(lib_speaker.hal_speaker, "paused",
                                  return_value=False), \
                mock.patch.object(lib_speaker.hal_speaker, "stop",
                                  return_value=True), \
                mock.patch.object(lib_speaker.hal_speaker, "running",
                                  return_value=99), \
                mock.patch.object(lib_speaker.hal_speaker, "wait",
                                  return_value=True):
            self.assertTrue(lib_speaker.pause())
            self.assertTrue(lib_speaker.resume())
            self.assertFalse(lib_speaker.paused())
            self.assertTrue(lib_speaker.stop())
            self.assertEqual(lib_speaker.playing(), 99)
            self.assertTrue(lib_speaker.wait())


if __name__ == "__main__":
    unittest.main()
