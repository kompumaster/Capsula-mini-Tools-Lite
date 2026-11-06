#!/usr/bin/env python3
"""Тесты патчей Lite: lapi, adb, ssh, заглушки."""

from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fwpatch import assets  # noqa: E402
from fwpatch import patches as patches_pkg  # noqa: E402
from fwpatch.errors import PatchError  # noqa: E402
from fwpatch.patches import KILLS, PATCHES, patch_adb, patch_lapi  # noqa: E402
from fwpatch.patches import patch_dnsmasq, patch_home  # noqa: E402
from fwpatch.patches import patch_hostapd, patch_mhal  # noqa: E402
from fwpatch.patches import patch_mtts  # noqa: E402
from fwpatch.patches import patch_mpython  # noqa: E402
from fwpatch.patches import patch_slfchk  # noqa: E402
from fwpatch.patches import patch_ssh  # noqa: E402
from fwpatch.patches import patch_telemetryd  # noqa: E402
from fwpatch.patches import patch_vkcall  # noqa: E402
from fwpatch.patches import patch_vkkill  # noqa: E402
from fwpatch.patches import patch_vkvoice  # noqa: E402
from fwpatch.patches.common import asset_bytes, sha  # noqa: E402
from fwpatch.status import detect  # noqa: E402
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


