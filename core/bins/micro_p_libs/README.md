# micro_p_libs — комплекты для колонки

Снимок на 16.11.2026. Пакеты для MicroPython, которые Lite кладёт на
плату.

| Пакет | Версия | Файлов | Размер | Что внутри |
|---|---|---:|---:|---|
| `micro_hal` | 0.2.6 | 41 | 644 КБ | 24 модуля, `examples/` (12), `bins/` — 4 `.so` |
| `micro_tts` | 0.4.0 | 38 | 464 КБ | пакет, `bins/` (edge_token, `libc_edge.so`, `libc_mp3.so`), `examples/` |
| `micro_asr` | 0.2.1 | 28 | 220 КБ | пакет, `bins/libc_mp3.so`, `examples/` |
| `micro_server` | 0.1.0 | 20 | 100 КБ | пакет, `web/`, `pages/`, `api/`, `examples/` |
| `micro_ww` | 0.1.0 | 35 | 1068 КБ | пакет, `bins/libc_ww.so`, `models/` (9 моделей) |
| `micro_ui` | 0.2.30 | 12 | 92 КБ | пакет, README |
| `micro_agent` | 0.1.23 | 32 | 208 КБ | пакет, `modules/`, `commands/`, `core/`, README |
| `micro_llm` | 0.1.1 | 16 | 96 КБ | пакет, `engine/`, `engines/` (deepseek, fake), `net/` (http, sse), README |

Всего 222 файла, 2,9 МБ. Тесты, `docs/`, `csrc/`, `repo/` и `_tmp/`
в комплект не входят.

## micro_hal — HAL колонки

```text
micro_hal/                  пакет MicroPython (24 модуля)
micro_hal/examples/         примеры (12 файлов)
micro_hal/bins/             C-библиотеки: display, ring, mic, speaker
```

Подробнее — `micro_hal/README.md`.

## micro_tts — синтез речи

```text
micro_tts/                  пакет MicroPython
micro_tts/bins/             edge_token, libc_edge.so, libc_mp3.so
micro_tts/engines/          edge, edge_drm, fake, mp3, yandexv1
micro_tts/net/              websocket, http
micro_tts/player/, cache/, text/, engine/
micro_tts/examples/         say_fake.py
```

Подробнее — `micro_tts/README.md`.

## micro_asr — распознавание речи

```text
micro_asr/                  пакет MicroPython
micro_asr/bins/libc_mp3.so  MP3-декодер
micro_asr/engines/          fake, yandexv1
micro_asr/sources/          память, файл, микрофон
micro_asr/net/              HTTP/TLS
micro_asr/examples/         5 примеров
```

Подробнее — `micro_asr/README.md`.

## micro_server — веб-портал

```text
micro_server/               пакет MicroPython
micro_server/web/           HTML, css/style.css, js/app.js, js/test.js
micro_server/pages/, api/   страницы и JSON `/api/status`
micro_server/examples/      test_server.py
```

Страница состояния на порту `8080`, JSON `/api/status`; текущие
настройки — `settings.json` рядом с пакетом.

Подробнее — `micro_server/README.md`.

## micro_ww — ключевое слово

```text
micro_ww/                   пакет MicroPython
micro_ww/bins/libc_ww.so    C-рантайм: TFLite Micro + microfrontend
micro_ww/models/            манифесты и .tflite (9 моделей)
```

Локальный детектор microWakeWord: 16 кГц, моно, окна 20 мс, источник
`mics` (как в `micro_asr`). В `models/` девять моделей: `hey_jarvis`,
`jarvis`, `алиса`, `домовой`, `кузя`, `окей_валера`, `стив`, `умка`,
`эй_железяка`; как сменить или добавить — в `micro_ww/README.md`. Без
сети; микрофон — через `micro_hal`.

## micro_ui — дисплей и кольцо

```text
micro_ui/                   пакет MicroPython
micro_ui/README.md
```

Скрипт запуска `S98micro_ui.sh` лежит не в пакете, а в `core/bins/`.

Отдельный процесс: владеет дисплеем и кольцом, принимает команды по
UDP `127.0.0.1:8766` (`mode`, `face`, `overlay`, `bright`, `global`,
`auto`, `sync`, `status`). `micro_hal` нужен для железа.

Подробнее — `micro_ui/README.md`.

## micro_agent — оркестратор

```text
micro_agent/                пакет MicroPython
micro_agent/modules/        звук, речь, TTS, UI-клиент, сеть, AP, веб
micro_agent/commands/       команды: bluetooth, volume, date, face, auto
micro_agent/core/           события, цикл, машина состояний, кнопки
micro_agent/adapters/       LLM-адаптер
```

