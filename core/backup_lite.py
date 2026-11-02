"""Упрощённый бэкап разделов для лёгкой редакции.

Читает все разделы из фиксированного списка через `fw_io`, каждый
дважды, и сравнивает SHA-256. Размер берётся из `fw_io.parts`;
обрыв чтения — остановка с просьбой перезапустить бэкап. Раздел пишется в
`<part>.bin.bad` и переименовывается в `<part>.bin` только после
сверки: прерванный прогон не оставляет готовый `.bin`.

Любая неудача (раздел не отдаётся, обрыв, расхождение чтений) -
остановка, удаляется только `backup/parts_bad`, прежний
`backup/parts` остаётся как был. При успехе старый `parts`
упаковывается в zip, а `parts_bad` становится `parts`.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from common.archive import archive_folder
from common.colors import GREEN, RED, paint
from common.sizes import APPROX
from common.ubi_check import check_ubi
from fw_io.parts import size_for
from fw_io.transport import Transport, UsbError

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "backup" / "parts"
STAGING = ROOT / "backup" / "parts_bad"

# Заведомо больше любого раздела (вся NAND 256 МиБ).
BIG = 256 * 1024 * 1024

# Разделы с UBI/UBIFS: их можно проверить через ubi_reader.
UBI_PARTS = {"system_a", "system_b", "data"}

# Только разделы, которые загрузчик отдаёт через `store`.
# `tpl` и `bootloader` так не читаются (нужен raw-путь).
PARTS = [
    "system_a", "system_b", "data",
    "boot_a", "boot_b", "misc",
]



def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def discard_staging() -> None:
    """Удаляет незавершённый бэкап; ошибки очистки не мешают отчёту."""
    try:
        if STAGING.is_dir():
            shutil.rmtree(STAGING)
        elif STAGING.exists():
            STAGING.unlink()
    except OSError:
        pass


def prepare_staging() -> None:
    """Готовит пустую `backup/parts_bad`."""
    if STAGING.is_dir():
        shutil.rmtree(STAGING)
    elif STAGING.exists():
        STAGING.unlink()
    STAGING.mkdir(parents=True, exist_ok=True)


def swap_staging() -> Path | None:
    """Архивирует старый `parts` и заменяет его на staging."""
    archived = None
    if BACKUP.is_dir() and any(BACKUP.iterdir()):
        print("Упаковываю старые файлы...")
        archived = archive_folder(BACKUP, prefix="parts")
        if archived:
            print(f"Старые файлы упакованы: {archived}")
    if BACKUP.is_dir():
        shutil.rmtree(BACKUP)
    elif BACKUP.exists():
        BACKUP.unlink()
    STAGING.rename(BACKUP)
    return archived


def progress(part: str, label: str):
    """Проценты от приблизительного размера раздела, не от запроса."""
    last = 0
    approx = APPROX.get(part, BIG)

    def show(done: int, total: int) -> None:
        nonlocal last
        if done == total or done - last >= 16 * 1024 * 1024:
            print(f"  {label} {part}: {done * 100 // approx}% ({done} Б)",
                  flush=True)
            last = done

    return show


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backup_lite",
        description="Бэкап разделов через fw_io, с двойным чтением")
    parser.add_argument("--wait", type=int, default=120,
                        help="сколько ждать загрузчик, секунд")
    parser.add_argument("--no-check-ubi", action="store_true",
                        help="не проверять UBI/UBIFS через ubi_reader")
    parser.add_argument("--no-check-read", action="store_true",
                        help="не читать второй раз и не сверять")
    args = parser.parse_args(argv)

    try:
        prepare_staging()
    except OSError as exc:
        print(paint(f"error: не удалось подготовить {STAGING}: {exc}",
                    RED, sys.stderr), file=sys.stderr)
        return 1
    try:
        transport = Transport.wait(args.wait)
    except UsbError as exc:
        discard_staging()
        print(paint(f"error: {exc}", RED, sys.stderr), file=sys.stderr)
        return 1

    try:
        for part in PARTS:
            target = STAGING / f"{part}.bin"
            working = STAGING / f"{part}.bin.bad"
            working.unlink(missing_ok=True)

            print()
            print(f"читаю {part}")
            size = size_for(part)
            try:
                sha_first = transport.read_partition(
                    part, size, working, progress(part, "чтение"),
                    force=True)
                got = working.stat().st_size
                if got != size:
                    raise UsbError(f"прочитано {got} из {size} Б")

                if not args.no_check_read:
                    print()
                    sha_second, size_second = transport.read_hash(
                        part, size, progress(part, "проверка"))
                    if size_second != size:
                        raise UsbError(
                            f"прочитано {size_second} из {size} Б")
                    if sha_first != sha_second:
                        raise UsbError(
                            f"хеши чтений разные: "
                            f"{sha_first[:12]} и {sha_second[:12]}")

                if not args.no_check_ubi and part in UBI_PARTS:
                    try:
                        records = check_ubi(working)
                    except Exception as exc:
                        discard_staging()
                        print(paint(
                            f"error: {part}: проверка UBI не прошла: "
                            f"{exc}; новый бэкап удалён, прежний сохранён",
                            RED, sys.stderr), file=sys.stderr)
                        return 1

                working.replace(target)
            except (UsbError, OSError) as exc:
                discard_staging()
                print(paint(f"error: {part}: {exc}", RED, sys.stderr),
                      file=sys.stderr)
                print(paint("Неудачное чтение. Отключите колонку и запустите "
                            "«Бекап» заново.", RED, sys.stderr),
                      file=sys.stderr)
                return 1

            print()
            line = f"{part}: {size} Б, sha256 {sha_first[:16]}…"
            if not args.no_check_ubi and part in UBI_PARTS:
                line += f", ФС ok, записей {records}"

            print(line)
    finally:
        transport.close()

    try:
        swap_staging()
    except OSError as exc:
        print(paint(f"error: не удалось заменить {BACKUP}: {exc}",
                    RED, sys.stderr), file=sys.stderr)
        if BACKUP.exists():
            print(f"старый бэкап: {BACKUP}", file=sys.stderr)
        else:
            print(f"старый бэкап: zip в {BACKUP.parent}", file=sys.stderr)
        if STAGING.exists():
            print(f"новый бэкап: {STAGING}", file=sys.stderr)
        return 1

    total = sum(p.stat().st_size for p in BACKUP.glob("*.bin"))
    print()
    print(paint(f"готово: разделов {len(list(BACKUP.glob('*.bin')))}, "
                f"всего {total} Б", GREEN))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
