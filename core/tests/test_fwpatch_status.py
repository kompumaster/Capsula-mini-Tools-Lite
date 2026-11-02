#!/usr/bin/env python3
"""Тесты `fwpatch.status`: on/off, хеши, status.txt."""

from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fwpatch import assets  # noqa: E402
from fwpatch.errors import PatchError  # noqa: E402
from fwpatch.patches import patch_lapi  # noqa: E402
from fwpatch.status import (  # noqa: E402
    Status, compr_name, detect, file_map, make_status,
    parse_status, read_status, render, sha256_file, write_status,
)
from fwpatch.tar_tree import TarTree  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

ADBD = (assets.BINS / "adbd").read_bytes()
S91 = (assets.BINS / "S91adbd.sh").read_bytes()
DROPBEAR = (assets.BINS / "dropbear").read_bytes()
DROPBEARKEY = (assets.BINS / "dropbearkey").read_bytes()
S90 = (assets.BINS / "S90dropbear").read_bytes()
NOOP = (assets.STUBS / "noop").read_bytes()


def make_tar(path: Path, entries: list[tuple[str, bytes, int]]):
    with tarfile.open(path, "w", format=tarfile.GNU_FORMAT) as tf:
        info = tarfile.TarInfo(".ubitar/ubi.json")
        info.size = 2
        tf.addfile(info, io.BytesIO(b"{}"))
        for name, data, mode in entries:
            info = tarfile.TarInfo(name)
            info.mode = mode
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def tar(self, entries) -> TarTree:
        path = self.dir / "part.tar"
        make_tar(path, entries)
        return TarTree(path)


class DetectSystemB(Base):
    def test_stock(self):
        tree = self.tar([
            ("usr/bin/telemetryd", b"orig-tele", 0o755),
            ("usr/bin/fwupdater", b"orig-fwu", 0o755),
            ("usr/bin/swupdate", b"orig-swu", 0o755),
        ])
        states, hashes = detect(tree, "system_b")
        self.assertEqual(states, {
            "adb": "off", "ssh": "off", "vkvoice": "off",
            "tele": "on", "fwu": "on", "swu": "on", "vkkill": "off",
        })
        self.assertNotIn("adb", hashes)
        self.assertNotIn("ssh", hashes)

    def test_patched(self):
        tree = self.tar([
            ("usr/bin/telemetryd", b"orig-tele", 0o755),
            ("usr/bin/fwupdater", b"orig-fwu", 0o755),
            ("usr/bin/swupdate", b"orig-swu", 0o755),
        ])
        tree.add("usr/bin/adbd-tcp", ADBD, 0o755)
        tree.add("etc/init.d/S91adbd.sh", S91, 0o755)
        tree.add("usr/bin/dropbear", DROPBEAR, 0o755)
        tree.add("usr/bin/dropbearkey", DROPBEARKEY, 0o755)
        tree.add("etc/init.d/S90dropbear", S90, 0o755)
        tree.replace("usr/bin/telemetryd", NOOP, 0o755)
        tree.replace("usr/bin/swupdate", NOOP, 0o755)

        states, hashes = detect(tree, "system_b")
        self.assertEqual(states, {
            "adb": "on", "ssh": "on", "vkvoice": "off",
            "tele": "off", "fwu": "on", "swu": "off", "vkkill": "off",
        })
        self.assertEqual(set(hashes["adb"]), {"adbd-tcp", "S91adbd.sh"})
        self.assertEqual(set(hashes["ssh"]),
                         {"dropbear", "dropbearkey", "S90dropbear"})
        self.assertEqual(set(hashes["tele"]), {"telemetryd"})

    def test_missing_stub_is_off(self):
        tree = self.tar([
            ("usr/bin/fwupdater", b"orig-fwu", 0o755),
        ])
        states, _ = detect(tree, "system_b")
        self.assertEqual(states["tele"], "off")
        self.assertEqual(states["swu"], "off")
        self.assertEqual(states["fwu"], "on")


