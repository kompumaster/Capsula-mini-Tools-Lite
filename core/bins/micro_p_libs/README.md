# micro_p_libs — комплекты для колонки

Снимок на 06.11.2026. Пакеты для MicroPython, которые Lite кладёт на
плату.

## micro_hal — HAL колонки (0.2.0)

```text
micro_hal/                  пакет MicroPython (24 модуля)
micro_hal/examples/         примеры (12 файлов)
micro_hal/bins/             C-библиотеки: display, ring, mic, speaker
```

## micro_tts — синтез речи (0.2.0)

```text
micro_tts/                  пакет MicroPython + bins
micro_tts/bins/             edge_token, libc_edge.so, libc_mp3.so
```

## micro_asr — распознавание речи (0.2.0)

```text
micro_asr/                  пакет MicroPython + bins
micro_asr/bins/             libc_mp3.so
```

## Куда класть на плате

`/home` на колонке — симлинк на `/data/permanent/home`.
Патч `mplibs` кладёт весь комплект в `/home/microp`:

```text
/home/microp/micro_hal/          <- пакет (py + examples)
/home/microp/micro_tts/          <- пакет + bins
/home/microp/micro_asr/          <- пакет + bins
```

У `micro_hal` библиотеки лежат в `bins/`, у `micro_tts`/`micro_asr` —
тоже в `bins/`; структура сохраняется. `/home/microp` уже входит в `MICROPYPATH`:
переменная задаётся в `/etc/init.d/S90dropbear` и
`/etc/init.d/S91adbd.sh` и в `/etc/profile.d/10-micropython.sh`.
Отдельный `/home/micro_p_libs` не нужен, обёртка `mp` не требуется.

## micro_ds

Пакет `micro_ds` в комплект больше не входит: он живёт в проекте
`micro_p_libs/micro_ds_apk/` и разворачивается отдельно (по желанию).
Инструкция — `micro_p_libs/micro_ds_apk/micro_ds/README.md`.
Токен на плате — `/home/.env` (`DSTOKEN=...`).

## Установка вручную (scp на плате нет)

С хоста, из этой папки (`IP` — адрес колонки):

```sh
tar -cf - micro_hal micro_tts micro_asr SHA256SUMS \
    | ssh capsula@IP 'cd /home/microp && tar -xf - --overwrite'
```

Права и владелец:

```sh
ssh capsula@IP \
    'chown -R root:root /home/microp/micro_hal /home/microp/micro_tts /home/microp/micro_asr'
```

Проверка:

```sh
ssh capsula@IP \
    'cd /home/microp && sha256sum -c SHA256SUMS'
```

## Важное

- запись в NAND не выполняется: только файлы в `/home`;
- если на плате запущены `voice-agent` или старые скрипты, они держат
  `display`/`ring`/`keys`/`mic`/`odas` — их нужно остановить;
- PoW у `micro_ds` без модуля прошивки работает через
  `ffi` + `libkeccak23.so`; проверить: `pow.backend() == "c"`.
