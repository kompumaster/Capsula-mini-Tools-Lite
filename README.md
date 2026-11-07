# Capsula-mini-Tools-Lite

Лёгкая редакция инструментов для VK Капсулы Мини (Amlogic A113X,
NAND 256 МиБ) на родной прошивке: чистый Python, `fw_io` и `fwpatch`.
Работает на Linux и Windows 10; на Windows 11 чтение
нестабильно, но возможно, на свой страх и риск.

## Что умеет

- Снять бэкап: `system_a`, `system_b`, `data`, `boot_a`, `boot_b`, `misc`;
  исключая `tpl` и `bootloader` - через `store` недоступны.
- Собрать образы с патчами: `/home`, LAPI, ADB, SSH, VK-Voice,
  VK-Call, Selfcheck, MicroPython, MP Libs, Hostapd, Dnsmasq,
  заглушки телеметрии и автообновлений.
- Записать образ в раздел: патченый или исходный, с обратной сверкой.
- Преобразовать UBI-раздел в tar для просмотра/правки:
  «Сервис → Раздел → tar».
- Собрать раздел из tar обратно: «Сервис → tar → раздел».
- Перезагрузить колонку: «Сервис → Перезагрузить колонку»
  (`core/common/reboot.py`) — сначала SSH, при неудаче ADB.

## Драйвер

- Windows: WinUSB для загрузчика колонки — [driver/Install](driver/Install/README.md);
  удаление старого или лишнего драйвера — [driver/Remove](driver/Remove/README.md).

## Запуск

Linux:

```sh
./Capsula-Tools-Lite.sh
```

Windows:

```bat
Capsula-Tools-Lite.bat
```

## Ограничения

`tpl` и `bootloader` через `store` не читаются и не пишутся.

## Перезагрузка колонки

```sh
_venv/bin/python core/common/reboot.py
_venv/bin/python core/common/reboot.py --ip АДРЕС
```

IP по умолчанию ищется через `core/common/find_ip.py`. Сначала
пробуется SSH (`capsula`, пароль `mini` или `CAPSULA_SSH_PASSWORD`):
`sshpass`, иначе `SSH_ASKPASS`, иначе ключ. Затем ADB: клиент `adb`
или напрямую протокол ADB на `IP:5555`.

## Патчи

| Патч | Что делает | Реализация |
|---|---|---|
| LAPI | локальный API, `:80` | `permanent/lapi` = `on` |
| ADB | ADB, `:5555` | пересобранный `adbd-tcp`, без проверки ключа |
| SSH | SSH, `:22` | `dropbearmulti` (dropbear + dropbearkey + scp + dbclient), `capsula` / `mini` |
| VK-Voice (`vkvoice`) | отключает автозапуск, файл остаётся | `S97voice-agent.sh` → `x_S97voice-agent.sh.bak` |
| VK-Call (`vkcall`) | отключает автозапуск, файл остаётся | `S97okcall.sh` → `x_S97okcall.sh.bak` |
| Selfcheck (`slfchk`) | отключает автозапуск S98, файл остаётся | `S98selfcheck.sh` → `x_S98selfcheck.sh.bak` |
| Удалить VK-Voice (`vkkill`) | заменяет бинарь заглушкой | `voice-agent` → `noop` |
| Micropython (`mpython`) | бинарник и профиль окружения в overlay `data` | `data/overlay/upper/usr/bin/micropython`, `data/overlay/upper/etc/profile.d/10-micropython.sh` |
| Hostapd (`hostapd`) | кладёт `hostapd` в overlay `data` | `data/overlay/upper/usr/bin/hostapd` |
| Dnsmasq (`dnsmasq`) | кладёт `dnsmasq` с DHCP в overlay `data` | `data/overlay/upper/usr/bin/dnsmasq` |
| Подключить `/home` (`home`) | подключает `/data/permanent/home` как `/home` | `S05home.sh` → `/etc/init.d/S05home.sh` |
| MP Libs (`mplibs`) | Библиотеки Micropython для работы с колонкой | `permanent/home/microp/` (`micro_hal`, `micro_tts`, `micro_asr`, `micro_server`) |
| Телеметрияd | отключает телеметрию | `telemetryd` → `noop` |
| Обновление FW | отключает обновление прошивки | `fwupdater` → `noop1` |
| Обновление SW | отключает обновление ПО | `swupdate` → `noop` |

