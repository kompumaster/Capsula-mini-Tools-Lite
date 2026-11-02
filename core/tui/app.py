"""Главное меню Lite: бэкап, патчи, прошивка, сервис."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.colors import GREEN, RED, paint  # noqa: E402
from fwpatch.patches import KILLS, PATCHES  # noqa: E402
from tui import actions  # noqa: E402
from tui.keys import read_key  # noqa: E402
from tui.screen import Screen  # noqa: E402

MENU = (
    ("1", "Бэкап"),
    ("2", "Патчи"),
    ("3", "Прошивка"),
    ("4", "Сервис"),
)

BACK_MENU = (
    ("1", "Снять бэкап"),
    ("2", "Статус бэкапа"),
    ("3", "Открыть папку backup/parts"),
)

# Пункты меню берутся из реестра патчей: название задаётся в модуле
# патча (`TITLE`), порядок — порядком в `PATCHES` и `KILLS`.
PATCH_ITEMS = tuple(
    (str(number), module.TITLE, module.KEY)
    for number, module in enumerate(
        sorted(PATCHES.values(), key=lambda module: module.ORDER)
        + sorted(KILLS.values(), key=lambda module: module.ORDER),
        1)
)

WRITE_FOLDERS = (
    ("1", "patched/parts"),
    ("2", "backup/parts"),
)


def result_text(code: int) -> str:
    """Итог операции: зелёный при успехе, красный при ошибке."""
    text = f"код: {code}"
    return paint(text, GREEN if code == 0 else RED)


def patch_state_text(label: str) -> str:
    """Состояние патча: on/kill — зелёные, off/work — красные."""
    if label.startswith("[") and "]" in label:
        state = label[1:label.index("]")]
        if state in ("on", "kill"):
            return paint(label, GREEN)
        if state in ("off", "work"):
            return paint(label, RED)
    return label


def backup_menu(screen: Screen) -> None:
    while True:
        screen.clear()
        screen.title("Бэкап")
        screen.menu(BACK_MENU)
        screen.message("B) Назад")
        screen.message()
        screen.prompt()

        key = read_key()
        if key in ("b", "B", "и", "И", "q", "Q", "й", "Й"):
            return
        if key == "1":
            screen.clear()
            screen.title("Бэкап: чтение разделов")
            code = actions.run_backup()
            screen.message(result_text(code))
            screen.message()
            screen.pause()
            if code == 0:
                return
        elif key == "2":
            screen.clear()
            screen.title("Статус бэкапа")
            screen.message("Проверяю статус...")
            for line in actions.backup_status_text():
                screen.message(line)
            screen.pause()
        elif key == "3":
            ok = actions.open_folder()
            screen.clear()
            screen.title("Открыть папку")
            screen.message("открыто" if ok
                           else "не удалось открыть backup/parts")
            screen.pause()


def patch_menu(screen: Screen) -> None:
    if not actions.has_patch_source():
        screen.clear()
        screen.title("Патчи")
        screen.message("Нет файлов. Сначала сделайте Бекап")
        screen.pause()
        return

    screen.clear()
    screen.title("Патчи")
    screen.message("Проверяю статус...")
    code, data, error = actions.patch_status()
    if code:
        screen.message(error or "статус не снят")
    overrides: dict[str, str] = {}

    while True:
        screen.clear()
        screen.title("Патчи")
        screen.message(f"Источник: {actions.BACKUP}")
        screen.message(f"Выход:    {actions.PATCHED}")
        if error:
            screen.message(paint(f"Статус:   {error}", RED))
        screen.message()
        for number, title, key in PATCH_ITEMS:
            mark = number
            if (key in actions.STUBS
                    and actions.current_patch_state(data, key) == "kill"):
                mark = "x"
            label = actions.patch_label(data, overrides, key)
            screen.message(f"{mark}) {title:<16} {patch_state_text(label)}")
        screen.message()
        screen.message(paint("P) Применить", GREEN))
        screen.message("R) Сбросить")
        screen.message("B) Назад")
        screen.message()
        screen.prompt()

        key = read_key()
        if key in ("b", "B", "и", "И", "q", "Q", "й", "Й"):
            return
        if key in ("r", "R", "к", "К"):
            overrides.clear()
            continue
        if key in ("p", "P", "з", "З"):
            if not overrides:
                screen.message()
                screen.message("ничего не выбрано")
                screen.pause()
                continue
            screen.clear()
            screen.title("Сборка патчей")
            code = actions.run_patch(dict(overrides))
            screen.message(result_text(code))
            screen.message()
            screen.pause()
            return
        for number, _title, patch_key in PATCH_ITEMS:
            if key == number:
                actions.toggle_patch(overrides, data, patch_key)
                break


def confirm_write() -> bool:
    try:
        answer = input(paint("Записать? Введите да/yes: ", RED))
    except EOFError:
        return False
    return answer.strip().lower() in ("yes", "да", "е")


def file_menu(screen: Screen, folder: Path) -> bool:
    images = actions.load_images(folder)
    if not images:
        screen.clear()
        screen.title("Прошивка")
        screen.message(f"нет .bin в {folder}")
        screen.pause()
        return False

    while True:
        screen.clear()
        screen.title("Прошивка")
        screen.message(f"Файлы: {folder}")
        screen.message()
        for number, image in enumerate(images, 1):
            screen.message(f"{number}) {image.path.name}   {image.states}")
        screen.message()
        screen.message("A) записать все")
        screen.message("B) Назад")
        screen.message()
        screen.prompt()

        key = read_key()
        if key in ("b", "B", "и", "И", "q", "Q", "й", "Й"):
            return False
        if key.lower() in ("a", "ф"):
            screen.clear()
            screen.title("Прошивка")
            screen.message("Выбор:")
            for image in images:
                screen.message(image.path.name)
            if not confirm_write():
                continue
            screen.clear()
            screen.title("Прошивка")
            failed = False
            for number, image in enumerate(images, 1):
                screen.message(
                    f"[{number}/{len(images)}] "
                    f"{image.path.name} -> {image.part}")
                code = actions.write_image(image)
                if code:
                    screen.message(paint(f"{image.path.name}: код {code}", RED))
                    failed = True
                    break
            screen.message()
            screen.pause()
            if failed:
                continue
            return True
        if not key.isdigit():
            continue
        index = int(key)
        if not 1 <= index <= len(images):
            continue
        image = images[index - 1]
        screen.clear()
        screen.title("Прошивка")
        screen.message("Выбор:")
        screen.message(image.path.name)
        if not confirm_write():
            continue
        screen.clear()
        screen.title("Прошивка")
        code = actions.write_image(image)
        screen.message(result_text(code))
        screen.message()
        screen.pause()
        if code == 0:
            return True
        continue


def write_menu(screen: Screen) -> None:
    while True:
        screen.clear()
        screen.title("Прошивка")
        for number, label in WRITE_FOLDERS:
            screen.message(f"{number}) {label}")
        screen.message("B) Назад")
        screen.message()
        screen.prompt()

        key = read_key()
        if key in ("b", "B", "и", "И", "q", "Q", "й", "Й"):
            return
        if key == "1":
            if file_menu(screen, actions.PATCHED):
                return
        elif key == "2":
            if file_menu(screen, actions.BACKUP):
                return


def confirm_overwrite(tar: Path) -> bool:
    try:
        answer = input(f"{tar.name} уже есть. Перезаписать? [y/N]: ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes", "д", "да", "е")


def tar_menu(screen: Screen) -> None:
    while True:
        try:
            images = actions.tar_images()
        except Exception as exc:
            screen.clear()
            screen.title("Сервис: раздел → tar")
            screen.message(paint(f"ошибка: {exc}", RED))
            screen.pause()
            return

        screen.clear()
        screen.title("Сервис: раздел → tar")
        if not images:
            screen.message("нет UBI-файлов")
            screen.pause()
            return

        folder = None
        for number, image in enumerate(images, 1):
            if image.folder != folder:
                if folder is not None:
                    screen.message()
                try:
                    label = image.folder.relative_to(actions.ROOT)
                except ValueError:
                    label = image.folder
                screen.message(str(label))
                folder = image.folder
            mark = (paint(" (есть .tar)", GREEN)
                    if image.tar.is_file() else "")
            screen.message(f"{number}) {image.path.name}{mark}")

        screen.message()
        screen.message("B) Назад")
        screen.message()
        screen.prompt()
        key = read_key()
        if key in ("b", "B", "и", "И", "q", "Q", "й", "Й"):
            return
        if not key.isdigit():
            continue
        index = int(key)
        if not 1 <= index <= len(images):
            continue

        image = images[index - 1]
        if not image.path.is_file():
            screen.message(paint(f"файл исчез: {image.path}", RED))
            screen.pause()
            continue

        force = False
        if image.tar.is_file():
            if not confirm_overwrite(image.tar):
                continue
            force = True

        screen.clear()
        screen.title("Сервис: раздел → tar")
        screen.message(f"Преобразую {image.path.name}...")
        try:
            tar, summary = actions.unpack_to_tar_details(
                image, force=force)
        except Exception as exc:
            screen.message(paint(f"ошибка: {exc}", RED))
        else:
            screen.message(paint(f"готово: {tar}", GREEN))
            for line in summary:
                screen.message(line)
        screen.message()
        screen.pause()


def image_menu(screen: Screen) -> None:
    while True:
        try:
            files = actions.tar_files()
        except Exception as exc:
            screen.clear()
            screen.title("Сервис: tar → раздел")
            screen.message(paint(f"ошибка: {exc}", RED))
            screen.pause()
            return

        screen.clear()
        screen.title("Сервис: tar → раздел")
        if not files:
            screen.message("нет tar-файлов")
            screen.pause()
            return

        folder = None
        for number, item in enumerate(files, 1):
            if item.folder != folder:
                if folder is not None:
                    screen.message()
                try:
                    label = item.folder.relative_to(actions.ROOT)
                except ValueError:
                    label = item.folder
                screen.message(label.as_posix())
                folder = item.folder
            mark = (paint(" (есть .bin)", GREEN)
                    if item.image.is_file() else "")
            screen.message(f"{number}) {item.path.name}{mark}")

        screen.message()
        screen.message("B) Назад")
        screen.message()
        screen.prompt()
        key = read_key()
        if key in ("b", "B", "и", "И", "q", "Q", "й", "Й"):
            return
        if not key.isdigit():
            continue
        index = int(key)
        if not 1 <= index <= len(files):
            continue

        item = files[index - 1]
        if not item.path.is_file():
            screen.message(paint(f"файл исчез: {item.path}", RED))
            screen.pause()
            continue

        force = False
        if item.image.is_file():
            if not confirm_overwrite(item.image):
                continue
            force = True

        screen.clear()
        screen.title("Сервис: tar → раздел")
        screen.message(f"Собираю {item.path.name}...")
        try:
            image, warning = actions.pack_from_tar(item, force=force)
        except Exception as exc:
            screen.message(paint(f"ошибка: {exc}", RED))
        else:
            screen.message(paint(f"готово: {image}", GREEN))
            if warning:
                screen.message(paint(warning, RED))
        screen.message()
        screen.pause()


def service_menu(screen: Screen) -> None:
    while True:
        screen.clear()
        screen.title("Сервис")
        screen.message("1) Найти IP колонки")
        screen.message("2) Раздел → tar")
        screen.message("3) tar → раздел")
        screen.message("B) Назад")
        screen.message()
        screen.prompt()

        key = read_key()
        if key in ("b", "B", "и", "И", "q", "Q", "й", "Й"):
            return
        if key == "1":
            screen.clear()
            screen.title("Сервис")
            screen.message("Ищу колонку...")
            try:
                ip = actions.find_column_ip()
            except Exception as exc:  # сеть не должна ломать меню
                ip = None
                screen.message(paint(f"ошибка: {exc}", RED))
            if ip:
                screen.message(paint(f"IP: {ip}", GREEN))
            else:
                screen.message(paint("колонка не найдена", RED))
            screen.pause()
        elif key == "2":
            tar_menu(screen)
        elif key == "3":
            image_menu(screen)


def main() -> int:
    screen = Screen()
    while True:
        screen.clear()
        screen.title("Capsula Mini Tools Lite")
        screen.menu(MENU)
        screen.message("Q) Выход")
        screen.message()
        screen.prompt()

        key = read_key()
        if key in ("q", "Q", "й", "Й"):
            screen.clear()
            return 0
        if key == "1":
            backup_menu(screen)
            continue
        if key == "2":
            patch_menu(screen)
            continue
        if key == "3":
            write_menu(screen)
            continue
        if key == "4":
            service_menu(screen)
            continue
        if not key:
            continue


if __name__ == "__main__":
    raise SystemExit(main())
