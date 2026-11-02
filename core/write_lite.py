"""Запись образа в раздел через fw_io (только store).

Лёгкая редакция: только Python, только `store`. Перед записью образ
проверяется как UBI (кроме boot/misc), размер сверяется с
приблизительной таблицей, после записи раздел читается обратно и
сверяется по SHA-256.

Любая ошибка - предложение повторить (по умолчанию Y), пока не
получится или пользователь не откажется.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from common.colors import GREEN, RED, paint
from common.sizes import APPROX, PEB, deviation
from common.ubi_check import VOLUMES, check_ubi, read_ubi_params
from fw_io.transport import Transport, UsbError

ROOT = Path(__file__).resolve().parents[1]

# Разделы, которые загрузчик принимает через `store`.
ALLOWED = {"system_a", "system_b", "data"}
# Дополнительно, только с --kamikadze.
KAMIKADZE = {"misc", "boot_a", "boot_b"}
UBI_PARTS = {"system_a", "system_b", "data"}

# Допустимое отклонение размера от таблицы, дальше - подтверждение.
SIZE_TOLERANCE = 0.10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ask(question: str, default: bool = True) -> bool:
    """Вопрос с ответом y/n; Enter - значение по умолчанию."""
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = input(f"{question} {hint}: ").strip().lower()
        except EOFError:
            return default
        if not answer:
            return default
        if answer in ("y", "yes", "д", "да", "е"):
            return True
        if answer in ("n", "no", "н", "нет", "т"):
            return False


def progress(label: str, total: int):
    last = 0

    def show(done: int, _total: int) -> None:
        nonlocal last
        if done == total or done - last >= 16 * 1024 * 1024:
            print(f"  {label}: {done * 100 // total}% ({done} Б)",
                  flush=True)
            last = done

    return show


def do_write(transport: Transport, part: str, path: Path,
             size: int) -> None:
    """Пишет раздел, повторяя по запросу при ошибке."""
    while True:
        try:
            transport.write_partition(part, size, path,
                                      progress(f"запись {part}", size))
            return
        except (UsbError, OSError) as exc:
            print(paint(f"error: запись не удалась: {exc}", RED, sys.stderr),
                  file=sys.stderr)
            if not ask("Повторить?", True):
                raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="write_lite",
        description="Запись раздела через fw_io (только store)")
    parser.add_argument("--part", required=True, help="имя раздела")
    parser.add_argument("--file", required=True, help="образ раздела")
    parser.add_argument("--wait", type=int, default=120,
                        help="сколько ждать загрузчик, секунд")
    parser.add_argument("--no-check-ubi", action="store_true",
                        help="не проверять образ как UBI")
    parser.add_argument("--no-check-size", action="store_true",
                        help="не сверять размер с таблицей")
    parser.add_argument("--no-check-write", action="store_true",
                        help="не читать обратно и не сверять")
    parser.add_argument("--no-confirm", action="store_true",
                        help="не спрашивать yes перед записью")
    parser.add_argument("--kamikadze", action="store_true",
                        help="разрешить запись в misc, boot_a, boot_b")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        print(paint(f"error: нет файла {path}", RED, sys.stderr),
              file=sys.stderr)
        return 1
    size = path.stat().st_size
    if size == 0 or size % PEB:
        print(paint(f"error: размер {size} Б не кратен PEB {PEB}",
                    RED, sys.stderr), file=sys.stderr)
        return 1

    allowed = args.part in ALLOWED or (
        args.kamikadze and args.part in KAMIKADZE)
    if not allowed:
        print(paint("запись запрещена", RED, sys.stderr), file=sys.stderr)
        return 1

    if not args.no_check_size:
        delta = deviation(args.part, size)
        if delta is not None and delta > SIZE_TOLERANCE:
            print(f"размер {size} Б отличается от типичного "
                  f"({APPROX[args.part]} Б) на {delta * 100:.0f}%")
            if not ask("Продолжить?", False):
                return 1

    if not args.no_check_ubi and args.part in UBI_PARTS:
        try:
            params = read_ubi_params(path)
            expected = VOLUMES[args.part]
            actual = params.get("vol_name")
            if actual != expected:
                print(paint(
                    f"ВНИМАНИЕ! В ОБРАЗЕ ТОМ {actual!r}, "
                    f"А РАЗДЕЛ {args.part!r}.", RED, sys.stderr),
                    file=sys.stderr)
                print(paint("ОБРАЗ НЕ СООТВЕТСТВУЕТ РАЗДЕЛУ.",
                            RED, sys.stderr), file=sys.stderr)
                try:
                    answer = input(
                        "Введите yes/да, чтобы записать всё равно: "
                    ).strip().lower()
                except EOFError:
                    answer = ""
                if answer not in ("yes", "да"):
                    print("запись отменена", file=sys.stderr)
                    return 1
            records = check_ubi(path, params)
        except Exception as exc:
            print(paint(f"error: проверка UBI не прошла: {exc}",
                        RED, sys.stderr), file=sys.stderr)
            return 1
        print(f"ФС ok, записей {records}")

    digest = sha256(path)
    print(f"раздел {args.part}, {size} Б, sha256 {digest[:16]}…")
    if not args.no_confirm:
        try:
            confirm = input("Введите yes/да для записи: ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in ("yes", "да", "е"):
            print("запись отменена")
            return 1

    try:
        transport = Transport.wait(args.wait)
    except UsbError as exc:
        print(paint(f"error: {exc}", RED, sys.stderr), file=sys.stderr)
        return 1

    try:
        while True:
            do_write(transport, args.part, path, size)
            if args.no_check_write:
                break

            print()
            got, got_size = transport.read_hash(
                args.part, size, progress(f"проверка {args.part}", size))
            if got == digest and got_size == size:
                break
            print(paint(
                f"error: сверка не прошла: записано {got_size} Б "
                f"sha256 {got[:16]}…, ожидалось {size} Б "
                f"sha256 {digest[:16]}…", RED, sys.stderr), file=sys.stderr)
            if not ask("Повторить запись?", True):
                return 1
    except (UsbError, OSError) as exc:
        print(paint(f"error: {exc}", RED, sys.stderr), file=sys.stderr)
        return 1
    finally:
        transport.close()

    tail = "без сверки" if args.no_check_write else "сверка ok"
    print()
    print(paint(f"готово: {args.part}, {size} Б, "
                f"sha256 {digest[:16]}…, {tail}", GREEN))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