class Lapi(Base):
    def test_on(self):
        tree = self.tree()
        patch_lapi.apply(tree)
        self.assertEqual(tree.kind(patch_lapi.PATH), "file")
        self.assertEqual(tree.read(patch_lapi.PATH), b"on")
        self.assertEqual(tree.mode(patch_lapi.PATH), 0o644)

    def test_on_twice(self):
        tree = self.tree()
        patch_lapi.apply(tree)
        before = tree.snapshot()
        patch_lapi.apply(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_off(self):
        tree = self.tree([(patch_lapi.PATH, b"on")])
        patch_lapi.remove(tree)
        self.assertFalse(tree.exists(patch_lapi.PATH))

    def test_off_absent(self):
        tree = self.tree()
        patch_lapi.remove(tree)
        self.assertFalse(tree.exists(patch_lapi.PATH))

    def test_conflict_on_declined(self):
        tree = self.tree([(patch_lapi.PATH, b"off")])
        with self.assertRaises(PatchError):
            patch_lapi.apply(tree, ask=lambda q, d: False)
        self.assertEqual(tree.read(patch_lapi.PATH), b"off")

    def test_conflict_on_accepted(self):
        tree = self.tree([(patch_lapi.PATH, b"off")])
        patch_lapi.apply(tree, ask=lambda q, d: True)
        self.assertEqual(tree.read(patch_lapi.PATH), b"on")

    def test_conflict_needs_ask(self):
        tree = self.tree([(patch_lapi.PATH, b"off")])
        with self.assertRaises(PatchError):
            patch_lapi.apply(tree)

    def test_conflict_off_declined(self):
        tree = self.tree([(patch_lapi.PATH, b"off")])
        with self.assertRaises(PatchError):
            patch_lapi.remove(tree, ask=lambda q, d: False)
        self.assertTrue(tree.exists(patch_lapi.PATH))

    def test_conflict_off_accepted(self):
        tree = self.tree([(patch_lapi.PATH, b"off")])
        patch_lapi.remove(tree, ask=lambda q, d: True)
        self.assertFalse(tree.exists(patch_lapi.PATH))


class Adb(Base):
    def test_on_off(self):
        tree = self.tree()
        patch_adb.apply(tree)
        for path, asset, _mode in patch_adb.FILES:
            self.assertEqual(tree.sha256(path), sha(asset_bytes(asset)))
            self.assertEqual(tree.mode(path), 0o755)
        self.assertEqual(detect(tree, "system_b")[0]["adb"], "on")

        patch_adb.remove(tree)
        for path, _asset, _mode in patch_adb.FILES:
            self.assertFalse(tree.exists(path))

    def test_on_twice(self):
        tree = self.tree()
        patch_adb.apply(tree)
        before = tree.snapshot()
        patch_adb.apply(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_conflict(self):
        tree = self.tree([("usr/bin/adbd-tcp", b"foreign")])
        with self.assertRaises(PatchError):
            patch_adb.apply(tree, ask=lambda q, d: False)
        patch_adb.apply(tree, ask=lambda q, d: True)
        self.assertEqual(tree.sha256("usr/bin/adbd-tcp"),
                         sha(asset_bytes("adbd")))

    def test_off_absent(self):
        tree = self.tree()
        patch_adb.remove(tree)
        self.assertFalse(tree.exists("usr/bin/adbd-tcp"))


class Ssh(Base):
    def test_on_off(self):
        tree = self.tree()
        patch_ssh.apply(tree)
        for path, asset, _mode in patch_ssh.FILES:
            self.assertEqual(tree.sha256(path), sha(asset_bytes(asset)))
        for path, target in patch_ssh.LINKS:
            self.assertEqual(tree.kind(path), "link")
            self.assertEqual(tree.link_target(path), target)
        self.assertEqual(detect(tree, "system_b")[0]["ssh"], "on")
        patch_ssh.remove(tree)
        for path, _asset, _mode in patch_ssh.FILES:
            self.assertFalse(tree.exists(path))
        for path, _target in patch_ssh.LINKS:
            self.assertFalse(tree.exists(path))

    def test_conflict_declined(self):
        tree = self.tree([("usr/bin/dropbear", b"foreign")])
        with self.assertRaises(PatchError):
            patch_ssh.apply(tree, ask=lambda q, d: False)


class MPython(Base):
    def test_on_off(self):
        tree = self.tree()
        self.assertEqual(patch_mpython.detect(tree)[0], "off")
        patch_mpython.apply(tree)
        self.assertEqual(tree.read(patch_mpython.PATH),
                         asset_bytes(patch_mpython.ASSET))
        self.assertEqual(tree.mode(patch_mpython.PATH), 0o755)
        self.assertEqual(tree.read(patch_mpython.ENV_PATH),
                         asset_bytes(patch_mpython.ENV_ASSET))
        self.assertEqual(tree.mode(patch_mpython.ENV_PATH), 0o644)
        self.assertEqual(patch_mpython.detect(tree)[0], "on")
        patch_mpython.remove(tree)
        self.assertFalse(tree.exists(patch_mpython.PATH))
        self.assertFalse(tree.exists(patch_mpython.ENV_PATH))
        self.assertEqual(patch_mpython.detect(tree)[0], "off")

    def test_on_twice(self):
        tree = self.tree()
        patch_mpython.apply(tree)
        before = tree.snapshot()
        patch_mpython.apply(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_off_absent(self):
        tree = self.tree()
        patch_mpython.remove(tree)
        self.assertFalse(tree.exists(patch_mpython.PATH))
        self.assertFalse(tree.exists(patch_mpython.ENV_PATH))


class Home(Base):
    def test_on_off(self):
        tree = self.tree()
        self.assertEqual(patch_home.detect(tree)[0], "off")
        patch_home.apply(tree)
        self.assertEqual(tree.read(patch_home.PATH),
                         asset_bytes(patch_home.ASSET))
        self.assertEqual(tree.mode(patch_home.PATH), 0o755)
        self.assertEqual(patch_home.detect(tree)[0], "on")
        patch_home.remove(tree)
        self.assertFalse(tree.exists(patch_home.PATH))
        self.assertEqual(patch_home.detect(tree)[0], "off")

    def test_on_twice(self):
        tree = self.tree()
        patch_home.apply(tree)
        before = tree.snapshot()
        patch_home.apply(tree)
        self.assertEqual(tree.snapshot(), before)


class MHal(Base):
    def test_on_off(self):
        tree = self.tree()
        self.assertEqual(patch_mhal.detect(tree)[0], "off")
        patch_mhal.apply(tree)
        base = patch_mhal.TARGET
        self.assertEqual(
            tree.read(base + "/__init__.py"),
            asset_bytes("micro_p_libs/micro_hal/__init__.py"))
        self.assertEqual(tree.mode(base + "/__init__.py"), 0o644)
        lib = base + "/bins/libc_mic.so"
        self.assertEqual(
            tree.read(lib),
            asset_bytes("micro_p_libs/micro_hal/bins/libc_mic.so"))
        self.assertEqual(tree.mode(lib), 0o755)
        self.assertFalse(tree.exists(base + "/tests"))
        states, hashes = patch_mhal.detect(tree)
        self.assertEqual(states, "on")
        self.assertIn("bins/libc_mic.so", hashes)
        self.assertEqual(patch_mhal.detect(tree)[0], "on")
        patch_mhal.remove(tree)
        self.assertFalse(tree.exists(base + "/__init__.py"))
        self.assertFalse(tree.exists(lib))
        self.assertEqual(patch_mhal.detect(tree)[0], "off")

    def test_on_twice(self):
        tree = self.tree()
        patch_mhal.apply(tree)
        before = tree.snapshot()
        patch_mhal.apply(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_partial_is_off(self):
        tree = self.tree()
        patch_mhal.apply(tree)
        tree.remove(patch_mhal.TARGET + "/__init__.py")
        self.assertEqual(patch_mhal.detect(tree)[0], "off")


class Mtts(Base):
    def test_on_off(self):
        tree = self.tree()
        self.assertEqual(patch_mtts.detect(tree)[0], "off")
        patch_mtts.apply(tree)
        base = patch_mtts.TARGET
        self.assertEqual(
            tree.read(base + "/__init__.py"),
            asset_bytes("micro_p_libs/micro_tts/__init__.py"))
        self.assertEqual(tree.mode(base + "/__init__.py"), 0o644)
        token = base + "/bins/edge_token"
        self.assertEqual(
            tree.read(token),
            asset_bytes("micro_p_libs/micro_tts/bins/edge_token"))
        self.assertEqual(tree.mode(token), 0o755)
        self.assertEqual(patch_mtts.detect(tree)[0], "on")
        patch_mtts.remove(tree)
        self.assertFalse(tree.exists(base + "/__init__.py"))
        self.assertEqual(patch_mtts.detect(tree)[0], "off")

    def test_on_twice(self):
        tree = self.tree()
        patch_mtts.apply(tree)
        before = tree.snapshot()
        patch_mtts.apply(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_partial_is_off(self):
        tree = self.tree()
        patch_mtts.apply(tree)
        tree.remove(patch_mtts.TARGET + "/__init__.py")
        self.assertEqual(patch_mtts.detect(tree)[0], "off")


class _BinaryInData:
    """Общие проверки бинарника, положенного в overlay data."""

    MODULE = None

    def test_on_off(self):
        module = self.MODULE
        tree = self.tree()
        self.assertEqual(module.detect(tree)[0], "off")
        module.apply(tree)
        self.assertEqual(tree.read(module.PATH),
                         asset_bytes(module.ASSET))
        self.assertEqual(tree.mode(module.PATH), 0o755)
        self.assertEqual(module.detect(tree)[0], "on")
        module.remove(tree)
        self.assertFalse(tree.exists(module.PATH))
        self.assertEqual(module.detect(tree)[0], "off")

    def test_on_twice(self):
        module = self.MODULE
        tree = self.tree()
        module.apply(tree)
        before = tree.snapshot()
        module.apply(tree)
        self.assertEqual(tree.snapshot(), before)


class Hostapd(Base, _BinaryInData):
    MODULE = patch_hostapd


class Dnsmasq(Base, _BinaryInData):
    MODULE = patch_dnsmasq


class VkVoice(Base):
    def test_off_and_on(self):
        tree = self.tree([(patch_vkvoice.PATH, b"#!/bin/sh\n")])
        self.assertEqual(patch_vkvoice.detect(tree)[0], "off")
        patch_vkvoice.apply(tree)
        self.assertFalse(tree.exists(patch_vkvoice.PATH))
        self.assertEqual(tree.read(patch_vkvoice.BACKUP), b"#!/bin/sh\n")
        self.assertEqual(tree.mode(patch_vkvoice.BACKUP), 0o755)
        self.assertEqual(patch_vkvoice.detect(tree)[0], "on")
        patch_vkvoice.remove(tree)
        self.assertTrue(tree.exists(patch_vkvoice.PATH))
        self.assertFalse(tree.exists(patch_vkvoice.BACKUP))
        self.assertEqual(patch_vkvoice.detect(tree)[0], "off")

    def test_apply_twice(self):
        tree = self.tree([(patch_vkvoice.PATH, b"script")])
        patch_vkvoice.apply(tree)
        before = tree.snapshot()
        patch_vkvoice.apply(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_apply_absent(self):
        tree = self.tree()
        before = tree.snapshot()
        patch_vkvoice.apply(tree)
        self.assertEqual(tree.snapshot(), before)
        self.assertEqual(patch_vkvoice.detect(tree)[0], "off")

    def test_remove_absent(self):
        tree = self.tree()
        patch_vkvoice.remove(tree)
        self.assertFalse(tree.exists(patch_vkvoice.PATH))
        self.assertFalse(tree.exists(patch_vkvoice.BACKUP))

    def test_backup_without_original(self):
        tree = self.tree([(patch_vkvoice.BACKUP, b"script")])
        state, hashes = patch_vkvoice.detect(tree)
        self.assertEqual(state, "on")
        self.assertIn(patch_vkvoice.BACKUP_NAME, hashes)


class VkCall(Base):
    def test_off_and_on(self):
        tree = self.tree([(patch_vkcall.PATH, b"#!/bin/sh\n")])
        self.assertEqual(patch_vkcall.detect(tree)[0], "off")
        patch_vkcall.apply(tree)
        self.assertFalse(tree.exists(patch_vkcall.PATH))
        self.assertEqual(tree.read(patch_vkcall.BACKUP), b"#!/bin/sh\n")
        self.assertEqual(tree.mode(patch_vkcall.BACKUP), 0o755)
        self.assertEqual(patch_vkcall.detect(tree)[0], "on")
        patch_vkcall.remove(tree)
        self.assertTrue(tree.exists(patch_vkcall.PATH))
        self.assertFalse(tree.exists(patch_vkcall.BACKUP))
        self.assertEqual(patch_vkcall.detect(tree)[0], "off")

    def test_apply_twice(self):
        tree = self.tree([(patch_vkcall.PATH, b"script")])
        patch_vkcall.apply(tree)
        before = tree.snapshot()
        patch_vkcall.apply(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_apply_absent(self):
        tree = self.tree()
        before = tree.snapshot()
        patch_vkcall.apply(tree)
        self.assertEqual(tree.snapshot(), before)
        self.assertEqual(patch_vkcall.detect(tree)[0], "off")

    def test_remove_absent(self):
        tree = self.tree()
        patch_vkcall.remove(tree)
        self.assertFalse(tree.exists(patch_vkcall.PATH))
        self.assertFalse(tree.exists(patch_vkcall.BACKUP))

    def test_backup_without_original(self):
        tree = self.tree([(patch_vkcall.BACKUP, b"script")])
        state, hashes = patch_vkcall.detect(tree)
        self.assertEqual(state, "on")
        self.assertIn(patch_vkcall.BACKUP_NAME, hashes)


class Slfchk(Base):
    def test_off_and_on(self):
        tree = self.tree([(patch_slfchk.PATH, b"#!/bin/sh\n")])
        self.assertEqual(patch_slfchk.detect(tree)[0], "off")
        patch_slfchk.apply(tree)
        self.assertFalse(tree.exists(patch_slfchk.PATH))
        self.assertEqual(tree.read(patch_slfchk.BACKUP), b"#!/bin/sh\n")
        self.assertEqual(tree.mode(patch_slfchk.BACKUP), 0o755)
        self.assertEqual(patch_slfchk.detect(tree)[0], "on")
        patch_slfchk.remove(tree)
        self.assertTrue(tree.exists(patch_slfchk.PATH))
        self.assertFalse(tree.exists(patch_slfchk.BACKUP))
        self.assertEqual(patch_slfchk.detect(tree)[0], "off")

    def test_apply_twice(self):
        tree = self.tree([(patch_slfchk.PATH, b"script")])
        patch_slfchk.apply(tree)
        before = tree.snapshot()
        patch_slfchk.apply(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_apply_absent(self):
        tree = self.tree()
        before = tree.snapshot()
        patch_slfchk.apply(tree)
        self.assertEqual(tree.snapshot(), before)
        self.assertEqual(patch_slfchk.detect(tree)[0], "off")

    def test_remove_absent(self):
        tree = self.tree()
        patch_slfchk.remove(tree)
        self.assertFalse(tree.exists(patch_slfchk.PATH))
        self.assertFalse(tree.exists(patch_slfchk.BACKUP))

    def test_backup_without_original(self):
        tree = self.tree([(patch_slfchk.BACKUP, b"script")])
        state, hashes = patch_slfchk.detect(tree)
        self.assertEqual(state, "on")
        self.assertIn(patch_slfchk.BACKUP_NAME, hashes)


class VkKill(Base):
    def test_kill(self):
        tree = self.tree([(patch_vkkill.PATH, b"orig")])
        self.assertEqual(patch_vkkill.detect(tree)[0], "on")
        patch_vkkill.kill(tree)
        self.assertEqual(tree.sha256(patch_vkkill.PATH),
                         sha(asset_bytes("noop", assets.STUBS)))
        self.assertEqual(patch_vkkill.detect(tree)[0], "off")

    def test_kill_twice(self):
        tree = self.tree([(patch_vkkill.PATH, b"orig")])
        patch_vkkill.kill(tree)
        before = tree.snapshot()
        patch_vkkill.kill(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_kill_absent(self):
        tree = self.tree()
        patch_vkkill.kill(tree)
        self.assertFalse(tree.exists(patch_vkkill.PATH))


class Stubs(Base):
    def test_kill_all(self):
        tree = self.tree([
            ("usr/bin/telemetryd", b"orig-tele"),
            ("usr/bin/fwupdater", b"orig-fwu"),
            ("usr/bin/swupdate", b"orig-swu"),
        ])
        for key in KILLS:
            KILLS[key].kill(tree)
        states = detect(tree, "system_b")[0]
        self.assertEqual(states["tele"], "off")
        self.assertEqual(states["fwu"], "off")
        self.assertEqual(states["swu"], "off")
        self.assertEqual(tree.sha256("usr/bin/fwupdater"),
                         sha(asset_bytes("noop1", assets.STUBS)))

    def test_kill_twice(self):
        tree = self.tree([("usr/bin/telemetryd", b"orig")])
        KILLS["tele"].kill(tree)
        before = tree.snapshot()
        KILLS["tele"].kill(tree)
        self.assertEqual(tree.snapshot(), before)

    def test_kill_absent(self):
        tree = self.tree()
        KILLS["tele"].kill(tree)
        self.assertFalse(tree.exists("usr/bin/telemetryd"))

    def test_registry(self):
        self.assertEqual(PATCHES["lapi"].KEY, "lapi")
        self.assertEqual(PATCHES["adb"].PART, "system_b")
        self.assertEqual(PATCHES["ssh"].PART, "system_b")
        self.assertEqual(set(KILLS), {"tele", "fwu", "swu", "vkkill"})



class Registry(unittest.TestCase):
    def test_all_files_registered(self):
        folder = Path(patches_pkg.__file__).parent
        files = {path.stem for path in folder.glob("patch_*.py")}
        registered = {module.__name__.rsplit(".", 1)[-1]
                      for module in patches_pkg.REGISTRY}
        self.assertEqual(files, registered)

    def test_order_sorted_and_unique(self):
        orders = [module.ORDER for module in patches_pkg.REGISTRY]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(len(orders), len(set(orders)))

    def test_views_match_registry(self):
        patches = [module.KEY for module in patches_pkg.REGISTRY
                   if module.KIND == "toggle"]
        kills = [module.KEY for module in patches_pkg.REGISTRY
                 if module.KIND == "kill"]
        self.assertEqual(list(patches_pkg.PATCHES), patches)
        self.assertEqual(list(patches_pkg.KILLS), kills)

    def test_by_part(self):
        parts = {module.PART for module in patches_pkg.REGISTRY}
        self.assertEqual(set(patches_pkg.BY_PART), parts)
        for part, modules in patches_pkg.BY_PART.items():
            self.assertTrue(modules)
            self.assertTrue(all(module.PART == part for module in modules))

    def test_part_order_covers_parts(self):
        self.assertEqual(patches_pkg.PART_ORDER, ("system_b", "data"))
        parts = {module.PART for module in patches_pkg.REGISTRY}
        self.assertTrue(parts <= set(patches_pkg.PART_ORDER))


class RegistryValidation(unittest.TestCase):
    def toggle(self, **changes):
        data = dict(
            KEY="x", TITLE="X", PART="system_b", KIND="toggle",
            FLAG="x", ORDER=1,
            detect=lambda tree: ("off", {}),
            apply=lambda tree, ask=None: None,
            remove=lambda tree, ask=None: None,
        )
        data.update(changes)
        return SimpleNamespace(**data)

    def kill(self, **changes):
        data = dict(
            KEY="k", TITLE="K", PART="system_b", KIND="kill",
            FLAG="k", ORDER=2,
            detect=lambda tree: ("off", {}),
            kill=lambda tree: None,
        )
        data.update(changes)
        return SimpleNamespace(**data)

    def test_ok(self):
        patches_pkg.validate_registry([self.toggle(), self.kill()])

    def test_bad_part(self):
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry(
                [self.toggle(PART="system_a")])

    def test_bad_kind(self):
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry(
                [self.toggle(KIND="other")])

    def test_duplicate_key(self):
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry([
                self.toggle(KEY="a", FLAG="a", ORDER=1),
                self.toggle(KEY="a", FLAG="b", ORDER=2),
            ])

    def test_duplicate_flag(self):
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry([
                self.toggle(KEY="a", FLAG="f", ORDER=1),
                self.toggle(KEY="b", FLAG="f", ORDER=2),
            ])

    def test_duplicate_order(self):
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry([
                self.toggle(KEY="a", FLAG="a", ORDER=1),
                self.toggle(KEY="b", FLAG="b", ORDER=1),
            ])

    def test_missing_detect(self):
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry(
                [self.toggle(detect=None)])

    def test_missing_order(self):
        module = self.toggle()
        del module.ORDER
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry([module])

    def test_missing_toggle_method(self):
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry([self.toggle(apply=None)])
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry([self.toggle(remove=None)])

    def test_missing_kill(self):
        with self.assertRaises(PatchError):
            patches_pkg.validate_registry([self.kill(kill=None)])


class Meta(unittest.TestCase):
    def modules(self):
        return list(PATCHES.values()) + list(KILLS.values())

    def test_metadata(self):
        keys, flags, orders = set(), set(), set()
        for module in self.modules():
            self.assertIn(module.KIND, ("toggle", "kill"))
            self.assertIn(module.PART, ("system_b", "data"))
            self.assertTrue(module.TITLE)
            self.assertTrue(module.SUMMARY)
            self.assertTrue(module.FLAG)
            self.assertIsInstance(module.ORDER, int)
            self.assertTrue(callable(module.detect))
            self.assertNotIn(module.KEY, keys)
            self.assertNotIn(module.FLAG, flags)
            self.assertNotIn(module.ORDER, orders)
            keys.add(module.KEY)
            flags.add(module.FLAG)
            orders.add(module.ORDER)


class Detect(Base):
    def test_lapi(self):
        self.assertEqual(patch_lapi.detect(self.tree()), ("off", {}))
        tree = self.tree([(patch_lapi.PATH, b"on")])
        state, hashes = patch_lapi.detect(tree)
        self.assertEqual(state, "on")
        self.assertEqual(hashes, {patch_lapi.PATH: sha(b"on")})
        tree = self.tree([(patch_lapi.PATH, b"off")])
        self.assertEqual(patch_lapi.detect(tree)[0], "off")

    def test_adb(self):
        self.assertEqual(patch_adb.detect(self.tree()), ("off", {}))
        entries = [(path, asset_bytes(asset))
                   for path, asset, _mode in patch_adb.FILES]
        state, hashes = patch_adb.detect(self.tree(entries))
        self.assertEqual(state, "on")
        self.assertEqual(set(hashes), set(patch_adb.LOGICAL.values()))

    def test_ssh(self):
        tree = self.tree()
        patch_ssh.apply(tree)
        state, hashes = patch_ssh.detect(tree)
        self.assertEqual(state, "on")
        self.assertEqual(set(hashes), set(patch_ssh.LOGICAL.values()))

    def test_stub_states(self):
        self.assertEqual(patch_telemetryd.detect(self.tree()), ("off", {}))
        tree = self.tree([(patch_telemetryd.PATH, b"original")])
        state, hashes = patch_telemetryd.detect(tree)
        self.assertEqual(state, "on")
        self.assertEqual(hashes, {patch_telemetryd.NAME: sha(b"original")})
        tree = self.tree([(patch_telemetryd.PATH,
                           asset_bytes("noop", assets.STUBS))])
        self.assertEqual(patch_telemetryd.detect(tree)[0], "off")

if __name__ == "__main__":
    unittest.main(verbosity=2)
