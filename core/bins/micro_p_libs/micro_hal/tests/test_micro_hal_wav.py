#!/usr/bin/env python3
"""Тесты micro_hal: WAV-заголовок без платы."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from micro_hal import HalError, lib_mic, lib_wav  # noqa: E402


class Header(unittest.TestCase):
    def test_mono(self):
        header = lib_wav.wav_header(32000)
        self.assertEqual(len(header), lib_wav.HEADER_SIZE)
        self.assertEqual(header[:4], b"RIFF")
        self.assertEqual(struct.unpack("<I", header[4:8])[0], 32036)
        self.assertEqual(header[8:16], b"WAVEfmt ")
        self.assertEqual(struct.unpack("<H", header[22:24])[0], 1)
        self.assertEqual(struct.unpack("<I", header[24:28])[0], 16000)
        self.assertEqual(struct.unpack("<I", header[28:32])[0], 32000)
        self.assertEqual(struct.unpack("<H", header[32:34])[0], 2)
        self.assertEqual(struct.unpack("<H", header[34:36])[0], 16)
        self.assertEqual(header[36:40], b"data")
        self.assertEqual(struct.unpack("<I", header[40:44])[0], 32000)

    def test_stereo_48k(self):
        header = lib_wav.wav_header(1000, channels=2, rate=48000)
        self.assertEqual(struct.unpack("<H", header[22:24])[0], 2)
        self.assertEqual(struct.unpack("<I", header[24:28])[0], 48000)
        self.assertEqual(struct.unpack("<I", header[28:32])[0], 192000)
        self.assertEqual(struct.unpack("<H", header[32:34])[0], 4)

    def test_width(self):
        header = lib_wav.wav_header(10, channels=1, rate=8000, width=1)
        self.assertEqual(struct.unpack("<H", header[34:36])[0], 8)
        self.assertEqual(struct.unpack("<I", header[28:32])[0], 8000)

    def test_zero_size(self):
        header = lib_wav.wav_header(0)
        self.assertEqual(len(header), 44)

    def test_bad(self):
        with self.assertRaises(HalError):
            lib_wav.wav_header(-1)
        with self.assertRaises(HalError):
            lib_wav.wav_header(10, channels=0)
        with self.assertRaises(HalError):
            lib_wav.wav_header(10, rate=0)
        with self.assertRaises(HalError):
            lib_wav.wav_header(10, width=0)


class MicDefaults(unittest.TestCase):
    def test_mic_header_is_4ch(self):
        header = lib_mic.wav_header(1000)
        self.assertEqual(struct.unpack("<H", header[22:24])[0], 4)
        self.assertEqual(struct.unpack("<I", header[24:28])[0], 16000)
        self.assertEqual(struct.unpack("<I", header[28:32])[0], 128000)
        self.assertEqual(len(header), 44)

    def test_mic_matches_shared(self):
        self.assertEqual(lib_mic.wav_header(500, channels=1, rate=8000),
                         lib_wav.wav_header(500, channels=1, rate=8000))


if __name__ == "__main__":
    unittest.main(verbosity=2)