В меню «Патчи» номер или команда вводятся строкой и подтверждаются
Enter; пункт `10` доступен. В строке каждого патча выводится краткое
описание (`SUMMARY`).

Патчи применяются к образам из `backup/parts`, результат — в
`patched/parts`; оригиналы не меняются.

## MicroPython: библиотеки

`micro_hal` даёт доступ к оборудованию из MicroPython: `hal_*` — только
железо, `lib_*` — логика. Готовы:

- дисплей — sysfs + C-helper `libc_display.so` (анимация);
- кольцо — 15 эффектов, C-helper `libc_ring.so`;
- кнопки — клики, удержание, сочетания;
- датчик света — люксы;
- NTP — синхронизация времени;
- громкость — управление Pulse;
- микрофоны — C-helper `libc_mic.so` (захват и поток);
- позиционирование источника звука — ODAS;
- вывод звука — тон, мелодия, WAV, C-helper `libc_speaker.so`;
- Bluetooth — A2DP;
- Wi-Fi — скан и подключение с откатом.

API и примеры — в пакете [micro_hal](core/bins/micro_p_libs/micro_hal/)
(`hal_*`/`lib_*`, `examples/`), описание —
[README](core/bins/micro_p_libs/micro_hal/README.md).

`micropython` пересобран: куча GC 8 МБ по умолчанию (было 2 МБ);
`-X heapsize=N` переопределяет.

[micro_tts](core/bins/micro_p_libs/micro_tts/) — синтез речи (Edge TTS):
пакет, `bins/edge_token`, `bins/libc_edge.so` и `bins/libc_mp3.so`.
Описание — [README](core/bins/micro_p_libs/micro_tts/README.md).

[micro_asr](core/bins/micro_p_libs/micro_asr/) — распознавание речи:
Yandex SpeechKit v1, VAD (остановка по тишине), MP3-кодирование;
источники — файл, микрофон, память (PCM/WAV/MP3). Ключ Yandex — в
`/home/.env` (`ASR_YANDEX_KEY`). Описание —
[README](core/bins/micro_p_libs/micro_asr/README.md).

[micro_server](core/bins/micro_p_libs/micro_server/) — веб-портал:
страница состояния на `:8080`, JSON `/api/status`. Описание —
[README](core/bins/micro_p_libs/micro_server/README.md).

Патч `mplibs` кладёт все четыре пакета в `/home/microp`; профиль
`10-micropython.sh` (патч `mpython`) добавляет `.frozen` в
`MICROPYPATH`, без чего нет `ssl` и Edge TTS не работает.

## Свои патчи

`core/fwpatch/patches/README.md` — структура модуля, шаблон и
регистрация. Новые модули подхватываются автоматически: появляются в
меню и статусах.

## Что сделано

- UBI разбирается в tar: сохраняются имена, права, uid/gid и симлинки,
  поэтому сборка работает и на Windows —
  [kompumaster/UbiTar](https://github.com/kompumaster/UbiTar).
- `adbd` пересобран статически (AArch64) — компактнее и без
  зависимости от стоковой glibc.
- `dropbearmulti` — `dropbear` + `dropbearkey` + `scp` + `dbclient`
  в одном файле, вход `capsula` / `mini` без настройки учётной записи.
- `system` и `data` пересобираются с zlib вместо стокового lzo —
  образы меньше.

## Требования

- Python 3.9 или новее.
- Linux: `libusb-1.0`; остальное ставится из `requirements.txt`.

## Лицензия

GPL-2.0, см. `LICENSE`.

