#!/usr/bin/env python3
"""Тесты `fwpatch.tar_tree`: чтение, правка, запись, метаданные."""

from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fwpatch.errors import PatchError  # noqa: E402
from fwpatch.tar_tree import TarTree, diff  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)


def add(tf, name, *, kind=tarfile.REGTYPE, data=None, mode=0o644,
        uid=0, gid=0, mtime=0, linkname=""):
    info = tarfile.TarInfo(name)
    info.type = kind
    info.mode = mode
    info.uid = uid
    info.gid = gid
    info.mtime = mtime
    info.linkname = linkname
    if data is not None:
        info.size = len(data)
    tf.addfile(info, io.BytesIO(data) if data is not None else None)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)
        self.src = self.dir / "in.tar"
        with tarfile.open(self.src, "w", format=tarfile.GNU_FORMAT) as tf:
            add(tf, ".ubitar/ubi.json",
                data=b'{"volume": "rootfs"}')
            add(tf, "etc", kind=tarfile.DIRTYPE, mode=0o755,
                uid=10, gid=20, mtime=111)
            add(tf, "etc/init.d", kind=tarfile.DIRTYPE, mode=0o755,
                uid=10, gid=20, mtime=111)
            add(tf, "etc/a.txt", data=b"old", mode=0o600,
                uid=10, gid=20, mtime=111)
            add(tf, "etc/link", kind=tarfile.SYMTYPE, mode=0o777,
                uid=10, gid=20, mtime=111, linkname="a.txt")
            add(tf, "etc/hard", kind=tarfile.LNKTYPE, mode=0o600,
                uid=10, gid=20, mtime=111, linkname="etc/a.txt")

    def tearDown(self):
        self._tmp.cleanup()


class Read(Base):
    def test_kinds(self):
        tree = TarTree(self.src)
        self.assertEqual(tree.kind("etc"), "dir")
        self.assertEqual(tree.kind("etc/a.txt"), "file")
        self.assertEqual(tree.kind("etc/link"), "link")
        self.assertEqual(tree.kind("etc/hard"), "hardlink")
        self.assertIsNone(tree.kind("nope"))

    def test_read_and_sha(self):
        tree = TarTree(self.src)
        self.assertEqual(tree.read("etc/a.txt"), b"old")
        self.assertEqual(tree.read("etc/hard"), b"old")
        self.assertEqual(len(tree.sha256("etc/a.txt")), 64)

    def test_meta(self):
        self.assertEqual(TarTree(self.src).meta(), {"volume": "rootfs"})

    def test_link_target(self):
        tree = TarTree(self.src)
        self.assertEqual(tree.link_target("etc/link"), "a.txt")
        self.assertIsNone(tree.link_target("etc/a.txt"))
        self.assertIsNone(tree.link_target("nope"))

    def test_read_dir_fails(self):
        with self.assertRaises(PatchError):
            TarTree(self.src).read("etc")

    def test_missing_read_fails(self):
        with self.assertRaises(PatchError):
            TarTree(self.src).read("nope")


class Edit(Base):
    def test_edit_and_write(self):
        tree = TarTree(self.src)
        before = tree.snapshot()

        tree.replace("etc/a.txt", b"new", 0o644)
        tree.add("etc/init.d/S91.sh", b"#!/bin/sh\n", 0o755)
        tree.add("opt/lapi", b"on", 0o644)
        tree.remove("etc/link")
        after = tree.snapshot()

        added, removed, changed = diff(before, after)
        self.assertEqual(removed, {"etc/link"})
        self.assertEqual(changed, {"etc/a.txt"})
        self.assertEqual(added, {"etc/init.d/S91.sh", "opt", "opt/lapi"})

        out = self.dir / "out.tar"
        tree.write(out)

        new = TarTree(out)
        self.assertEqual(new.read("etc/a.txt"), b"new")
        self.assertEqual(new.read("opt/lapi"), b"on")
        self.assertEqual(new.meta(), {"volume": "rootfs"})
        self.assertFalse(new.exists("etc/link"))
        self.assertEqual(new.kind("opt"), "dir")
        self.assertEqual(new.kind("etc/hard"), "hardlink")

        info = new._by_path["etc/a.txt"]
        self.assertEqual(info.mode, 0o644)
        self.assertEqual((info.uid, info.gid), (10, 20))
        added_info = new._by_path["etc/init.d/S91.sh"]
        self.assertEqual(added_info.mode, 0o755)
        self.assertEqual((added_info.uid, added_info.gid), (0, 0))
        self.assertEqual(new._by_path["etc/hard"].linkname, "etc/a.txt")

    def test_symlink_add_and_write(self):
        tree = TarTree(self.src)
        tree.remove("etc/a.txt")
        tree.symlink("etc/a.txt", "b.txt")
        tree.symlink("opt/scp", "../dropbear")

        self.assertEqual(tree.kind("etc/a.txt"), "link")
        self.assertEqual(tree.link_target("etc/a.txt"), "b.txt")
        self.assertEqual(tree.link_target("opt/scp"), "../dropbear")

        out = self.dir / "links.tar"
        tree.write(out)
        new = TarTree(out)
        self.assertEqual(new.kind("etc/a.txt"), "link")
        self.assertEqual(new.link_target("etc/a.txt"), "b.txt")
        self.assertEqual(new.link_target("opt/scp"), "../dropbear")
        info = new._by_path["opt/scp"]
        self.assertTrue(info.issym())
        self.assertEqual(info.linkname, "../dropbear")

    def test_add_existing_fails(self):
        with self.assertRaises(PatchError):
            TarTree(self.src).add("etc/a.txt", b"x")

    def test_replace_missing_fails(self):
        with self.assertRaises(PatchError):
            TarTree(self.src).replace("nope", b"x")

    def test_remove_missing_fails(self):
        with self.assertRaises(PatchError):
            TarTree(self.src).remove("nope")

    def test_capsula_is_protected(self):
        tree = TarTree(self.src)
        with self.assertRaises(PatchError):
            tree.add(".ubitar/other", b"x")
        with self.assertRaises(PatchError):
            tree.replace(".ubitar/ubi.json", b"x")
        with self.assertRaises(PatchError):
            tree.remove(".ubitar/ubi.json")

    def test_write_same_path_fails(self):
        with self.assertRaises(PatchError):
            TarTree(self.src).write(self.src)

    def test_ensure_dir_on_file_fails(self):
        tree = TarTree(self.src)
        with self.assertRaises(PatchError):
            tree.ensure_dir("etc/a.txt")

    def test_ensure_dir_idempotent(self):
        tree = TarTree(self.src)
        tree.ensure_dir("etc")
        tree.ensure_dir("etc")
        self.assertEqual(tree.kind("etc"), "dir")


if __name__ == "__main__":
    unittest.main(verbosity=2)
