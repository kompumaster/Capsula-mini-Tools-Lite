#!/bin/sh
# Запуск меню Capsula Mini Tools Lite.
# Вся логика меню — в core/tui; этот файл только готовит Python.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP="$HERE/core/tui/app.py"
PY="$HERE/_venv/bin/python"
REQ="$HERE/requirements.txt"

if [ "$#" -gt 0 ]; then
    echo "Меню запускается без аргументов." >&2
    echo "Инструменты с флагами: core/backup_lite.py, core/write_lite.py, core/fw_patch_lite.py." >&2
    exit 2
fi

if [ ! -f "$APP" ]; then
    echo "error: нет $APP" >&2
    exit 1
fi

find_python() {
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && \
           "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
               >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# _venv годится, только если Python запускается, sys.prefix совпадает
# с папкой, базовый Python из pyvenv.cfg существует на этой машине,
# а версия не ниже 3.9.
venv_ok() {
    [ -x "$PY" ] || return 1
    "$PY" -c 'import os,pathlib,sys
v = pathlib.Path(sys.argv[1]).resolve()
c = pathlib.Path(sys.prefix) / "pyvenv.cfg"
h = [l.split("=", 1)[1].strip() for l in c.read_text().splitlines()
     if l.startswith("home")] if c.is_file() else []
sys.exit(0 if pathlib.Path(sys.prefix).resolve() == v and h
         and os.path.isdir(h[0])
         and sys.version_info >= (3, 9) else 1)' "$HERE/_venv" >/dev/null 2>&1
}

if ! venv_ok; then
    BASE=$(find_python || true)
    if [ -z "$BASE" ]; then
        found=$(command -v python3 || command -v python || true)
        if [ -n "$found" ]; then
            version=$("$found" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || true)
            echo "error: нужен Python 3.9 или новее; найден ${version:-неизвестной версии}" >&2
        else
            echo "error: не найден Python 3.9 или новее" >&2
        fi
        exit 1
    fi

    if [ -d "$HERE/_venv" ]; then
        printf '_venv не подходит (другая машина или Python старше 3.9). Создать заново и установить зависимости? [Y/n]: '
    else
        printf 'Создать _venv и установить зависимости? [Y/n]: '
    fi
    answer=""
    if [ -t 0 ]; then
        read -r answer || true
    else
        answer=n
    fi
    case "$answer" in
        n|N|no|NO|нет|НЕТ|т|Т)
            echo "Отменено." >&2
            exit 1
            ;;
    esac

    rm -rf "$HERE/_venv"
    "$BASE" -m venv "$HERE/_venv" || {
        echo "error: не удалось создать _venv" >&2
        exit 1
    }
    "$PY" -m pip install -r "$REQ" || {
        echo "error: не удалось установить зависимости" >&2
        exit 1
    }
fi

if ! PYTHONPATH="$HERE/core" "$PY" -c \
        "import backup_lite, write_lite, fw_patch_lite" >/dev/null 2>&1; then
    echo "error: зависимости не установлены; выполните:" >&2
    echo "  $PY -m pip install -r $REQ" >&2
    exit 1
fi

exec "$PY" "$APP"
