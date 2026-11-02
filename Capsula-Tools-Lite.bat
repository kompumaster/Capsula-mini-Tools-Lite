@echo off
rem Запуск меню Capsula Mini Tools Lite.
rem Вся логика меню — в core\tui; этот файл только готовит Python.
chcp 65001 >nul
title Capsula-mini Tools Lite
setlocal EnableDelayedExpansion
set "HERE=%~dp0"
set "APP=%HERE%core\tui\app.py"
set "PY=%HERE%_venv\Scripts\python.exe"
set "REQ=%HERE%requirements.txt"
set "PYTHONUTF8=1"

if not "%~1"=="" (
    echo Меню запускается без аргументов.
    echo Инструменты с флагами: core\backup_lite.py, core\write_lite.py, core\fw_patch_lite.py.
    pause
    exit /b 2
)

if not exist "%APP%" (
    echo error: нет "%APP%"
    pause
    exit /b 1
)

set "VENV_OK=0"
if exist "%PY%" (
    "%PY%" -c "import os,pathlib,sys;v=pathlib.Path(sys.argv[1]).resolve();c=pathlib.Path(sys.prefix)/'pyvenv.cfg';h=[l.split('=',1)[1].strip() for l in c.read_text().splitlines() if l.startswith('home')] if c.is_file() else [];sys.exit(0 if pathlib.Path(sys.prefix).resolve()==v and h and os.path.isdir(h[0]) and sys.version_info>=(3,9) else 1)" "%HERE%_venv" >nul 2>nul
    if not errorlevel 1 set "VENV_OK=1"
)

if "%VENV_OK%"=="0" (
    if exist "%HERE%_venv" (
        set /p "answer=_venv не подходит (другая машина или Python старше 3.9). Создать заново и установить зависимости? [Y/n]: "
    ) else (
        set /p "answer=Создать _venv и установить зависимости? [Y/n]: "
    )
    if /I "!answer!"=="n" goto cancel
    if /I "!answer!"=="no" goto cancel
    if /I "!answer!"=="нет" goto cancel
    if /I "!answer!"=="т" goto cancel

    set "BASE="
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if not errorlevel 1 set "BASE=py -3"
    if not defined BASE (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
        if not errorlevel 1 set "BASE=python"
    )
    if not defined BASE (
        echo error: нужен Python 3.9 или новее
        pause
        exit /b 1
    )

    if exist "%HERE%_venv" (
        rmdir /s /q "%HERE%_venv" >nul 2>nul
        if exist "%HERE%_venv" (
            powershell -NoProfile -Command "Remove-Item -LiteralPath '%HERE%_venv' -Recurse -Force" >nul 2>nul
        )
        if exist "%HERE%_venv" (
            echo error: не удалось удалить старый _venv; удалите папку вручную
            pause
            exit /b 1
        )
    )
    !BASE! -m venv "%HERE%_venv"
    if errorlevel 1 (
        echo error: не удалось создать _venv
        pause
        exit /b 1
    )
    "%PY%" -m pip install -r "%REQ%"
    if errorlevel 1 (
        echo error: не удалось установить зависимости
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%HERE%core"
"%PY%" -c "import backup_lite, write_lite, fw_patch_lite" >nul 2>nul
if errorlevel 1 (
    echo error: зависимости не установлены; выполните:
    echo   "%PY%" -m pip install -r "%REQ%"
    pause
    exit /b 1
)

"%PY%" "%APP%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%

:cancel
echo Отменено.
exit /b 1