Скрипт запуска `S99micro_agent.sh` лежит не в пакете, а в `core/bins/`;
системный промпт — в `core/bins/config/system.txt`.

Сценарий «WW → ASR → LLM → TTS», диалог без повторной фразы, кнопки,
mute, автогромкость. Зависит от `micro_hal`, `micro_asr`, `micro_tts`,
`micro_ww`, `micro_llm` и `micro_ui`.

Подробнее — `micro_agent/README.md`.

## micro_llm — клиент LLM

```text
micro_llm/                  пакет MicroPython
micro_llm/engine/           интерфейс и реестр
micro_llm/engines/          deepseek, fake
micro_llm/net/              http, sse
```

Ключ `DEEPSEEK`, модель `DS_MODEL` — в `/home/.env`. Нужен агенту для
ответов; без него `main()` остаётся на `EchoAssistant`.

Подробнее — `micro_llm/README.md`.

## Куда класть на плате

`/home` на колонке — симлинк на `/data/permanent/home`.
Патч `mplibs` кладёт весь комплект в `/home/microp`:

```text
/home/microp/micro_hal/          <- пакет (py + examples)
/home/microp/micro_tts/          <- пакет + bins
/home/microp/micro_asr/          <- пакет + bins
/home/microp/micro_server/       <- пакет + web
/home/microp/micro_ww/           <- пакет + bins + models
/home/microp/micro_ui/           <- пакет
/home/microp/micro_agent/        <- пакет
/home/microp/micro_llm/          <- пакет
```

У `micro_hal` библиотеки лежат в `bins/`, у `micro_tts`/`micro_asr` —
тоже в `bins/`, у `micro_server` — `web/`, у `micro_ww` — `bins/` и
`models/`; структура сохраняется.

`/home/microp` уже входит в `MICROPYPATH`:
переменная задаётся в `/etc/init.d/S90dropbear` и
`/etc/init.d/S91adbd.sh` и в `/etc/profile.d/10-micropython.sh`.
Отдельный `/home/micro_p_libs` не нужен, обёртка `mp` не требуется.

## Автозапуск и конфиги

Скрипты запуска — отдельные ассеты в `core/bins/`:
`S98micro_ui.sh` и `S99micro_agent.sh`. В пакеты они не входят.
Их ставит патч `agentboot` в нижний `/rom/etc/init.d` (`system_b`):
`rcS` строит список `S??*` до overlay-монтирования, поэтому overlay
не подходит.

Шаблоны лежат в `core/bins/config/`: `example.env` (ключи, без значений)
и `system.txt` (промпт). Патч `agentcfg` кладёт их в `/home` как `.env`
и `system.txt`, только если файлов нет. Для LLM и облачных TTS/ASR
переименуйте `example.env` в `.env` и пропишите ключи.

## Что задаётся отдельно

- `/home/.env` — ключи `YANDEX_API`, `DEEPSEEK`, `DS_MODEL`;
- `/home/a_settings.ini` — настройки агента (создаётся при первом
  старте из умолчаний: `[ww]` 0.85/4, `[asr]` −48/0.13/1.5, `[tts]`
  yandexv1/filipp, авто-яркость включена);
- `/home/system.txt` — системный промпт LLM (шаблон — в
  `core/bins/config/system.txt`, ставит патч `agentcfg`);
- `micro_tts` кеш — `/home/microp/tts_cache`, логи — `/home/microp/logs`.

## micro_ds

Пакет `micro_ds` в комплект не входит: он живёт в проекте
`micro_p_libs/micro_ds_apk/` и разворачивается отдельно (по желанию).
Инструкция — `micro_p_libs/micro_ds_apk/micro_ds/README.md`.
Токен на плате — `/home/.env` (`DSTOKEN=...`).

## Установка вручную

С хоста, из этой папки (`IP` — адрес колонки):

```sh
tar -cf - micro_hal micro_tts micro_asr micro_server micro_ww \
    micro_ui micro_agent micro_llm SHA256SUMS \
    | ssh capsula@IP 'cd /home/microp && tar -xf - --overwrite'
```

Права и владелец:

```sh
ssh capsula@IP \
    'chown -R root:root /home/microp/micro_hal /home/microp/micro_tts \
     /home/microp/micro_asr /home/microp/micro_server /home/microp/micro_ww \
     /home/microp/micro_ui /home/microp/micro_agent /home/microp/micro_llm'
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
