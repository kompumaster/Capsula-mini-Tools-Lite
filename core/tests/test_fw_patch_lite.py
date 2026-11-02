#!/usr/bin/env python3
"""Тесты CLI `fw_patch_lite`: имена, статус, флаги, файлы."""

from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fw_patch_lite as cli  # noqa: E402
from fwpatch import status  # noqa: E402
from fwpatch.errors import PatchError  # noqa: E402
from fwpatch.patches import (  # noqa: E402
    patch_adb, patch_mpython, patch_ssh, patch_telemetryd,
    patch_vkkill, patch_vkvoice,
)
from fwpatch.tar_tree import TarTree  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)


def make_tar(path: Path, entries=()):
    with tarfile.open(path, "w", format=tarfile.GNU_FORMAT) as tf:
        info = tarfile.TarInfo(".ubitar/ubi.json")
        info.size = 2
        tf.addfile(info, io.BytesIO(b"{}"))
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.mode = 0o755
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def tree(self, entries=()) -> TarTree:
        path = self.dir / "part.tar"
        make_tar(path, entries)
        return TarTree(path)


class Names(Base):
    def test_stock_system_b(self):
        tree = self.tree([
            ("usr/bin/telemetryd", b"orig"),
            ("usr/bin/fwupdater", b"orig"),
            ("usr/bin/swupdate", b"orig"),
        ])
        self.assertEqual(cli.output_name("system_b", tree), "system_b.bin")

    def test_patched_system_b(self):
        tree = self.tree([
            ("usr/bin/telemetryd", b"orig"),
            ("usr/bin/fwupdater", b"orig"),
            ("usr/bin/swupdate", b"orig"),
        ])
        patch_adb.apply(tree)
        patch_ssh.apply(tree)
        patch_telemetryd.kill(tree)
        self.assertEqual(
            cli.output_name("system_b", tree),
            "system_b.adb-ssh-tele.bin")

    def test_vkvoice(self):
        tree = self.tree([(patch_vkvoice.PATH, b"script")])
        patch_vkvoice.apply(tree)
        self.assertEqual(cli.output_name("system_b", tree),
                         "system_b.vkvoice.bin")

    def test_vkkill(self):
        tree = self.tree([(patch_vkkill.PATH, b"orig")])
        patch_vkkill.kill(tree)
        self.assertEqual(cli.output_name("system_b", tree),
                         "system_b.vkkill.bin")

    def test_mpython(self):
        tree = self.tree()
        patch_mpython.apply(tree)
        self.assertEqual(cli.output_name("data", tree), "data.mpython.bin")

    def test_data(self):
        tree = self.tree()
        self.assertEqual(cli.output_name("data", tree), "data.bin")
        tree.add("permanent/lapi", b"on", 0o644)
        self.assertEqual(cli.output_name("data", tree), "data.lapi.bin")


class Inputs(Base):
    def test_direct(self):
        path = self.dir / "system_b.bin"
        path.write_bytes(b"x")
        self.assertEqual(cli.resolve_input(self.dir, "system_b", {}), path)

    def test_from_status(self):
        path = self.dir / "system_b.adb.bin"
        path.write_bytes(b"x")
        data = {"system_b.file": "system_b.adb.bin"}
        self.assertEqual(cli.resolve_input(self.dir, "system_b", data), path)

    def test_missing(self):
        with self.assertRaises(PatchError):
            cli.resolve_input(self.dir, "system_b", {})

    def test_subdir_rejected(self):
        data = {"system_b.file": "sub/system_b.bin"}
        with self.assertRaises(PatchError):
            cli.resolve_input(self.dir, "system_b", data)


class StatusFile(Base):
    def test_merge(self):
        data_status = status.Status(
            part="data", file="data.lapi.bin", size=1,
            sha256="d" * 64, compr="zlib",
            states={"lapi": "on"},
            hashes={"lapi": {"permanent/lapi": "e" * 64}},
        )
        status.write_status(self.dir / "status.txt", [data_status])

        system_status = status.Status(
            part="system_b", file="system_b.adb.bin", size=2,
            sha256="a" * 64, compr="zlib",
            states={"adb": "on"}, hashes={},
        )
        cli.save_status(self.dir, [system_status])
        text = (self.dir / "status.txt").read_text()
        self.assertIn("data.file=data.lapi.bin", text)
        self.assertIn("data.lapi=on", text)
        self.assertIn("system_b.file=system_b.adb.bin", text)
        self.assertIn("system_b.adb=on", text)


class Flags(unittest.TestCase):
    parser = cli.build_parser()

    def args(self, *argv):
        return self.parser.parse_args(["--src", "src", *argv])

    def test_none(self):
        with self.assertRaises(PatchError):
            cli.validate(self.args())

    def test_status_with_patch(self):
        with self.assertRaises(PatchError):
            cli.validate(self.args("--status", "--adb-on"))

    def test_out_required(self):
        with self.assertRaises(PatchError):
            cli.validate(self.args("--adb-on"))

    def test_flag_without_parts(self):
        args = self.args("--adb-on", "--out", "o")
        with mock.patch.object(cli, "BY_PART",
                               {"system_b": (), "data": ()}):
            with self.assertRaises(PatchError):
                cli.validate(args)

    def test_on_off(self):
        with self.assertRaises(PatchError):
            cli.validate(self.args("--adb-on", "--adb-off", "--out", "o"))

    def test_lzo_zstd(self):
        with self.assertRaises(PatchError):
            cli.validate(self.args("--adb-on", "--out", "o",
                                   "--lzo", "--zstd"))

    def test_parts(self):
        args = self.args("--adb-on", "--lapi-on", "--out", "o")
        self.assertEqual(cli.needed_parts(args), ["system_b", "data"])

    def test_compression(self):
        self.assertEqual(cli.compression(self.args("--adb-on", "--out", "o",
                                                   "--lzo")), "lzo")


class Compare(Base):
    def test_mismatch_declined(self):
        tree = self.tree([("usr/bin/telemetryd", b"orig")])
        data = {"system_b.tele": "off"}
        with mock.patch.object(cli, "ask", return_value=False):
            with self.assertRaises(PatchError):
                cli.compare_status(data, "system_b",
                                   self.dir / "system_b.bin", tree)

    def test_mismatch_accepted(self):
        tree = self.tree([("usr/bin/telemetryd", b"orig")])
        data = {"system_b.tele": "off"}
        with mock.patch.object(cli, "ask", return_value=True):
            cli.compare_status(data, "system_b",
                               self.dir / "system_b.bin", tree)


if __name__ == "__main__":
    unittest.main(verbosity=2)
