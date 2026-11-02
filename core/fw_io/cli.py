"""Командная строка `fw_io`: read / write раздела через загрузчик."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .parts import size_for
from .transport import Transport, UsbError

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "_tmp/fw_io"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def make_progress():
    last = 0

    def progress(done: int, total: int) -> None:
        nonlocal last
        if done == total or done - last >= 8 * 1024 * 1024:
            print(f"  {done * 100 // total:3d}%  {done}/{total} Б", flush=True)
            last = done

    return progress


def wait_transport(seconds: int) -> Transport:
    return Transport.wait(seconds=seconds, log=print)


def cmd_read(args) -> int:
    size = size_for(args.part, args.size)
    out = Path(args.out).expanduser().resolve()
    if out.exists() and not args.force:
        print(f"error: уже есть {out} (нужен --force)", file=sys.stderr)
        return 1
    transport = wait_transport(args.wait)
    try:
        print(f"читаю {args.part}: {size} Б -> {out}")
        digest = transport.read_partition(
            args.part, size, out, make_progress(), force=args.force,
            allow_short=args.allow_short)
        actual = out.stat().st_size
        print(f"готово: {out}")
        print(f"прочитано: {actual} из {size} Б")
        print(f"sha256: {digest}")
        return 0
    finally:
        transport.close()


def cmd_write(args) -> int:
    image = Path(args.file).expanduser().resolve()
    if not image.is_file():
        raise SystemExit(f"error: нет файла {image}")
    size = size_for(args.part, args.size)
    if image.stat().st_size != size:
        raise SystemExit(
            f"error: {image}: размер {image.stat().st_size}, ожидался {size}")
    source_sha = sha256(image)
    transport = wait_transport(args.wait)
    try:
        print(f"пишу {args.part}: {image} ({size} Б)")
        print(f"sha256 источника: {source_sha}")
        transport.write_partition(args.part, size, image, make_progress())
        print("запись завершена, проверяю обратным чтением")

        TMP.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        verify = Path(tempfile.mkdtemp(
            prefix=f"verify-{args.part}-{stamp}-", dir=str(TMP)))
        verified = False
        try:
            readback = verify / f"{args.part}.bin"
            actual = transport.read_partition(
                args.part, size, readback, make_progress(), force=True)
            if actual != source_sha:
                raise UsbError(
                    f"проверка не прошла: источник {source_sha}, "
                    f"обратное чтение {actual}; файл оставлен в {readback}"
                )
            verified = True
            print(f"OK: {args.part} совпал, sha256={actual}")
        finally:
            if args.keep_verify:
                print(f"каталог проверки: {verify}")
            elif verified:
                shutil.rmtree(verify, ignore_errors=True)
            else:
                print(f"каталог проверки: {verify}", file=sys.stderr)
        return 0
    finally:
        transport.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fw_io",
        description="Чтение/запись раздела NAND через USB-загрузчик")
    sub = ap.add_subparsers(dest="cmd", required=True)

    read = sub.add_parser("read", help="прочитать раздел")
    read.add_argument("--part", required=True)
    read.add_argument("--out", required=True)
    read.add_argument("--size", type=lambda x: int(x, 0))
    read.add_argument("--wait", type=int, default=300)
    read.add_argument("--force", action="store_true")
    read.add_argument("--allow-short", action="store_true",
                      help="принять частичное чтение (зонд размера)")
    read.set_defaults(func=cmd_read)

    write = sub.add_parser("write", help="записать раздел с проверкой")
    write.add_argument("--part", required=True)
    write.add_argument("--file", required=True)
    write.add_argument("--size", type=lambda x: int(x, 0))
    write.add_argument("--wait", type=int, default=300)
    write.add_argument("--keep-verify", action="store_true")
    write.set_defaults(func=cmd_write)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (UsbError, OSError, ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
