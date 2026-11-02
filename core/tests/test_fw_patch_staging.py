#!/usr/bin/env python3
"""Тесты атомарной сборки патчей через `patched/parts_bad`."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fw_patch_lite as cli  # noqa: E402
from fwpatch.errors import PatchError  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)


class FakeTree:
    def __init__(self, changed: bool = True):
        self.changed = changed
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        if not self.changed:
            return {"x": 1}
        return {"x": 1} if self.calls == 1 else {"x": 2}

    def write(self, path):
        Path(path).write_bytes(b"tar")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.image = self.src / "system_b.bin"
        self.image.write_bytes(b"image")
        self.out = self.root / "parts"

    def tearDown(self):
        self._tmp.cleanup()

    def args(self):
        return cli.build_parser().parse_args([
            "--src", str(self.src),
            "--out", str(self.out),
            "--adb-on",
        ])

    def run_patch(self, changed=True, pack=None, swap=None, archive=None):
        tree = FakeTree(changed)

        def fake_unpack(image, part, out, *, force=False):
            Path(out).write_bytes(b"tar")
            return Path(out)

        def fake_pack(tar, final, *, compr="zlib", expected=None,
                      force=False):
            if pack is not None:
                return pack(tar, final, compr=compr, expected=expected,
                            force=force)
            Path(final).write_bytes(b"image")
            return Path(final)

        def fake_save(folder, statuses):
            Path(folder, "status.txt").write_text("ok", encoding="utf-8")

        def fake_status(part, name, image, tree_, params):
            return SimpleNamespace(part=part, file=name)

        patches = [
            mock.patch.object(cli, "load_status", return_value={}),
            mock.patch.object(cli, "resolve_input", return_value=self.image),
            mock.patch.object(cli.checks, "validate_image",
                              return_value={"vol_name": "rootfs",
                                            "size": 1}),
            mock.patch.object(cli, "TarTree", lambda path: tree),
            mock.patch.object(cli, "apply_part"),
            mock.patch.object(cli, "compare_status"),
            mock.patch.object(cli.status, "detect",
                              return_value=({"adb": "on"}, {})),
            mock.patch.object(cli, "output_name",
                              return_value="system_b.adb.bin"),
            mock.patch.object(cli.build, "unpack", side_effect=fake_unpack),
            mock.patch.object(cli.build, "pack", side_effect=fake_pack),
            mock.patch.object(cli.status, "make_status",
                              side_effect=fake_status),
            mock.patch.object(cli, "save_status", side_effect=fake_save),
            redirect_stdout(io.StringIO()),
        ]
        if swap is not None:
            patches.append(mock.patch.object(
                cli, "swap_staging", side_effect=swap))
        if archive is not None:
            patches.append(mock.patch.object(
                cli, "archive_folder", archive))
        with ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            return cli.run_patch(self.args())


class Staging(Base):
    def test_staging_name(self):
        self.assertEqual(cli.staging_for(self.out),
                         self.out.with_name("parts_bad"))

    def test_success_swaps_and_archives_old(self):
        self.out.mkdir()
        (self.out / "old.bin").write_bytes(b"old")
        code = self.run_patch()
        files = sorted(path.name for path in self.out.iterdir())
        archives = list(self.root.glob("parts_*.zip"))
        self.assertEqual(code, 0)
        self.assertEqual(files, ["status.txt", "system_b.adb.bin",
                                 "system_b.tar"])
        self.assertEqual(len(archives), 1)
        self.assertFalse((self.root / "parts_bad").exists())

    def test_no_changes_keeps_old(self):
        (self.src / "status.txt").write_text("old")
        self.out.mkdir()
        (self.out / "old.bin").write_bytes(b"old")
        code = self.run_patch(changed=False)
        files = sorted(path.name for path in self.out.iterdir())
        self.assertEqual(code, 0)
        self.assertEqual(files, ["old.bin"])
        self.assertFalse((self.root / "parts_bad").exists())
        self.assertEqual(list(self.root.glob("parts_*.zip")), [])

    def test_failure_keeps_old_and_removes_staging(self):
        self.out.mkdir()
        (self.out / "old.bin").write_bytes(b"old")

        def fail(*args, **kwargs):
            raise PatchError("boom")

        with self.assertRaises(PatchError):
            self.run_patch(pack=fail)
        self.assertTrue((self.out / "old.bin").exists())
        self.assertFalse((self.root / "parts_bad").exists())
        self.assertEqual(list(self.root.glob("parts_*.zip")), [])

    def test_in_place_does_not_stage(self):
        (self.src / "old.bin").write_bytes(b"old")
        self.out = self.src
        code = self.run_patch()
        self.assertEqual(code, 0)
        self.assertTrue((self.src / "old.bin").exists())
        self.assertTrue((self.src / "system_b.adb.bin").exists())
        self.assertFalse((self.root / "src_bad").exists())

    def test_swap_failure_keeps_both(self):
        self.out.mkdir()
        (self.out / "old.bin").write_bytes(b"old")

        def fail(*args, **kwargs):
            raise OSError("нет места")

        code = self.run_patch(swap=fail)
        self.assertEqual(code, 1)
        self.assertTrue((self.out / "old.bin").exists())
        self.assertTrue(
            (self.root / "parts_bad" / "system_b.adb.bin").exists())
        self.assertTrue(
            (self.root / "parts_bad" / "status.txt").exists())

    def test_archive_failure_keeps_both(self):
        self.out.mkdir()
        (self.out / "old.bin").write_bytes(b"old")

        def fail(*args, **kwargs):
            raise OSError("нет места")

        code = self.run_patch(archive=fail)
        self.assertEqual(code, 1)
        self.assertTrue((self.out / "old.bin").exists())
        self.assertTrue(
            (self.root / "parts_bad" / "system_b.adb.bin").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
