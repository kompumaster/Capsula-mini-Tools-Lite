"""Сборка образов через UbiTar.

`unpack` делает tar из раздела, `pack` собирает образ в `<имя>.bad`,
проверяет размер и параметры тома и только потом переименовывает.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .assets import UBITAR
from .errors import PatchError

if str(UBITAR) not in sys.path:
    sys.path.insert(0, str(UBITAR))

from ubitar.ubi_params import read_params  # noqa: E402

TIMEOUT = 900


def _run(args: list[str], timeout: int = TIMEOUT) -> str:
    env = os.environ.copy()
    paths = [str(UBITAR)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)

    command = [sys.executable, "-m", "ubitar", *args]
    try:
        result = subprocess.run(command, env=env, capture_output=True,
                                text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise PatchError(
            f"ubitar {args[0]}: таймаут {timeout} с") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise PatchError(
            f"ubitar {args[0]} не запустился: {exc}") from exc

    if result.returncode != 0:
        tail = (result.stdout + result.stderr).strip().splitlines()[-8:]
        raise PatchError(
            f"ubitar {args[0]} завершился с кодом {result.returncode}:\n"
            + "\n".join(tail))
    return result.stdout


def unpack(image: Path, part: str, out: Path, *,
           force: bool = False,
           report: bool = False) -> Path | tuple[Path, str]:
    """Раздел -> tar. Возвращает путь; с `report` — путь и вывод UbiTar."""
    image = Path(image)
    out = Path(out)
    if not image.is_file():
        raise PatchError(f"нет образа {image}")
    if out.exists() and not force:
        raise PatchError(f"tar уже есть: {out} (нужен --force)")

    out.parent.mkdir(parents=True, exist_ok=True)
    args = ["unpack", "--image", str(image), "--out", str(out),
            "--part", part]
    if force:
        args.append("--force")
    output = _run(args)
    if not out.is_file():
        raise PatchError(f"ubitar не создал tar {out}")
    if report:
        return out, output
    return out


def pack(tar: Path, out: Path, *, compr: str = "zlib",
         expected: dict | None = None, force: bool = False) -> Path:
    """tar -> образ. Собирает в `.bad`, проверяет и переименовывает."""
    tar = Path(tar)
    out = Path(out)
    if not tar.is_file():
        raise PatchError(f"нет tar {tar}")
    if out.exists() and not force:
        raise PatchError(f"образ уже есть: {out} (нужен --force)")

    out.parent.mkdir(parents=True, exist_ok=True)
    bad = out.with_name(out.name + ".bad")
    bad.unlink(missing_ok=True)

    _run(["pack", "--tar", str(tar), "--out", str(bad),
          "--compr", compr])
    if not bad.is_file():
        raise PatchError(f"ubitar не создал образ {bad}")

    if expected:
        size = expected.get("size", expected.get("part_size"))
        if size is not None and bad.stat().st_size != int(size):
            raise PatchError(
                f"{bad}: размер {bad.stat().st_size}, ожидался {size}")
        try:
            params = read_params(bad)
        except Exception as exc:
            raise PatchError(f"{bad}: не читаются параметры: {exc}") from exc
        for key in ("vol_name", "reserved_pebs", "image_seq"):
            if key in expected and params.get(key) != expected[key]:
                raise PatchError(
                    f"{bad}: {key}={params.get(key)!r}, "
                    f"ожидалось {expected[key]!r}")

    os.replace(bad, out)
    return out