class DetectData(Base):
    def test_absent(self):
        states, hashes = detect(self.tar([]), "data")
        self.assertEqual(states, {"lapi": "off", "mpython": "off"})
        self.assertEqual(hashes, {})

    def test_on(self):
        tree = self.tar([(patch_lapi.PATH, b"on", 0o644)])
        states, hashes = detect(tree, "data")
        self.assertEqual(states, {"lapi": "on", "mpython": "off"})
        self.assertIn(patch_lapi.PATH, hashes["lapi"])

    def test_other(self):
        tree = self.tar([(patch_lapi.PATH, b"off", 0o644)])
        states, hashes = detect(tree, "data")
        self.assertEqual(states, {"lapi": "off", "mpython": "off"})
        self.assertIn(patch_lapi.PATH, hashes["lapi"])

    def test_unknown_part(self):
        with self.assertRaises(PatchError):
            detect(self.tar([]), "system_a")


class Text(Base):
    def status(self):
        return Status(
            part="system_b",
            file="system_b.adb-ssh.bin",
            size=67108864,
            sha256="a" * 64,
            compr="zlib",
            states={"adb": "on", "ssh": "on", "tele": "off",
                    "fwu": "on", "swu": "off"},
            hashes={"adb": {"adbd-tcp": "b" * 64},
                    "tele": {"telemetryd": "c" * 64}},
        )

    def test_render_parse(self):
        text = render([self.status()])
        self.assertIn("# fw_patch_lite status 1", text)
        self.assertIn("system_b.file=system_b.adb-ssh.bin", text)
        self.assertIn("system_b.adb=on", text)
        self.assertIn("system_b.adb.adbd-tcp.sha256=" + "b" * 64, text)
        self.assertIn("system_b.tele=off", text)
        data = parse_status(text)
        self.assertEqual(data["system_b.adb"], "on")
        self.assertEqual(data["system_b.tele"], "off")
        self.assertEqual(file_map(data),
                         {"system_b": "system_b.adb-ssh.bin"})

    def test_write_read(self):
        path = self.dir / "status.txt"
        write_status(path, [self.status()])
        data = read_status(path)
        self.assertEqual(data["system_b.size"], "67108864")
        self.assertEqual(data["system_b.compr"], "zlib")

    def test_read_cp1251(self):
        path = self.dir / "status.txt"
        path.write_bytes(
            "system_b.file=system_b.bin\n"
            "system_b.tele=off\n".encode("cp1251"))
        data = read_status(path)
        self.assertEqual(data["system_b.file"], "system_b.bin")
        self.assertEqual(data["system_b.tele"], "off")

    def test_read_utf8_bom(self):
        path = self.dir / "status.txt"
        path.write_bytes(
            b"\xef\xbb\xbfsystem_b.file=system_b.bin\n")
        data = read_status(path)
        self.assertEqual(data["system_b.file"], "system_b.bin")

    def test_read_bad_encoding(self):
        path = self.dir / "status.txt"
        path.write_bytes(b"\x98\x98\n")
        with self.assertRaises(PatchError):
            read_status(path)

    def test_compr(self):
        self.assertEqual(compr_name(1), "lzo")
        self.assertEqual(compr_name(2), "zlib")
        self.assertEqual(compr_name(None), "unknown")
        self.assertEqual(compr_name(9), "unknown(9)")

    def test_make_status(self):
        image = self.dir / "system_b.bin"
        image.write_bytes(b"x")
        tree = self.tar([
            ("usr/bin/telemetryd", b"orig", 0o755),
        ])
        status = make_status("system_b", "system_b.bin", image, tree,
                             {"sb": {"compr": 2}})
        self.assertEqual(status.size, 1)
        self.assertEqual(status.compr, "zlib")
        self.assertEqual(status.states["tele"], "on")
        self.assertEqual(sha256_file(image),
                         "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881")

    def test_bad_line(self):
        with self.assertRaises(PatchError):
            parse_status("no equals\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
