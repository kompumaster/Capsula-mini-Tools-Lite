#!/usr/bin/env python3
"""Тесты micro_hal: тон и мелодии без платы."""

from __future__ import annotations

import math
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import HalError, lib_speaker  # noqa: E402


def samples(pcm):
    return struct.unpack("<%dh" % (len(pcm) // 2), pcm)


def rms(pcm):
    values = samples(pcm)
    return math.sqrt(sum(value * value for value in values) / len(values))


def goertzel(pcm, freq, rate=lib_speaker.RATE):
    values = samples(pcm)
    step = 2.0 * math.pi * freq / rate
    coeff = 2.0 * math.cos(step)
    s1 = s2 = 0.0
    for value in values:
        s0 = value + coeff * s1 - s2
        s2, s1 = s1, s0
    power = s1 * s1 + s2 * s2 - coeff * s1 * s2
    return math.sqrt(max(power, 0.0)) / len(values) * 2.0


class TonePcm(unittest.TestCase):
    def test_length(self):
        pcm = lib_speaker.tone_pcm(1000, 0.1)
        self.assertEqual(len(pcm), 3200)
        self.assertEqual(len(samples(pcm)), 1600)

    def test_amplitude(self):
        pcm = lib_speaker.tone_pcm(1000, 0.1, amplitude=0.5, fade_ms=0)
        self.assertEqual(max(samples(pcm)), 16383)
        self.assertAlmostEqual(rms(pcm) / (0.5 * 32767), 1 / math.sqrt(2),
                               places=2)

    def test_frequency(self):
        pcm = lib_speaker.tone_pcm(440, 0.5)
        self.assertGreater(goertzel(pcm, 440), goertzel(pcm, 880) * 20)

    def test_fade(self):
        pcm = lib_speaker.tone_pcm(1000, 0.1, fade_ms=10)
        values = samples(pcm)
        self.assertEqual(values[0], 0)
        self.assertEqual(values[-1], 0)
        self.assertEqual(abs(values[1]) < 200, True)
        self.assertGreater(max(abs(value) for value in values[100:1500]), 9000)

    def test_no_fade(self):
        pcm = lib_speaker.tone_pcm(1000, 0.1, fade_ms=0)
        self.assertEqual(samples(pcm)[0], 0)
        self.assertNotEqual(samples(pcm)[-1], 0)

    def test_tone_removes_tmp(self):
        with mock.patch.object(lib_speaker.hal_speaker, "play"), \
                mock.patch.object(lib_speaker.hal_speaker, "wait"):
            path = lib_speaker.tone(1000, 0.05)
        self.assertEqual(path, lib_speaker.RAW)
        self.assertFalse(Path(path).exists())

    def test_silence(self):
        pcm = lib_speaker.tone_pcm(0, 0.05)
        self.assertEqual(set(samples(pcm)), {0})
        self.assertEqual(len(pcm), 1600)

    def test_defaults(self):
        pcm = lib_speaker.tone_pcm(1000, 0.05)
        self.assertEqual(max(samples(pcm)), int(0.3 * 32767))

    def test_bad_frequency(self):
        with self.assertRaises(HalError):
            lib_speaker.tone_pcm(-1, 0.1)
        with self.assertRaises(HalError):
            lib_speaker.tone_pcm(9000, 0.1)

    def test_bad_seconds(self):
        with self.assertRaises(HalError):
            lib_speaker.tone_pcm(1000, 0)

    def test_bad_amplitude(self):
        with self.assertRaises(HalError):
            lib_speaker.tone_pcm(1000, 0.1, amplitude=1.5)


class FakeHelper:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def tone(self, rate, freq, frames, amplitude, fade):
        self.calls.append(("tone", rate, freq, frames, amplitude, fade))
        return -1 if self.fail else frames

    def zero(self, frames):
        self.calls.append(("zero", frames))
        return -1 if self.fail else frames

    def view(self, size):
        return bytearray(size)

    def error(self):
        return "spk errno 22"


class HelperPath(unittest.TestCase):
    def setUp(self):
        self.saved = lib_speaker._HELPER
        self.addCleanup(self._restore)

    def _restore(self):
        lib_speaker._HELPER = self.saved

    def test_tone(self):
        fake = FakeHelper()
        lib_speaker._HELPER = fake
        pcm = lib_speaker.tone_pcm(1000, 0.1)
        self.assertEqual(fake.calls,
                         [("tone", 16000, 1000000, 1600, 9830, 160)])
        self.assertEqual(len(pcm), 3200)

    def test_tone_removes_tmp(self):
        with mock.patch.object(lib_speaker.hal_speaker, "play"), \
                mock.patch.object(lib_speaker.hal_speaker, "wait"):
            path = lib_speaker.tone(1000, 0.05)
        self.assertEqual(path, lib_speaker.RAW)
        self.assertFalse(Path(path).exists())

    def test_silence(self):
        fake = FakeHelper()
        lib_speaker._HELPER = fake
        pcm = lib_speaker.tone_pcm(0, 0.05)
        self.assertEqual(fake.calls, [("zero", 800)])
        self.assertEqual(len(pcm), 1600)

    def test_error(self):
        lib_speaker._HELPER = FakeHelper(fail=True)
        with self.assertRaises(HalError) as context:
            lib_speaker.tone_pcm(1000, 0.1)
        self.assertIn("errno 22", str(context.exception))

    def test_fallback(self):
        lib_speaker._HELPER = None
        pcm = lib_speaker.tone_pcm(1000, 0.1)
        self.assertEqual(len(pcm), 3200)

    def test_helper_retries(self):
        calls = []

        def make(path):
            calls.append(path)
            if len(calls) == 1:
                raise OSError("нет библиотеки")
            return object()

        lib_speaker._HELPER = False
        with mock.patch.object(lib_speaker, "_SpeakerLibrary",
                               side_effect=make):
            self.assertIsNone(lib_speaker.helper())
            self.assertIsNotNone(lib_speaker.helper())
        self.assertEqual(len(calls), 2)


class MelodyPcm(unittest.TestCase):
    def test_duration(self):
        pcm = lib_speaker.melody_pcm([(440, 100), (0, 50)])
        self.assertEqual(len(samples(pcm)), 2400)

    def test_notes(self):
        pcm = lib_speaker.melody_pcm([(440, 100), (880, 100)])
        self.assertEqual(len(samples(pcm)), 3200)

    def test_empty(self):
        with self.assertRaises(HalError):
            lib_speaker.melody_pcm([])

    def test_bad_note(self):
        with self.assertRaises(HalError):
            lib_speaker.melody_pcm([(440, 0)])


class Play(unittest.TestCase):
    def test_tone(self):
        path = str(TMP / "tone-test.raw")
        with mock.patch.object(lib_speaker.hal_speaker, "play",
                               return_value=10) as play, \
                mock.patch.object(lib_speaker.hal_speaker, "wait",
                                  return_value=True) as wait:
            result = lib_speaker.tone(1000, 0.1, path=path)
        self.assertEqual(result, path)
        play.assert_called_once_with(path, sink="master", raw=True,
                                     rate=16000, channels=1)
        wait.assert_called_once()
        self.assertTrue(Path(path).exists())
        Path(path).unlink()

    def test_tone_removes_tmp_on_error(self):
        path = str(TMP / "tone-error.raw")
        with mock.patch.object(lib_speaker, "RAW", path), \
                mock.patch.object(lib_speaker.hal_speaker, "play",
                                  side_effect=HalError("нет sink")):
            with self.assertRaises(HalError):
                lib_speaker.tone(440, 0.05)
        self.assertFalse(Path(path).exists())

    def test_tone_without_wait(self):
        path = str(TMP / "tone-test2.raw")
        with mock.patch.object(lib_speaker.hal_speaker, "play"), \
                mock.patch.object(lib_speaker.hal_speaker, "wait") as wait:
            lib_speaker.tone(1000, 0.1, path=path, wait=False)
        wait.assert_not_called()
        Path(path).unlink()

    def test_tone_removes_tmp(self):
        with mock.patch.object(lib_speaker.hal_speaker, "play"), \
                mock.patch.object(lib_speaker.hal_speaker, "wait"):
            path = lib_speaker.tone(1000, 0.05)
        self.assertEqual(path, lib_speaker.RAW)
        self.assertFalse(Path(path).exists())

    def test_silence(self):
        path = str(TMP / "silence-test.raw")
        with mock.patch.object(lib_speaker.hal_speaker, "play"), \
                mock.patch.object(lib_speaker.hal_speaker, "wait"):
            lib_speaker.silence(0.05, path=path)
        self.assertEqual(set(samples(open(path, "rb").read())), {0})
        Path(path).unlink()

    def test_melody(self):
        path = str(TMP / "melody-test.raw")
        with mock.patch.object(lib_speaker.hal_speaker, "play"), \
                mock.patch.object(lib_speaker.hal_speaker, "wait") as wait:
            lib_speaker.melody([(440, 100), (0, 50)], path=path)
        self.assertTrue(Path(path).exists())
        self.assertAlmostEqual(wait.call_args[0][0], 0.15 + 3.0, places=3)
        Path(path).unlink()

    def test_play_wav(self):
        with mock.patch.object(lib_speaker.hal_speaker, "play",
                               return_value=5) as play, \
                mock.patch.object(lib_speaker.hal_speaker, "wait") as wait:
            self.assertEqual(lib_speaker.play_wav("/tmp/a.wav"), 5)
        play.assert_called_once_with("/tmp/a.wav", sink="master", raw=False)
        wait.assert_not_called()

    def test_play_wav_wait(self):
        with mock.patch.object(lib_speaker.hal_speaker, "play",
                               return_value=5), \
                mock.patch.object(lib_speaker.hal_speaker, "wait") as wait:
            self.assertEqual(lib_speaker.play_wav("/tmp/a.wav", wait=True), 5)
        wait.assert_called_once_with(None)

    def test_stop_and_playing(self):
        with mock.patch.object(lib_speaker.hal_speaker, "stop",
                               return_value=True) as stop:
            self.assertTrue(lib_speaker.stop())
        stop.assert_called_once_with()
        with mock.patch.object(lib_speaker.hal_speaker, "running",
                               return_value=7):
            self.assertEqual(lib_speaker.playing(), 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
