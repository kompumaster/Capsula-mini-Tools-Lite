#!/usr/bin/env python3
"""Перезагрузка колонки: сначала SSH, при неудаче — ADB.

IP по умолчанию ищется через `common.find_ip.find_capsula()`;
`--ip` задаёт адрес вручную.

SSH: `capsula@IP`, пароль из `CAPSULA_SSH_PASSWORD` (по умолчанию
`mini`). Если есть `sshpass` — используется он, иначе `SSH_ASKPASS`
(Linux/macOS) или ключ (`BatchMode=yes`, Windows).

ADB: клиент `adb` из `PATH`/`CAPSULA_ADB`, если есть; иначе —
минимальный протокол ADB напрямую на `IP:5555` (`reboot:`).
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import struct
import subprocess
import sys
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.find_ip import find_capsula  # noqa: E402

SSH_USER = "capsula"
SSH_PASSWORD = os.environ.get("CAPSULA_SSH_PASSWORD", "mini")
SSH_CONNECT_TIMEOUT = 5
TIMEOUT = 15
ADB_PORT = 5555

ROOT = Path(__file__).resolve().parents[2]
KNOWN_HOSTS = ROOT / "_tmp" / "known_hosts"
ASKPASS = ROOT / "_tmp" / "askpass.sh"

# nohup и sleep — чтобы ssh успел выйти до перезагрузки.
REMOTE_REBOOT = "nohup sh -c 'sleep 1; sync; /sbin/reboot' >/dev/null 2>&1 &"

# Минимальный ADB-протокол (без клиента adb).
ADB_CNXN = 0x4E584E43
ADB_AUTH = 0x48545541
ADB_OPEN = 0x4E45504F
ADB_OKAY = 0x59414B4F
ADB_CLSE = 0x45534C43
ADB_VERSION = 0x01000001
ADB_MAXDATA = 4096

Log = Callable[[str], None]


def _run(command: list[str], timeout: int = TIMEOUT,
         env: dict[str, str] | None = None,
         new_session: bool = False):
    kwargs = {}
    if new_session and os.name != "nt":
        kwargs["start_new_session"] = True
    return subprocess.run(command, capture_output=True, text=True,
                          timeout=timeout, check=False, env=env,
                          **kwargs)


def _tail(result) -> str:
    """Последняя строка вывода команды для сообщения об ошибке."""
    text = (result.stderr or result.stdout or "").strip()
    return text.splitlines()[-1] if text else ""


# ------------------------------------------------------------------ SSH

def _askpass_env() -> dict[str, str] | None:
    """Окружение с SSH_ASKPASS; `None`, если скрипт не создать."""
    if os.name == "nt":
        return None
    try:
        ASKPASS.parent.mkdir(parents=True, exist_ok=True)
        ASKPASS.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"${CAPSULA_SSH_PASSWORD:-mini}\"\n",
            encoding="utf-8")
        os.chmod(ASKPASS, 0o700)
    except OSError:
        return None
    env = os.environ.copy()
    env["SSH_ASKPASS"] = str(ASKPASS)
    env["SSH_ASKPASS_REQUIRE"] = "force"
    env.setdefault("DISPLAY", ":0")
    env["CAPSULA_SSH_PASSWORD"] = SSH_PASSWORD
    return env


def _ssh_setup(ip: str) -> tuple[list[str] | None, dict[str, str] | None]:
    """Команда ssh и окружение; `(None, None)`, если клиента нет."""
    if shutil.which("ssh") is None:
        return None, None
    sshpass = shutil.which("sshpass")
    if sshpass:
        command = [sshpass, "-p", SSH_PASSWORD, "ssh"]
        env = None
    else:
        env = _askpass_env()
        if env:
            command = ["ssh"]
        else:
            command = ["ssh", "-o", "BatchMode=yes"]
            env = None
    command += [
        "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
        f"{SSH_USER}@{ip}",
    ]
    return command, env


def ssh_reboot(ip: str, log: Log = print) -> bool:
    """Перезагрузить по SSH; `True`, если команда принята."""
    command, env = _ssh_setup(ip)
    if command is None:
        log("SSH: клиент ssh не найден")
        return False
    KNOWN_HOSTS.parent.mkdir(parents=True, exist_ok=True)
    try:
        check = _run(command + ["true"], timeout=SSH_CONNECT_TIMEOUT + 5,
                     env=env, new_session=env is not None)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"SSH: не удалось запустить ssh: {exc}")
        return False
    if check.returncode != 0:
        log("SSH: " + (_tail(check) or "нет связи"))
        return False
    try:
        result = _run(command + [REMOTE_REBOOT], env=env,
                      new_session=env is not None)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"SSH: команда не отправилась: {exc}")
        return False
    if result.returncode == 0:
        return True
    log("SSH: " + (_tail(result) or "команда отклонена"))
    return False


# ------------------------------------------------------------------ ADB

def _find_adb() -> str | None:
    """Путь к клиенту adb: env, PATH или типовые места Windows."""
    for name in ("CAPSULA_ADB", "ADB"):
        value = os.environ.get(name)
        if not value:
            continue
        path = Path(value)
        if path.is_file():
            return str(path)
        found = shutil.which(value)
        if found:
            return found
    found = shutil.which("adb")
    if found:
        return found
    if os.name == "nt":
        roots = [os.environ.get("LOCALAPPDATA"),
                 os.environ.get("USERPROFILE")]
        candidates = [Path("C:/platform-tools/adb.exe")]
        for root in roots:
            if root:
                candidates += [
                    Path(root) / "Android/Sdk/platform-tools/adb.exe",
                    Path(root) / "platform-tools/adb.exe",
                ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def _adb_cli_reboot(adb: str, ip: str, log: Log) -> bool:
    """Перезагрузка штатным клиентом adb."""
    target = f"{ip}:{ADB_PORT}"
    try:
        connect = _run([adb, "connect", target])
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"ADB: не удалось запустить adb: {exc}")
        return False
    text = ((connect.stdout or "") + (connect.stderr or "")).lower()
    if connect.returncode != 0 or any(
            word in text for word in ("failed", "unable", "cannot")):
        log("ADB: " + (_tail(connect) or "нет связи"))
        return False
    try:
        result = _run([adb, "-s", target, "reboot"])
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"ADB: команда не отправилась: {exc}")
        return False
    if result.returncode == 0:
        return True
    log("ADB: " + (_tail(result) or "команда отклонена"))
    return False


def _adb_packet(command: int, arg0: int = 0, arg1: int = 0,
                data: bytes = b"") -> bytes:
    """Заголовок пакета ADB и данные (little-endian)."""
    return struct.pack("<6I", command, arg0, arg1, len(data),
                       sum(data) & 0xFFFFFFFF,
                       command ^ 0xFFFFFFFF) + data


def _adb_recv(sock, size: int) -> bytes | None:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def _adb_read(sock) -> tuple[int, int, int, bytes] | None:
    head = _adb_recv(sock, 24)
    if head is None:
        return None
    command, arg0, arg1, size, _crc, _magic = struct.unpack("<6I", head)
    if size > 4 * 1024 * 1024:
        raise ValueError(f"ADB: слишком большой пакет {size}")
    data = _adb_recv(sock, size) if size else b""
    if data is None:
        return None
    return command, arg0, arg1, data


def _adb_raw_reboot(ip: str, log: Log) -> bool:
    """Перезагрузка по протоколу ADB напрямую, без клиента adb."""
    try:
        with socket.create_connection((ip, ADB_PORT), timeout=5) as sock:
            sock.settimeout(5)
            sock.sendall(_adb_packet(ADB_CNXN, ADB_VERSION, ADB_MAXDATA,
                                     b"host::\0"))
            hello = _adb_read(sock)
            if hello is None:
                log("ADB: нет ответа")
                return False
            command, _arg0, _arg1, _data = hello
            if command == ADB_AUTH:
                log("ADB: устройство требует авторизацию")
                return False
            if command != ADB_CNXN:
                log(f"ADB: неожиданный ответ 0x{command:08x}")
                return False

            sock.sendall(_adb_packet(ADB_OPEN, 1, 0, b"reboot:\0"))
            while True:
                packet = _adb_read(sock)
                if packet is None:
                    log("ADB: соединение закрыто без подтверждения")
                    return False
                command, _arg0, _arg1, _data = packet
                if command == ADB_OKAY:
                    return True
                if command == ADB_CLSE:
                    log("ADB: команда отклонена")
                    return False
    except (OSError, ValueError) as exc:
        log(f"ADB: {exc}")
        return False


def adb_reboot(ip: str, log: Log = print) -> bool:
    """Перезагрузить по ADB: клиент adb, иначе напрямую по протоколу."""
    adb = _find_adb()
    if adb:
        if _adb_cli_reboot(adb, ip, log):
            return True
        log("ADB: клиент не сработал, пробую напрямую...")
    else:
        log("ADB: клиент adb не найден, подключаюсь напрямую...")
    return _adb_raw_reboot(ip, log)


# ------------------------------------------------------------------ main

def reboot(ip: str | None = None, log: Log = print) -> int:
    """Найти колонку и перезагрузить: SSH, затем ADB."""
    if ip is None:
        log("Ищу колонку в сети...")
        ip = find_capsula()
    if not ip:
        log("error: колонка не найдена")
        return 1
    log(f"колонка: {ip}")

    if ssh_reboot(ip, log):
        log("перезагрузка отправлена по SSH")
        return 0

    log("SSH не сработал, пробую ADB...")
    if adb_reboot(ip, log):
        log("перезагрузка отправлена по ADB")
        return 0

    log("error: не удалось перезагрузить ни по SSH, ни по ADB")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Перезагрузка колонки: SSH, затем ADB")
    parser.add_argument("--ip", help="адрес колонки; без него — поиск в сети")
    args = parser.parse_args(argv)
    return reboot(args.ip)


if __name__ == "__main__":
    raise SystemExit(main())
