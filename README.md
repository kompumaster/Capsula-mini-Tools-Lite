# Capsula-mini-Tools-Lite

Лёгкая редакция инструментов для VK Капсулы Мини (Amlogic A113X,
NAND 256 МиБ) на родной прошивке: чистый Python, `fw_io` и `fwpatch`.
Работает на Linux и Windows 10; на Windows 11 чтение
нестабильно, но возможно, на свой страх и риск.

## Что умеет

- Снять бэкап: `system_a`, `system_b`, `data`, `boot_a`, `boot_b`, `misc`;
  исключая `tpl` и `bootloader` - через `store` недоступны.
- Собрать образы с патчами: LAPI, ADB, SSH, VK-Voice, Selfcheck,
  Micropython, заглушки телеметрии и автообновлений.
- Записать образ в раздел: патченый или исходный, с обратной сверкой.
- Преобразовать UBI-раздел в tar для просмотра/правки:
  «Сервис → Раздел → tar».
- Собрать раздел из tar обратно: «Сервис → tar → раздел».

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

## Патчи

| Патч | Что делает | Реализация |
|---|---|---|
| LAPI | локальный API, `:80` | `permanent/lapi` = `on` |
| ADB | ADB, `:5555` | пересобранный `adbd-tcp`, без проверки ключа |
| SSH | SSH, `:22` | патченный `dropbear`, `capsula` / `mini` |
| VK-Voice (`vkvoice`) | отключает автозапуск, файл остаётся | `S97voice-agent.sh` → `x_S97voice-agent.sh.bak` |
| Selfcheck (`slfchk`) | отключает автозапуск S98, файл остаётся | `S98selfcheck.sh` → `x_S98selfcheck.sh.bak` |
| Удалить VK-Voice (`vkkill`) | заменяет бинарь заглушкой | `voice-agent` → `noop` |
| Micropython (`mpython`) | кладёт бинарник в overlay `data` | `data/overlay/upper/usr/bin/micropython` |
| Телеметрияd | отключает телеметрию | `telemetryd` → `noop` |
| Обновление FW | отключает обновление прошивки | `fwupdater` → `noop1` |
| Обновление SW | отключает обновление ПО | `swupdate` → `noop` |

В меню «Патчи» номер или команда вводятся строкой и подтверждаются
Enter; пункт `10` доступен.

Патчи применяются к образам из `backup/parts`, результат — в
`patched/parts`; оригиналы не меняются.

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
- `dropbear` пересобран со статичными именем и паролем (`capsula` /
  `mini`) — вход без настройки учётной записи.
- `system` и `data` пересобираются с zlib вместо стокового lzo —
  образы меньше.

## Требования

- Python 3.9 или новее.
- Linux: `libusb-1.0`; остальное ставится из `requirements.txt`.

## Зависимости

`core/bins`, `core/stubs` и `core/ubitar` входят в репозиторий;
внешние симлинки не нужны.

## Лицензия

GPL-2.0, см. `LICENSE`.

