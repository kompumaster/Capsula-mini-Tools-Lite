#!/usr/bin/env python3
"""Тесты TUI: клавиши, экран, главное меню."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.tar_ubi import TarFile, TarImage  # noqa: E402
from tui import actions, app  # noqa: E402
from tui.keys import read_key  # noqa: E402
from tui.screen import Screen  # noqa: E402

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)


class Keys(unittest.TestCase):
    def test_char(self):
        with mock.patch.object(sys, "stdin", io.StringIO("q\n")):
            self.assertEqual(read_key(), "q")

    def test_empty_line(self):
        with mock.patch.object(sys, "stdin", io.StringIO("\n")):
            self.assertEqual(read_key(), "")

    def test_eof(self):
        with mock.patch.object(sys, "stdin", io.StringIO("")):
            self.assertEqual(read_key(), "q")


class ScreenTest(unittest.TestCase):
    def test_non_tty(self):
        screen = Screen()
        screen.tty = False
        screen.clear()
        with redirect_stdout(io.StringIO()) as out:
            screen.title("Test")
            screen.menu([("1", "Один")])
        self.assertIn("Test\n====", out.getvalue())
        self.assertIn("1) Один", out.getvalue())


class Menu(unittest.TestCase):
    def test_quit(self):
        with mock.patch.object(app, "read_key", side_effect=["q"]), \
             redirect_stdout(io.StringIO()) as out:
            self.assertEqual(app.main(), 0)
        self.assertIn("Capsula Mini Tools Lite", out.getvalue())
        self.assertIn("1) Бэкап", out.getvalue())

    def test_service_menu(self):
        with mock.patch.object(app, "read_key", side_effect=["4", "q"]), \
             mock.patch.object(app, "service_menu") as menu, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(), 0)
        menu.assert_called_once()

    def test_backup_menu(self):
        with mock.patch.object(app, "read_key", side_effect=["1", "q"]), \
             mock.patch.object(app, "backup_menu") as menu, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(), 0)
        menu.assert_called_once()


class BackupActions(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_status(self):
        self.assertIn("нет status.txt",
                      actions.backup_status_text(self.dir / "nope")[0])

    def test_status_auto(self):
        status = self.dir / "status.txt"

        def fake():
            status.write_text(
                "system_b.file=system_b.bin\n"
                "system_b.adb=on\n",
                encoding="utf-8")
            return 0, {}, ""

        with mock.patch.object(actions, "STATUS", status), \
             mock.patch.object(actions, "BACKUP", self.dir), \
             mock.patch.object(actions, "patch_status", side_effect=fake):
            lines = actions.backup_status_text()
        self.assertIn("system_b.bin: adb=on", "\n".join(lines))

    def test_status(self):
        path = self.dir / "status.txt"
        path.write_text(
            "# fw_patch_lite status 1\n"
            "system_b.file=system_b.adb.bin\n"
            "system_b.adb=on\n"
            "system_b.tele=off\n"
            "data.file=data.lapi.bin\n"
            "data.lapi=on\n",
            encoding="utf-8")
        lines = actions.backup_status_text(path)
        text = "\n".join(lines)
        self.assertIn("system_b.adb.bin: adb=on", text)
        self.assertIn("tele=kill", text)
        self.assertIn("data.lapi.bin: lapi=on", text)

    def test_open_folder(self):
        with mock.patch.object(actions.subprocess, "Popen") as popen:
            self.assertTrue(actions.open_folder(self.dir))
        self.assertIn(str(self.dir), popen.call_args.args[0])

    def test_open_missing(self):
        with mock.patch.object(actions.subprocess, "Popen") as popen:
            self.assertFalse(actions.open_folder(self.dir / "nope"))
        popen.assert_not_called()


class BackupMenu(unittest.TestCase):
    def test_success_returns_to_main(self):
        with mock.patch.object(app, "read_key", side_effect=["1"]) as key, \
             mock.patch.object(actions, "run_backup", return_value=0), \
             redirect_stdout(io.StringIO()):
            app.backup_menu(Screen())
        self.assertEqual(key.call_count, 1)

    def test_failure_stays_in_menu(self):
        with mock.patch.object(app, "read_key",
                               side_effect=["1", "b"]) as key, \
             mock.patch.object(actions, "run_backup", return_value=1), \
             redirect_stdout(io.StringIO()):
            app.backup_menu(Screen())
        self.assertEqual(key.call_count, 2)

    def test_status_screen(self):
        with mock.patch.object(app, "read_key", side_effect=["2", "b"]), \
             mock.patch.object(actions, "backup_status_text",
                               return_value=["line"]), \
             redirect_stdout(io.StringIO()) as out:
            app.backup_menu(Screen())
        self.assertIn("line", out.getvalue())


DATA = {
    "data.lapi": "on",
    "system_b.adb": "on",
    "system_b.ssh": "off",
    "system_b.tele": "on",
    "system_b.fwu": "on",
    "system_b.swu": "off",
}


class PatchActions(unittest.TestCase):
    def test_flags(self):
        self.assertEqual(
            actions.patch_flags({"lapi": "on", "adb": "off",
                                 "tele": "kill"}),
            ["--lapi-on", "--adb-off", "--telemetry-kill"])

    def test_states(self):
        self.assertEqual(actions.current_patch_state(DATA, "lapi"), "on")
        self.assertEqual(actions.current_patch_state(DATA, "adb"), "on")
        self.assertEqual(actions.current_patch_state(DATA, "ssh"), "off")
        self.assertEqual(actions.current_patch_state(DATA, "tele"), "work")
        self.assertEqual(actions.current_patch_state(DATA, "swu"), "kill")
        self.assertIsNone(actions.current_patch_state({}, "adb"))

    def test_display_state(self):
        self.assertEqual(actions.display_state("system_b", "tele", "on"),
                         "work")
        self.assertEqual(actions.display_state("system_b", "tele", "off"),
                         "kill")
        self.assertEqual(actions.display_state("data", "lapi", "on"), "on")
        fake = SimpleNamespace(PART="data")
        with mock.patch.dict(actions.KILLS, {"mykill": fake}):
            self.assertEqual(
                actions.display_state("data", "mykill", "on"), "work")
            self.assertEqual(
                actions.display_state("data", "mykill", "off"), "kill")
            self.assertEqual(
                actions.display_state("system_b", "mykill", "on"), "on")

    def test_labels(self):
        self.assertEqual(actions.patch_label(DATA, {}, "adb"), "[on]")
        self.assertEqual(actions.patch_label(DATA, {"adb": "off"}, "adb"),
                         "[off]*")
        self.assertEqual(actions.patch_label(DATA, {}, "tele"), "[work]")
        self.assertEqual(actions.patch_label(DATA, {}, "swu"), "[kill]")
        self.assertEqual(actions.patch_label({}, {}, "adb"), "[?]")

    def test_toggle_feature(self):
        overrides = {}
        actions.toggle_patch(overrides, DATA, "adb")
        self.assertEqual(overrides, {"adb": "off"})
        actions.toggle_patch(overrides, DATA, "adb")
        self.assertEqual(overrides, {})

    def test_toggle_unknown_cycle(self):
        overrides = {}
        actions.toggle_patch(overrides, {}, "adb")
        self.assertEqual(overrides, {"adb": "on"})
        actions.toggle_patch(overrides, {}, "adb")
        self.assertEqual(overrides, {"adb": "off"})
        actions.toggle_patch(overrides, {}, "adb")
        self.assertEqual(overrides, {})

    def test_toggle_stub(self):
        overrides = {}
        actions.toggle_patch(overrides, DATA, "tele")
        self.assertEqual(overrides, {"tele": "kill"})
        actions.toggle_patch(overrides, DATA, "tele")
        self.assertEqual(overrides, {})

    def test_toggle_killed_stub(self):
        overrides = {}
        actions.toggle_patch(overrides, DATA, "swu")
        self.assertEqual(overrides, {})

    def test_run_patch(self):
        with mock.patch.object(actions.fw_patch_lite, "main",
                               return_value=0) as main:
            actions.run_patch({"adb": "on"})
        args = main.call_args.args[0]
        self.assertIn("--src", args)
        self.assertIn("--out", args)
        self.assertIn("--adb-on", args)

    def test_patch_status(self):
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            folder = Path(tmp)

            def fake(args):
                (folder / "status.txt").write_text(
                    "system_b.adb=on\n", encoding="utf-8")
                return 0

            with mock.patch.object(actions, "BACKUP", folder), \
                 mock.patch.object(actions.fw_patch_lite, "main",
                                   side_effect=fake):
                code, data, error = actions.patch_status()
        self.assertEqual(code, 0)
        self.assertEqual(data["system_b.adb"], "on")
        self.assertEqual(error, "")


class Quit(unittest.TestCase):
    def test_quit_clears_screen(self):
        with mock.patch.object(app, "read_key", side_effect=["q"]), \
             mock.patch.object(Screen, "clear") as clear, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(), 0)
        self.assertEqual(clear.call_count, 2)


class PatchLists(unittest.TestCase):
    def test_from_registry(self):
        from fwpatch.patches import KILLS, PATCHES

        self.assertEqual(actions.FEATURES, tuple(PATCHES))
        self.assertEqual(actions.STUBS, tuple(KILLS))
        self.assertEqual(actions.KILL_FLAGS,
                         {key: f"--{module.FLAG}-kill"
                          for key, module in KILLS.items()})
        self.assertEqual(actions.IMAGE_PARTS, ("system_b", "data"))


class PatchItems(unittest.TestCase):
    def test_titles_from_registry(self):
        from fwpatch.patches import KILLS, PATCHES

        modules = list(PATCHES.values()) + list(KILLS.values())
        self.assertEqual([title for _, title, _ in app.PATCH_ITEMS],
                         [module.TITLE for module in modules])
        self.assertEqual([key for _, _, key in app.PATCH_ITEMS],
                         list(PATCHES) + list(KILLS))


class PatchLine(unittest.TestCase):
    def test_columns(self):
        short = app.patch_line("1", "LAPI(:80)", "[on]",
                               "локальный API, порт 80")
        long = app.patch_line("10", "Удалить VK-Voice", "[kill]*",
                              "заменить VK-Voice пустышкой, необратимо")
        self.assertTrue(short.startswith(" 1) "))
        self.assertTrue(long.startswith("10) "))
        self.assertEqual(short.index("[on]"), 23)
        self.assertEqual(long.index("[kill]*"), 23)
        self.assertEqual(short.index("локальный"), 31)
        self.assertEqual(long.index("заменить"), 31)

    def test_unknown_state(self):
        line = app.patch_line("7", "Телеметрияd", "[?]", "кратко")
        self.assertIn("[?]     кратко", line)


class PatchMenu(unittest.TestCase):
    def test_summary_in_menu(self):
        with mock.patch.object(actions, "has_patch_source",
                               return_value=True), \
             mock.patch.object(actions, "patch_status",
                               return_value=(0, DATA, "")), \
             mock.patch.object(app, "read_command",
                               side_effect=["b"]), \
             redirect_stdout(io.StringIO()) as out:
            app.patch_menu(Screen())
        text = out.getvalue()
        self.assertIn("локальный API, порт 80", text)
        self.assertIn("заменить SW обновление пустышкой, необратимо", text)

    def test_toggle_and_back(self):
        lapi = next(number for number, _title, key in app.PATCH_ITEMS
                    if key == "lapi")
        with mock.patch.object(actions, "has_patch_source",
                               return_value=True), \
             mock.patch.object(actions, "patch_status",
                               return_value=(0, DATA, "")), \
             mock.patch.object(app, "read_command",
                               side_effect=[lapi, "b"]), \
             redirect_stdout(io.StringIO()) as out:
            app.patch_menu(Screen())
        self.assertIn("LAPI", out.getvalue())
        self.assertIn("[off]*", out.getvalue())

    def test_build_overrides(self):
        lapi = next(number for number, _title, key in app.PATCH_ITEMS
                    if key == "lapi")
        with mock.patch.object(actions, "has_patch_source",
                               return_value=True), \
             mock.patch.object(actions, "patch_status",
                               return_value=(0, DATA, "")), \
             mock.patch.object(app, "read_command",
                               side_effect=[lapi, "p"]), \
             mock.patch.object(actions, "run_patch",
                               return_value=0) as run, \
             redirect_stdout(io.StringIO()):
            app.patch_menu(Screen())
        run.assert_called_once_with({"lapi": "off"})

    def test_reset_clears_selection(self):
        lapi = next(number for number, _title, key in app.PATCH_ITEMS
                    if key == "lapi")
        with mock.patch.object(actions, "has_patch_source",
                               return_value=True), \
             mock.patch.object(actions, "patch_status",
                               return_value=(0, DATA, "")), \
             mock.patch.object(app, "read_command",
                               side_effect=[lapi, "r", "b"]), \
             mock.patch.object(actions, "run_patch") as run, \
             redirect_stdout(io.StringIO()):
            app.patch_menu(Screen())
        run.assert_not_called()

    def test_killed_marked_x(self):
        number = next(number for number, _title, key in app.PATCH_ITEMS
                      if key == "tele")
        with mock.patch.object(actions, "has_patch_source",
                               return_value=True), \
             mock.patch.object(actions, "patch_status",
                               return_value=(0, DATA, "")), \
             mock.patch.object(app, "read_command",
                               side_effect=[number, "b"]), \
             redirect_stdout(io.StringIO()) as out:
            app.patch_menu(Screen())
        self.assertIn("x) Обновление SW", out.getvalue())
        self.assertIn("[kill]*", out.getvalue())

    def test_no_files(self):
        with mock.patch.object(actions, "has_patch_source",
                               return_value=False), \
             redirect_stdout(io.StringIO()) as out:
            app.patch_menu(Screen())
        self.assertIn("Нет файлов", out.getvalue())
        self.assertIn("Бекап", out.getvalue())


class WriteActions(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)
        (self.dir / "system_b.adb.bin").write_bytes(b"x")
        (self.dir / "data.lapi.bin").write_bytes(b"x")
        (self.dir / "boot_a.bin").write_bytes(b"x")
        (self.dir / "system_a.bin").write_bytes(b"x")
        (self.dir / "status.txt").write_text(
            "system_b.file=system_b.adb.bin\n"
            "system_b.adb=on\n"
            "system_b.tele=off\n"
            "data.file=data.lapi.bin\n"
            "data.lapi=on\n",
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_images(self):
        images = actions.load_images(self.dir)
        self.assertEqual([image.part for image in images],
                         ["data", "system_b"])
        self.assertIn("lapi=on", images[0].states)
        self.assertIn("adb=on", images[1].states)
        self.assertIn("tele=kill", images[1].states)

    def test_image_states(self):
        self.assertEqual(
            actions.image_states(
                {"system_b.adb": "on", "system_b.tele": "off"},
                "system_b"),
            "adb=on tele=kill")
        self.assertEqual(
            actions.image_states({}, "system_b"), "нет данных")

    def test_write_image(self):
        image = actions.ImageInfo(self.dir / "system_b.adb.bin",
                                  "system_b", "adb=on")
        with mock.patch.object(actions.write_lite, "main",
                               return_value=0) as main:
            self.assertEqual(actions.write_image(image), 0)
        self.assertEqual(main.call_args.args[0], [
            "--part", "system_b",
            "--file", str(self.dir / "system_b.adb.bin"),
            "--no-confirm"])


class WriteMenu(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.dir = Path(self._tmp.name)
        (self.dir / "system_b.bin").write_bytes(b"x")
        (self.dir / "status.txt").write_text(
            "system_b.file=system_b.bin\n"
            "system_b.adb=on\n",
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_file_menu_write_one(self):
        with mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             mock.patch("builtins.input", return_value="yes"), \
             mock.patch.object(actions, "write_image",
                               return_value=0) as write, \
             redirect_stdout(io.StringIO()) as out:
            self.assertTrue(app.file_menu(Screen(), self.dir))
        write.assert_called_once()
        self.assertIn("Выбор:\nsystem_b.bin\n", out.getvalue())

    def test_file_menu_failure_stays(self):
        with mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             mock.patch("builtins.input", return_value="yes"), \
             mock.patch.object(actions, "write_image", return_value=1), \
             redirect_stdout(io.StringIO()):
            self.assertFalse(app.file_menu(Screen(), self.dir))

    def test_file_menu_write_all_russian(self):
        with mock.patch.object(app, "read_key", side_effect=["ф", "b"]), \
             mock.patch("builtins.input", return_value="да"), \
             mock.patch.object(actions, "write_image",
                               return_value=0) as write, \
             redirect_stdout(io.StringIO()):
            self.assertTrue(app.file_menu(Screen(), self.dir))
        write.assert_called_once()

    def test_write_all_two(self):
        (self.dir / "data.bin").write_bytes(b"y")
        (self.dir / "status.txt").write_text(
            "system_b.file=system_b.bin\n"
            "system_b.adb=on\n"
            "data.file=data.bin\n"
            "data.lapi=on\n",
            encoding="utf-8")
        with mock.patch.object(app, "read_key", side_effect=["ф", "b"]), \
             mock.patch("builtins.input", return_value="да"), \
             mock.patch.object(actions, "write_image",
                               return_value=0) as write, \
             redirect_stdout(io.StringIO()) as out:
            app.file_menu(Screen(), self.dir)
        self.assertEqual(write.call_count, 2)
        self.assertIn("[1/2]", out.getvalue())
        self.assertIn("[2/2]", out.getvalue())
        self.assertIn("Выбор:\ndata.bin\nsystem_b.bin\n", out.getvalue())

    def test_write_menu_folder(self):
        with mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             mock.patch.object(app, "file_menu") as menu:
            app.write_menu(Screen())
        menu.assert_called_once_with(mock.ANY, actions.PATCHED)

    def test_main_write(self):
        with mock.patch.object(app, "read_key", side_effect=["3", "q"]), \
             mock.patch.object(app, "write_menu") as menu:
            self.assertEqual(app.main(), 0)
        menu.assert_called_once()


class ServiceActions(unittest.TestCase):
    def test_find_ip(self):
        with mock.patch.object(actions, "find_capsula",
                               return_value="192.0.2.10"):
            self.assertEqual(actions.find_column_ip(), "192.0.2.10")

    def test_reboot(self):
        def fake(log):
            log("перезагрузка отправлена по SSH")
            return 0

        with mock.patch.object(actions.reboot_tool, "reboot",
                               side_effect=fake) as call:
            code, lines = actions.reboot_column()
        self.assertEqual(code, 0)
        self.assertIn("SSH", lines[-1])
        call.assert_called_once()


class ServiceMenu(unittest.TestCase):
    def test_ip(self):
        with mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             mock.patch.object(actions, "find_column_ip",
                               return_value="192.0.2.10"), \
             redirect_stdout(io.StringIO()) as out:
            app.service_menu(Screen())
        self.assertIn("IP: 192.0.2.10", out.getvalue())

    def test_tar_item(self):
        with mock.patch.object(app, "read_key", side_effect=["2", "b"]), \
             mock.patch.object(app, "tar_menu") as menu:
            app.service_menu(Screen())
        menu.assert_called_once()

    def test_image_item(self):
        with mock.patch.object(app, "read_key", side_effect=["3", "b"]), \
             mock.patch.object(app, "image_menu") as menu:
            app.service_menu(Screen())
        menu.assert_called_once()

    def test_reboot_item(self):
        with mock.patch.object(app, "read_key", side_effect=["4", "b"]), \
             mock.patch.object(actions, "reboot_column",
                               return_value=(0, ["ok"])) as reboot, \
             redirect_stdout(io.StringIO()):
            app.service_menu(Screen())
        reboot.assert_called_once()

    def test_blank_before_back(self):
        with mock.patch.object(app, "read_key", side_effect=["b"]), \
             redirect_stdout(io.StringIO()) as out:
            app.service_menu(Screen())
        self.assertIn("4) Перезагрузить колонку\n\nB) Назад", out.getvalue())


class TarActions(unittest.TestCase):
    def test_tar_images_order(self):
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            root = Path(tmp)
            backup = root / "backup"
            patched = root / "patched"
            backup.mkdir()
            patched.mkdir()
            (backup / "system_b.bin").write_bytes(b"UBI#" + b"\0" * 8)
            (backup / "boot_a.bin").write_bytes(b"ANDR")
            (patched / "data.lapi.bin").write_bytes(b"UBI#" + b"\0" * 8)
            with mock.patch.object(actions, "BACKUP", backup), \
                 mock.patch.object(actions, "PATCHED", patched):
                images = actions.tar_images()
        self.assertEqual([image.path.name for image in images],
                         ["system_b.bin", "data.lapi.bin"])
        self.assertEqual([image.folder for image in images],
                         [backup, patched])

    def test_unpack_to_tar(self):
        image = TarImage(Path("a/system_b.bin"), Path("a"),
                         "system_b", Path("a/system_b.tar"))
        with mock.patch.object(actions, "unpack_ubi",
                               return_value=image.tar) as unpack:
            result = actions.unpack_to_tar(image, force=True)
        self.assertEqual(result, image.tar)
        unpack.assert_called_once_with(image.path, force=True)

    def test_unpack_to_tar_details(self):
        image = TarImage(Path("a/system_b.bin"), Path("a"),
                         "system_b", Path("a/system_b.tar"))
        with mock.patch.object(actions, "unpack_ubi_details",
                               return_value=(image.tar, ["том: rootfs"])):
            tar, summary = actions.unpack_to_tar_details(
                image, force=True)
        self.assertEqual(tar, image.tar)
        self.assertEqual(summary, ["том: rootfs"])

    def test_tar_files_order(self):
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            root = Path(tmp)
            backup = root / "backup"
            patched = root / "patched"
            backup.mkdir()
            patched.mkdir()
            (backup / "data.tar").write_bytes(b"tar")
            (patched / "system_b.tar").write_bytes(b"tar")
            with mock.patch.object(actions, "BACKUP", backup), \
                 mock.patch.object(actions, "PATCHED", patched):
                files = actions.tar_files()
        self.assertEqual([item.path.name for item in files],
                         ["data.tar", "system_b.tar"])
        self.assertEqual([item.folder for item in files],
                         [backup, patched])

    def test_pack_from_tar(self):
        item = TarFile(Path("a/data.tar"), Path("a"), Path("a/data.bin"))
        with mock.patch.object(actions, "pack_tar",
                               return_value=(item.image, None)) as pack:
            image, warning = actions.pack_from_tar(item, force=True)
        self.assertEqual(image, item.image)
        self.assertIsNone(warning)
        pack.assert_called_once_with(item.path, force=True)


class TarMenu(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.root = Path(self._tmp.name)
        self.backup = self.root / "backup"
        self.patched = self.root / "patched"
        self.backup.mkdir()
        self.patched.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def image(self, name="system_b.bin", folder=None, tar=False):
        folder = folder or self.backup
        path = folder / name
        path.write_bytes(b"UBI#" + b"\0" * 8)
        tar_path = path.with_suffix(".tar")
        if tar:
            tar_path.write_bytes(b"tar")
        return TarImage(path, folder, name.split(".", 1)[0], tar_path)

    def test_list_marks_tar(self):
        first = self.image("system_b.bin")
        second = self.image("data.lapi.bin", tar=True)
        with mock.patch.object(actions, "tar_images",
                               return_value=[first, second]), \
             mock.patch.object(app, "read_key", return_value="b"), \
             redirect_stdout(io.StringIO()) as out:
            app.tar_menu(Screen())
        text = out.getvalue()
        self.assertIn("system_b.bin", text)
        self.assertIn("data.lapi.bin (есть .tar)", text)

    def test_unpack(self):
        image = self.image()
        with mock.patch.object(actions, "tar_images",
                               return_value=[image]), \
             mock.patch.object(actions, "unpack_to_tar_details",
                               return_value=(image.tar,
                                             ["том: rootfs"])) as unpack, \
             mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             redirect_stdout(io.StringIO()) as out:
            app.tar_menu(Screen())
        unpack.assert_called_once_with(image, force=False)
        self.assertIn("готово", out.getvalue())
        self.assertIn("том: rootfs", out.getvalue())

    def test_overwrite_declined(self):
        image = self.image(tar=True)
        with mock.patch.object(actions, "tar_images",
                               return_value=[image]), \
             mock.patch.object(actions, "unpack_to_tar_details") as unpack, \
             mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             mock.patch("builtins.input", return_value="n"):
            app.tar_menu(Screen())
        unpack.assert_not_called()

    def test_overwrite_accepted(self):
        image = self.image(tar=True)
        with mock.patch.object(actions, "tar_images",
                               return_value=[image]), \
             mock.patch.object(actions, "unpack_to_tar_details",
                               return_value=(image.tar,
                                             ["том: rootfs"])) as unpack, \
             mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             mock.patch("builtins.input", return_value="д"), \
             redirect_stdout(io.StringIO()):
            app.tar_menu(Screen())
        unpack.assert_called_once_with(image, force=True)

    def test_no_ubi(self):
        with mock.patch.object(actions, "tar_images", return_value=[]), \
             redirect_stdout(io.StringIO()) as out:
            app.tar_menu(Screen())
        self.assertIn("нет UBI-файлов", out.getvalue())


class ImageMenu(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=TMP)
        self.root = Path(self._tmp.name)
        self.backup = self.root / "backup"
        self.patched = self.root / "patched"
        self.backup.mkdir()
        self.patched.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def item(self, name="data.tar", folder=None, image=False):
        folder = folder or self.backup
        path = folder / name
        path.write_bytes(b"tar")
        image_path = path.with_suffix(".bin")
        if image:
            image_path.write_bytes(b"image")
        return TarFile(path, folder, image_path)

    def test_list_marks_bin(self):
        first = self.item("data.tar")
        second = self.item("system_b.tar", image=True)
        with mock.patch.object(actions, "tar_files",
                               return_value=[first, second]), \
             mock.patch.object(app, "read_key", return_value="b"), \
             redirect_stdout(io.StringIO()) as out:
            app.image_menu(Screen())
        text = out.getvalue()
        self.assertIn("data.tar", text)
        self.assertIn("system_b.tar (есть .bin)", text)

    def test_pack(self):
        item = self.item()
        with mock.patch.object(actions, "tar_files",
                               return_value=[item]), \
             mock.patch.object(actions, "pack_from_tar",
                               return_value=(item.image, None)) as pack, \
             mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             redirect_stdout(io.StringIO()) as out:
            app.image_menu(Screen())
        pack.assert_called_once_with(item, force=False)
        self.assertIn("готово", out.getvalue())

    def test_pack_warning(self):
        item = self.item()
        with mock.patch.object(actions, "tar_files",
                               return_value=[item]), \
             mock.patch.object(actions, "pack_from_tar",
                               return_value=(item.image, "zstd заменён")), \
             mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             redirect_stdout(io.StringIO()) as out:
            app.image_menu(Screen())
        self.assertIn("zstd заменён", out.getvalue())

    def test_overwrite_declined(self):
        item = self.item(image=True)
        with mock.patch.object(actions, "tar_files",
                               return_value=[item]), \
             mock.patch.object(actions, "pack_from_tar") as pack, \
             mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             mock.patch("builtins.input", return_value="n"):
            app.image_menu(Screen())
        pack.assert_not_called()

    def test_overwrite_accepted(self):
        item = self.item(image=True)
        with mock.patch.object(actions, "tar_files",
                               return_value=[item]), \
             mock.patch.object(actions, "pack_from_tar",
                               return_value=(item.image, None)) as pack, \
             mock.patch.object(app, "read_key", side_effect=["1", "b"]), \
             mock.patch("builtins.input", return_value="д"), \
             redirect_stdout(io.StringIO()):
            app.image_menu(Screen())
        pack.assert_called_once_with(item, force=True)

    def test_no_tars(self):
        with mock.patch.object(actions, "tar_files", return_value=[]), \
             redirect_stdout(io.StringIO()) as out:
            app.image_menu(Screen())
        self.assertIn("нет tar-файлов", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
