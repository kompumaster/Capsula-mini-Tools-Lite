# micro_p_libs — комплекты для колонки

Снимок на 04.11.2026. Пакеты для MicroPython, которые Lite кладёт на
плату.

## micro_hal — HAL колонки (0.1.0)

```text
micro_hal/                  пакет MicroPython (23 модуля)
micro_hal/tests/            тесты для хоста (25 файлов)
micro_hal/examples/         примеры (11 файлов)
micro_hal/bins/             C-библиотеки: display, ring, mic, speaker
```

Структура повторяет исходный `micro_p_libs/micro_hal/`: `.so` лежат
в `bins/`, а не в корне пакета.

## Куда класть на плате

`/home` на колонке — симлинк на `/data/permanent/home`.
Патч `mhal` кладёт пакет целиком:

```text
/home/microp/micro_hal/          <- пакет (py + tests + examples)
/home/microp/micro_hal/bins/     <- libc_*.so
```

`hal_*` и `lib_speaker` ищут библиотеки по путям
`/home/microp/micro_hal/bins/libc_*.so`, поэтому структура `bins/`
сохраняется. `/home/microp` уже входит в `MICROPYPATH` обёртки
`/home/microp/mp`, отдельный `/home/micro_p_libs` не нужен.

## micro_ds

Пакет `micro_ds` в комплект больше не входит: он живёт в проекте
`micro_p_libs/micro_ds_apk/` и разворачивается отдельно (по желанию).
Инструкция — `micro_p_libs/micro_ds_apk/micro_ds/README.md`.
Токен на плате — `/home/.env` (`DSTOKEN=...`).

## Установка вручную (scp на плате нет)

С хоста, из этой папки (`IP` — адрес колонки):

```sh
tar -cf - micro_hal SHA256SUMS \
    | ssh capsula@IP 'cd /home/microp && tar -xf - --overwrite'
```

Права и владелец:

```sh
ssh capsula@IP \
    'chown -R root:root /home/microp/micro_hal'
```

Проверка:

```sh
ssh capsula@IP \
    'cd /home/microp && sha256sum -c SHA256SUMS'
```

## Важное

- тесты запускаются **на хосте** (CPython: `unittest`, `mock`),
  в MicroPython их не запустить; на плате они лежат для справки;
- запись в NAND не выполняется: только файлы в `/home`;
- если на плате запущены `voice-agent` или старые скрипты, они держат
  `display`/`ring`/`keys`/`mic`/`odas` — их нужно остановить;
- PoW у `micro_ds` без модуля прошивки работает через
  `ffi` + `libkeccak23.so`; проверить: `pow.backend() == "c"`.
