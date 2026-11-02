#!/usr/bin/env python3
"""Тесты `common.tar_ubi`: список UBI и имена tar."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import tar_ubi  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

UBI = b"UBI#" + b"\0" * 12


class Names(unittest.TestCase):
    def test_part_of(self):
        self.assertEqual(tar_ubi.part_of(Path("system_b.bin")), "system_b")
        self.assertEqual(
            tar_ubi.part_of(Path("system_b.adb-ssh.bin")), "system_b")
        self.assertEqual(tar_ubi.part_of(Path("data.lapi.bin")), "data")

    def test_tar_for(self):
        self.assertEqual(tar_ubi.tar_for(Path("a/system_b.bin")),
                         Path("a/system_b.tar"))
        self.assertEqual(
            tar_ubi.tar_for(Path("a/system_b.adb-ssh.bin")),
            Path("a/system_b.adb-ssh.tar"))

    def test_image_for_tar(self):
        self.assertEqual(
            tar_ubi.image_for_tar(Path("a/system_b.adb-ssh.tar")),
            Path("a/system_b.adb-ssh.bin"))

    def test_is_ubi(self):
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            good = Path(tmp) / "good.bin"
            bad = Path(tmp) / "bad.bin"
            good.write_bytes(UBI)
            bad.write_bytes(b"ANDR")
            self.assertTrue(tar_ubi.is_ubi(good))
            self.assertFalse(tar_ubi.is_ubi(bad))
            self.assertFalse(tar_ubi.is_ubi(Path(tmp) / "nope.bin"))


class Listing(unittest.TestCase):
    def test_order_and_filter(self):
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            root = Path(tmp)
            backup = root / "backup"
            patched = root / "patched"
            backup.mkdir()
            patched.mkdir()
            (backup / "boot_a.bin").write_bytes(b"ANDR")
            (backup / "data.bin").write_bytes(UBI)
            (backup / "misc.bin").write_bytes(b"\xff" * 16)
            (backup / "system_b.bin").write_bytes(UBI)
            (patched / "data.lapi.bin").write_bytes(UBI)
            (patched / "system_b.adb.bin").write_bytes(UBI)

            images = tar_ubi.list_images((backup, patched))
            names = [image.path.name for image in images]
            self.assertEqual(names, [
                "data.bin", "system_b.bin",
                "data.lapi.bin", "system_b.adb.bin",
            ])
            self.assertEqual([image.folder for image in images],
                             [backup, backup, patched, patched])
            self.assertEqual(images[-1].part, "system_b")
            self.assertEqual(images[-1].tar.name, "system_b.adb.tar")

    def test_unpack_uses_image_name(self):
        image = Path("/x/system_b.adb.bin")
        with mock.patch("fwpatch.build.unpack",
                        return_value=Path("/x/system_b.adb.tar")) as unpack:
            result = tar_ubi.unpack(image, force=True)
        self.assertEqual(result, Path("/x/system_b.adb.tar"))
        unpack.assert_called_once_with(
            image, "system_b", Path("/x/system_b.adb.tar"), force=True)

    def test_unpack_details(self):
        image = Path("/x/system_b.bin")
        output = ("записей: файлов 1, каталогов 2, "
                  "симлинков 3, hardlinks 4\n")
        with mock.patch("fwpatch.build.unpack",
                        return_value=(Path("/x/system_b.tar"),
                                      output)) as unpack, \
             mock.patch.object(tar_ubi, "summary",
                               return_value=["том: rootfs"]):
            tar, lines = tar_ubi.unpack_details(image, force=True)
        self.assertEqual(tar, Path("/x/system_b.tar"))
        self.assertEqual(lines, ["том: rootfs"])
        unpack.assert_called_once_with(
            image, "system_b", Path("/x/system_b.tar"),
            force=True, report=True)

    def test_summary(self):
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            image = Path(tmp) / "data.bin"
            image.write_bytes(UBI)
            params = {"vol_name": "data", "peb": 131072,
                      "sb": {"leb_size": 126976, "compr": 2}}
            with mock.patch("common.ubi_check.read_ubi_params",
                            return_value=params):
                lines = tar_ubi.summary(
                    image,
                    "записей: файлов 1, каталогов 2, "
                    "симлинков 3, hardlinks 4")
        self.assertIn("том: data", lines)
        self.assertIn("PEB: 131072, LEB: 126976, сжатие: zlib", lines)
        self.assertIn("записей: файлов 1, каталогов 2, "
                      "симлинков 3, hardlinks 4", lines)


class Tars(unittest.TestCase):
    def test_list_tars_order(self):
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            root = Path(tmp)
            backup = root / "backup"
            patched = root / "patched"
            backup.mkdir()
            patched.mkdir()
            (backup / "data.tar").write_bytes(b"tar")
            (backup / "system_b.tar").write_bytes(b"tar")
            (backup / "not.tar.json").write_bytes(b"json")
            (patched / "data.lapi.tar").write_bytes(b"tar")

            files = tar_ubi.list_tars((backup, patched))
            self.assertEqual([item.path.name for item in files],
                             ["data.tar", "system_b.tar", "data.lapi.tar"])
            self.assertEqual([item.folder for item in files],
                             [backup, backup, patched])
            self.assertEqual(files[-1].image.name, "data.lapi.bin")

    def test_compression(self):
        for code, expected in ((0, "none"), (1, "lzo"), (2, "zlib")):
            with mock.patch("fwpatch.tar_tree.TarTree") as tree:
                tree.return_value.meta.return_value = {"compr": code}
                self.assertEqual(tar_ubi.compression_for(Path("x.tar")),
                                 (expected, None))
        with mock.patch("fwpatch.tar_tree.TarTree") as tree:
            tree.return_value.meta.return_value = {"compr": 3}
            self.assertEqual(tar_ubi.compression_for(Path("x.tar")),
                             ("zlib", "zstd заменён на zlib: "
                                      "ядро 4.9 не читает"))

    def test_pack(self):
        tar = Path("/x/data.tar")
        with mock.patch.object(tar_ubi, "compression_for",
                               return_value=("lzo", None)), \
             mock.patch("fwpatch.build.pack",
                        return_value=Path("/x/data.bin")) as pack:
            image, warning = tar_ubi.pack(tar, force=True)
        self.assertEqual(image, Path("/x/data.bin"))
        self.assertIsNone(warning)
        pack.assert_called_once_with(tar, Path("/x/data.bin"),
                                     compr="lzo", force=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
