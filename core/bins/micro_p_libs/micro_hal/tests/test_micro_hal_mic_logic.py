#!/usr/bin/env python3
"""Тесты micro_hal: WAV и уровни без платы."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TMP = REPO / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

from micro_hal import HalError, lib_mic  # noqa: E402


def pcm(values):
    return struct.pack("<%dh" % len(values), *values)


class Header(unittest.TestCase):
    def test_header(self):
        header = lib_mic.wav_header(1000)
        self.assertEqual(len(header), 44)
        self.assertEqual(header[:4], b"RIFF")
        self.assertEqual(struct.unpack("<I", header[4:8])[0], 1036)
        self.assertEqual(header[8:12], b"WAVE")
        self.assertEqual(header[12:16], b"fmt ")
        self.assertEqual(struct.unpack("<I", header[16:20])[0], 16)
        self.assertEqual(struct.unpack("<H", header[20:22])[0], 1)
        self.assertEqual(struct.unpack("<H", header[22:24])[0], 4)
        self.assertEqual(struct.unpack("<I", header[24:28])[0], 16000)
        self.assertEqual(struct.unpack("<I", header[28:32])[0], 128000)
        self.assertEqual(struct.unpack("<H", header[32:34])[0], 8)
        self.assertEqual(struct.unpack("<H", header[34:36])[0], 16)
        self.assertEqual(header[36:40], b"data")
        self.assertEqual(struct.unpack("<I", header[40:44])[0], 1000)

    def test_bad_header(self):
        with self.assertRaises(HalError):
            lib_mic.wav_header(-1)
        with self.assertRaises(HalError):
            lib_mic.wav_header(0, channels=0)


class Levels(unittest.TestCase):
    def test_level(self):
        data = pcm([1000] * 10)
        self.assertAlmostEqual(lib_mic.level(data), 1000 / 32768)

    def test_level_empty(self):
        self.assertEqual(lib_mic.level(b""), 0.0)

    def test_level_odd(self):
        data = pcm([1000]) + b"\x00"
        self.assertAlmostEqual(lib_mic.level(data), 1000 / 32768)

    def test_levels(self):
        data = pcm([1000, -2000, 3000, -4000] * 2)
        values = lib_mic.levels(data)
        self.assertEqual(len(values), 4)
        self.assertAlmostEqual(values[0], 1000 / 32768)
        self.assertAlmostEqual(values[1], 2000 / 32768)
        self.assertAlmostEqual(values[2], 3000 / 32768)
        self.assertAlmostEqual(values[3], 4000 / 32768)

    def test_peak(self):
        data = pcm([100, -4000, 2000, 0])
        self.assertAlmostEqual(lib_mic.peak(data), 4000 / 32768)

    def test_bad_channels(self):
        with self.assertRaises(HalError):
            lib_mic.level(b"", channels=0)


class Mono(unittest.TestCase):
    def test_mono(self):
        data = pcm([100, 200, 300, 400])
        result = struct.unpack("<1h", lib_mic.mono(data))[0]
        self.assertEqual(result, 250)

    def test_mono_stereo(self):
        data = pcm([100, 300, -100, -300])
        result = struct.unpack("<2h", lib_mic.mono(data, channels=2))
        self.assertEqual(result, (200, -200))

    def test_mono_passthrough(self):
        data = pcm([1, 2, 3])
        self.assertEqual(lib_mic.mono(data, channels=1), data)


class Record(unittest.TestCase):
    def test_record(self):
        raw = str(TMP / "lib_mic_raw.raw")
        target = TMP / "lib_mic_out.wav"
        payload = pcm([1, 2, 3, 4] * 10)

        def fake_capture(path, seconds, **kwargs):
            Path(path).write_bytes(payload)

        try:
            with mock.patch.object(lib_mic, "RAW", raw), \
                    mock.patch.object(
                        lib_mic.hal_mic, "capture",
                        side_effect=fake_capture):
                self.assertEqual(
                    lib_mic.record(str(target), 1), str(target))
            data = target.read_bytes()
            self.assertEqual(data[:4], b"RIFF")
            self.assertEqual(struct.unpack("<I", data[40:44])[0],
                             len(payload))
            self.assertEqual(data[44:], payload)
            self.assertFalse(Path(raw).exists())
        finally:
            if target.exists():
                target.unlink()
            if Path(raw).exists():
                Path(raw).unlink()

    def test_record_same_path(self):
        with self.assertRaises(HalError):
            lib_mic.record(lib_mic.RAW, 1)

    def test_record_bad_folder(self):
        raw = str(TMP / "lib_mic_raw2.raw")
        payload = pcm([1, 2, 3, 4])

        def fake_capture(path, seconds, **kwargs):
            Path(path).write_bytes(payload)

        try:
            with mock.patch.object(lib_mic, "RAW", raw), \
                    mock.patch.object(
                        lib_mic.hal_mic, "capture",
                        side_effect=fake_capture):
                with self.assertRaises(HalError):
                    lib_mic.record(
                        str(TMP / "no-such-dir" / "out.wav"), 1)
            self.assertFalse(Path(raw).exists())
        finally:
            if Path(raw).exists():
                Path(raw).unlink()


class Separated(unittest.TestCase):
    """`direction`/`tracks` — в test_micro_hal_mic_odas.py."""

    def test_separate(self):
        with self.assertRaises(HalError):
            lib_mic.separate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
