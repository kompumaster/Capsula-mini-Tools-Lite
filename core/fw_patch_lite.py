#!/usr/bin/env python3
"""Патчер разделов для лёгкой редакции.

Примеры:
    fw_patch_lite.py --src backup/parts --status
    fw_patch_lite.py --src backup/parts --out patched --adb-on --ssh-on
    fw_patch_lite.py --src patched --out patched --adb-off
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from common.archive import archive_folder
from common.colors import GREEN, RED, paint
from fwpatch import assets, build, checks, status
from fwpatch.errors import PatchError
from fwpatch.patches import BY_PART, PART_ORDER, REGISTRY
from fwpatch.patches.common import stub_hashes
from fwpatch.tar_tree import TarTree, diff

STATUS_NAME = "status.txt"
TMP = assets.ROOT / "_tmp"
STAGING_SUFFIX = "_bad"


def ask(question: str, default: bool = False) -> bool:
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


def load_status(src: Path) -> dict[str, str]:
    path = src / STATUS_NAME
    if not path.is_file():
        return {}
    return status.read_status(path)


def resolve_input(src: Path, part: str,
                  data: dict[str, str]) -> Path:
    name = data.get(f"{part}.file")
    if name:
        if "/" in name or "\\" in name or name in (".", ".."):
            raise PatchError(f"status: недопустимое имя файла {name!r}")
    path = src / (name or f"{part}.bin")
    if not path.is_file():
        raise PatchError(f"нет файла {path}")
    return path


def toggle_dest(module) -> tuple[str, str]:
    """Имена argparse-атрибутов для include/exclude-патча."""
    return f"{module.FLAG}_on", f"{module.FLAG}_off"


def output_name(part: str, tree: TarTree) -> str:
    states, _ = status.detect(tree, part)
    known = stub_hashes()
    keys: list[str] = []
    for module in BY_PART.get(part, ()):
        if module.KIND == "toggle":
            if states.get(module.KEY) == "on":
                keys.append(module.KEY)
        elif (tree.kind(module.PATH) == "file"
              and tree.sha256(module.PATH) in known):
            keys.append(module.KEY)
    suffix = "." + "-".join(keys) if keys else ""
    return f"{part}{suffix}.bin"


def save_status(folder: Path, statuses: list[status.Status]) -> None:
    path = folder / STATUS_NAME
    existing: dict[str, str] = {}
    if path.is_file():
        existing = status.read_status(path)
    for entry in statuses:
        prefix = f"{entry.part}."
        for key in [k for k in existing if k.startswith(prefix)]:
            del existing[key]

    lines = ["# fw_patch_lite status 1"]
    lines.extend(f"{key}={value}" for key, value in existing.items())
    for entry in statuses:
        lines.extend(status.render([entry]).splitlines()[1:])

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def compare_status(data: dict[str, str], part: str, image: Path,
                   tree: TarTree) -> None:
    if not data:
        return
    actual, _ = status.detect(tree, part)
    problems = []
    recorded_sha = data.get(f"{part}.sha256")
    if recorded_sha:
        actual_sha = status.sha256_file(image)
        if recorded_sha != actual_sha:
            problems.append("sha256 образа")
    for key in status.PART_KEYS.get(part, ()):
        recorded = data.get(f"{part}.{key}")
        if recorded and recorded != actual.get(key):
            problems.append(
                f"{key}: в статусе {recorded}, фактически {actual.get(key)}")
    if not problems:
        return
    print(f"{part}: статус не совпадает с образом:")
    for problem in problems:
        print(f"  {problem}")
    if not ask("Продолжать?", True):
        raise PatchError("отменено")


def apply_part(tree: TarTree, part: str, args) -> None:
    for module in BY_PART.get(part, ()):
        if module.KIND == "toggle":
            on, off = toggle_dest(module)
            if getattr(args, on):
                module.apply(tree, ask)
            elif getattr(args, off):
                module.remove(tree, ask)
        elif getattr(args, f"{module.FLAG}_kill"):
            module.kill(tree)


def needed_parts(args) -> list[str]:
    result = []
    for part in PART_ORDER:
        for module in BY_PART[part]:
            if module.KIND == "toggle":
                on, off = toggle_dest(module)
                selected = getattr(args, on) or getattr(args, off)
            else:
                selected = getattr(args, f"{module.FLAG}_kill")
            if selected:
                result.append(part)
                break
    return result


def compression(args) -> str:
    if args.lzo:
        return "lzo"
    if args.zstd:
        print("warning: zstd не читается ядром 4.9", file=sys.stderr)
        return "zstd"
    return "zlib"


def state_text(part: str, states: dict[str, str]) -> str:
    return " ".join(
        f"{key}={states.get(key, 'off')}"
        for key in status.PART_KEYS[part])


def requested_text(args) -> str:
    items = []
    for module in REGISTRY:
        if module.KIND == "toggle":
            on, off = toggle_dest(module)
            if getattr(args, on):
                items.append(f"{module.KEY}=on")
            elif getattr(args, off):
                items.append(f"{module.KEY}=off")
        elif getattr(args, f"{module.FLAG}_kill"):
            items.append(f"{module.KEY}=kill")
    return ", ".join(items)


def print_diff(added: set, removed: set, changed: set) -> None:
    items = ([f"+ {path}" for path in sorted(added)]
             + [f"- {path}" for path in sorted(removed)]
             + [f"~ {path}" for path in sorted(changed)])
    print("  изменения:")
    for item in items:
        print(f"  {item}")


def run_status(args) -> int:
    src = Path(args.src).resolve()
    data = load_status(src)
    statuses = []
    TMP.mkdir(parents=True, exist_ok=True)

    for part in PART_ORDER:
        name = data.get(f"{part}.file")
        path = (resolve_input(src, part, data) if name
                else src / f"{part}.bin")
        if not path.is_file():
            if name:
                raise PatchError(f"нет файла {path}")
            continue
        params = checks.validate_image(path, part, no_check_size=True)
        with tempfile.TemporaryDirectory(dir=str(TMP)) as tmp:
            tar = Path(tmp) / f"{part}.tar"
            build.unpack(path, part, tar)
            tree = TarTree(tar)
            statuses.append(
                status.make_status(part, path.name, path, tree, params))

    if not statuses:
        raise PatchError(f"в {src} нет "
                          f"{', '.join(p + '.bin' for p in PART_ORDER)}")
    status.write_status(src / STATUS_NAME, statuses)
    print(f"источник: {src}")
    print()
    for entry in statuses:
        print(f"{entry.file}: {state_text(entry.part, entry.states)}")
    print()
    print(f"status: {src / STATUS_NAME}")
    return 0


def staging_for(out: Path) -> Path:
    """`patched/parts` -> `patched/parts_bad`."""
    return out.with_name(out.name + STAGING_SUFFIX)


def discard_staging(staging: Path) -> None:
    """Удаляет незавершённую сборку; ошибки очистки не мешают отчёту."""
    try:
        if staging.is_dir():
            shutil.rmtree(staging)
        elif staging.exists():
            staging.unlink()
    except OSError:
        pass


def prepare_staging(staging: Path) -> None:
    """Готовит пустую папку сборки."""
    if staging.is_dir():
        shutil.rmtree(staging)
    elif staging.exists():
        staging.unlink()
    staging.mkdir(parents=True, exist_ok=True)


def swap_staging(out: Path, staging: Path) -> Path | None:
    """Архивирует старый `out` и заменяет его на staging."""
    archived = None
    if out.is_dir() and any(out.iterdir()):
        print("Упаковываю старые файлы...")
        archived = archive_folder(out, prefix=out.name)
        if archived:
            print(f"Старые файлы упакованы: {archived}")
    if out.is_dir():
        shutil.rmtree(out)
    elif out.exists():
        out.unlink()
    staging.rename(out)
    return archived


def run_patch(args) -> int:
    src = Path(args.src).resolve()
    out = Path(args.out).resolve()
    in_place = out == src
    staging = None if in_place else staging_for(out)
    if (staging is not None
            and out == (assets.ROOT / "backup" / "parts").resolve()):
        raise PatchError("--out не может быть backup/parts: конфликт staging")
    print(f"источник: {src}")
    print(f"выход:    {out}")
    print(f"применяем патчи: {requested_text(args)}")
    print()

    data = load_status(src)
    parts = needed_parts(args)
    paths = {part: resolve_input(src, part, data) for part in parts}
    params = {
        part: checks.validate_image(
            paths[part], part, no_check_size=args.no_check_size, ask=ask)
        for part in parts
    }

    if staging is None:
        out.mkdir(parents=True, exist_ok=True)
        if any(out.iterdir()):
            print("выход совпадает с источником — старые файлы не архивирую")
    else:
        try:
            prepare_staging(staging)
        except OSError as exc:
            print(paint(f"error: не удалось подготовить {staging}: {exc}",
                        RED, sys.stderr), file=sys.stderr)
            return 1

    dest = staging if staging is not None else out
    new_statuses = []
    inspected_statuses = []
    compr = compression(args)

    try:
        TMP.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(TMP)) as tmp:
            for part in parts:
                image = paths[part]
                tar = Path(tmp) / f"{part}.tar"
                build.unpack(image, part, tar)
                tree = TarTree(tar)
                compare_status(data, part, image, tree)

                before_states, _ = status.detect(tree, part)
                before = tree.snapshot()
                apply_part(tree, part, args)
                after = tree.snapshot()
                added, removed, changed = diff(before, after)
                if not (added or removed or changed):
                    print(f"{image.name}: "
                          f"{state_text(part, before_states)} — изменений нет")
                    inspected_statuses.append(
                        status.make_status(part, image.name, image, tree,
                                           params[part]))
                    print()
                    continue

                after_states, _ = status.detect(tree, part)
                print(f"{image.name}: {state_text(part, before_states)}"
                      f" -> {state_text(part, after_states)}")
                print_diff(added, removed, changed)

                out_tar = dest / f"{part}.tar"
                name = output_name(part, tree)
                final = dest / name
                if final.exists() and not args.force:
                    raise PatchError(
                        f"образ уже есть: {final} (нужен --force)")

                tree.write(out_tar)
                build.pack(out_tar, final, compr=compr,
                           expected=params[part], force=args.force)
                entry = status.make_status(part, final.name, final, tree,
                                           params[part])
                new_statuses.append(entry)
                print(f"  tar:    {out_tar}")
                print(f"  образ:  {final} "
                      f"({final.stat().st_size} Б, {compr})")
                print()

        if new_statuses:
            save_status(dest, new_statuses)
    except Exception:
        if staging is not None:
            discard_staging(staging)
        raise

    if new_statuses:
        if staging is not None:
            try:
                archived = swap_staging(out, staging)
            except OSError as exc:
                print(paint(f"error: не удалось заменить {out}: {exc}",
                            RED, sys.stderr), file=sys.stderr)
                if out.exists():
                    print(f"старый набор: {out}", file=sys.stderr)
                else:
                    print(f"старый набор: zip в {out.parent}",
                          file=sys.stderr)
                print(f"новый набор: {staging}", file=sys.stderr)
                return 1
            if archived:
                print()
        print(paint(f"готово: образов {len(new_statuses)}", GREEN))
    else:
        if staging is not None:
            discard_staging(staging)
        if inspected_statuses and not (src / STATUS_NAME).is_file():
            status.write_status(src / STATUS_NAME, inspected_statuses)
        print(paint("готово: новых образов нет — "
                    "запрошенные патчи уже в этом состоянии", GREEN))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fw_patch_lite",
        description="Патчер разделов Lite: tar через UbiTar")
    parser.add_argument("--src", required=True,
                        help="папка с исходными образами")
    parser.add_argument("--out", help="папка для tar и готовых образов")
    parser.add_argument("--status", action="store_true",
                        help="только проверить патчи и записать status.txt")

    for module in REGISTRY:
        if module.KIND == "toggle":
            parser.add_argument(f"--{module.FLAG}-on", action="store_true",
                                help=f"{module.TITLE}: применить")
            parser.add_argument(f"--{module.FLAG}-off", action="store_true",
                                help=f"{module.TITLE}: отменить")
        else:
            parser.add_argument(f"--{module.FLAG}-kill", action="store_true",
                                help=f"{module.TITLE}: "
                                     f"{module.NAME} -> заглушка")

    parser.add_argument("--no-check-size", action="store_true",
                        help="не спрашивать при отклонении размера >10%%")
    parser.add_argument("--lzo", action="store_true",
                        help="сжать UBIFS через lzo")
    parser.add_argument("--zstd", action="store_true",
                        help="сжать UBIFS через zstd (ядро 4.9 не читает)")
    parser.add_argument("--force", action="store_true",
                        help="перезаписать готовый образ")
    return parser


def selected_flags(args) -> list[bool]:
    result = []
    for module in REGISTRY:
        if module.KIND == "toggle":
            on, off = toggle_dest(module)
            result += [getattr(args, on), getattr(args, off)]
        else:
            result.append(getattr(args, f"{module.FLAG}_kill"))
    return result


def validate(args) -> None:
    patch_flags = selected_flags(args)
    if args.status:
        if any(patch_flags):
            raise PatchError("--status несовместим с патч-флагами")
        return
    if not any(patch_flags):
        raise PatchError("нужен хотя бы один патч-флаг")
    if not args.out:
        raise PatchError("для патча нужен --out")
    if not needed_parts(args):
        raise PatchError("выбранные патчи не привязаны к разделам")
    for module in REGISTRY:
        if module.KIND != "toggle":
            continue
        on, off = toggle_dest(module)
        if getattr(args, on) and getattr(args, off):
            raise PatchError(
                f"--{module.FLAG}-on и --{module.FLAG}-off несовместимы")
    if args.lzo and args.zstd:
        raise PatchError("--lzo и --zstd несовместимы")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate(args)
        if args.status:
            return run_status(args)
        return run_patch(args)
    except (PatchError, OSError) as exc:
        print(paint(f"error: {exc}", RED, sys.stderr), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
