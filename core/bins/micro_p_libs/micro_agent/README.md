# micro_agent: оркестратор колонки

Пакет для MicroPython на VK Капсуле Мини. Один процесс связывает
оборудование (`micro_hal`), ключевое слово (`micro_ww`), распознавание
(`micro_asr`), ассистента (`micro_llm`) и синтез (`micro_tts`) в
сценарий «часы → ключевая фраза → вопрос → ответ».

Версия 0.1.23. Тесты - 255 на CPython, без платы.

## Что умеет

- базовый режим: часы и нейтральное кольцо, ожидание ключевой фразы;
- после фразы: тон готовности, запись вопроса, ASR, затем **команда**
  или ответ LLM, потом TTS;
- диалог: после ответа слушает следующий вопрос без фразы-обращения,
  выход - по тишине;
- barge-in: фраза во время ответа останавливает TTS и начинает новый
  сценарий;
- режим Bluetooth: A2DP-звук приостанавливается на время ответа и
  возвращается после;
- кнопки: громкость, `circle` (слушать), `play` (пауза TTS или
  AVRCP), `mic` (глобальный mute);
- громкость запоминается и восстанавливается после перезагрузки;
- сетевой watchdog и точка доступа при потере связи;
- настройки в `/home/a_settings.ini`: читаются при старте, пишутся
  атомарно;
- детский режим промпта по `[agent] age_limit`.

## Что нужно на колонке

- MicroPython с `ffi`/`ssl` и `.frozen` в `MICROPYPATH`:

  ```sh
  MICROPYPATH=/home/microp:/usr/lib/micropython:.frozen
  ```

- запуск с кучей 32 МБ: `micropython -X heapsize=32M` - без этого ASR
  падает по памяти;
- пакеты `micro_hal`, `micro_ww`, `micro_asr`, `micro_tts`,
  `micro_llm` и процесс `micro_ui` (дисплей и кольцо);
- ключи в `/home/.env`: `YANDEX_API` (ASR и TTS), `DEEPSEEK` и
  `DS_MODEL` (LLM); без ключей агент работает, но без LLM (эхо-ответ)
  и без облачных TTS/ASR;
- системный промпт `/home/system.txt` - туда же пишется имя
  помощника текстом;
- свободный микрофон: `voice-agent` и ASR-клиенты его не должны
  держать.

## Куда ставится

```text
/home/microp/micro_agent/          пакет
/home/a_settings.ini               настройки (создаёт сам при старте)
/home/system.txt                   системный промпт
/home/.env                         ключи платформы
/home/microp/logs/                 логи агента
/home/microp/tts_cache/            кеш подтверждений TTS
```

Автозапуск - `S99micro_agent.sh` (в исходниках лежит в `init.d/`; в
Lite-комплекте это отдельный ассет `core/bins/`, его ставит патч
`agentboot` в `/rom/etc/init.d`). Скрипт запускает агент через
`micropython -X heapsize=32M` и отдельный процесс `log.py` для
ротации логов.

Вручную:

```sh
/home/microp/micro_agent/init.d/S99micro_agent.sh start
/home/microp/micro_agent/init.d/S99micro_agent.sh status
```

## Сценарий

```text
BASE (часы)
  └─ ключевая фраза → WAKE (тон) → ASR (запись вопроса)
        ├─ команда → выполнить, подтверждение голосом → BASE/BT_MODE
        └─ вопрос → THINK (LLM) → SPEAK (TTS)
                                   ├─ диалог: снова ASR без фразы
                                   └─ тишина → BASE/BT_MODE
```

Состояния: `base`, `wake`, `asr`, `think`, `speak`, `bt_mode`,
`netlost`, `apmode`, `error`. Ошибка держит `9 9` на дисплее и
возвращает в базовый режим через `recover_ms` (5 с).

Диалог включается `[agent] dialog=true` (по умолчанию). После ответа
LLM агент сразу слушает следующий вопрос; выход - когда ASR не увидел
речи (`start_timeout`, 5 с) или по `CANCEL`/ошибке/сети/BT.

## Команды

Распознанный текст нормализуется (регистр, пунктуация, `ё → е`) и
проверяется по реестру `commands/`:

| Команда | Примеры | Действие |
|---|---|---|
| `bluetooth.on` | «включи блютус» | BT вкл, режим `bt_mode` |
| `bluetooth.off` | «выключи блютус» | BT выкл, режим `base` |
| `volume.up` / `volume.down` | «громче», «тише» | громкость и оверлей |
| `date` | «покажи дату» | оверлей даты на 20 с |
| `face` | «подмигни», «улыбнись» | смайл на 5 с |
| `auto.on` / `auto.off` | «включи автояркость» | авто-яркость в `micro_ui` |

Подтверждения - без рода: «блютус включен», «громкость повышена».
Командные подтверждения кешируются в `micro_tts` после первого
удачного синтеза.

## Кнопки

Раскладка описана в `docs/PLAN_BUTTONS.md`; настройки - `[keys]`.

| Кнопка (код) | Действие |
|---|---|
| `vol+` / `vol-` (115/114) | громкость ±`volume_step`, оверлей; автоповтор |
| `circle` (164) | сброс текущего и новое прослушивание |
| `play` (704) | пауза/продолжение TTS, иначе AVRCP |
| `mic` (248) | глобальный mute: режим `muted`, четыре красные точки |
| `circle` + `vol±`, удержание 2 с | следующий/предыдущий трек (AVRCP) |

Кнопки опрашиваются в начале каждого шага цикла, поэтому работают в
любом режиме. Ограничение: во время блокирующего захвата ASR цикл
стоит, и кнопки обрабатываются только после него.

## Настройки

`/home/a_settings.ini`; если файла нет, агент создаёт его из
умолчаний при первом старте. Основные секции:

| Секция | Ключи (по умолчанию) |
|---|---|
| `agent` | `tick_ms=10`, `max_utterance=25.0`, `mic_source=mics`, `dialog=true`, `age_limit=120` |
| `ww` | `model=.../hey_jarvis.json`, `threshold=0.85`, `window=4`, `cooldown_ms=1000` |
| `asr` | `engine=yandexv1`, `threshold_db=-48`, `min_speech=0.13`, `silence=1.5` |
| `llm` | `engine=deepseek`, `system_file=/home/system.txt`, `session_ttl_seconds=600`, `max_turns=6`, `max_chars=4000`, `max_tokens=650`, `temperature=0.7`, `thinking=false` |
| `tts` | `engine=yandexv1`, `voice=filipp`, `emotion=neutral`, `sample_rate=16000`, `cache=false` |
| `ui` | `host=127.0.0.1`, `port=8766`, яркости 80/24, `global_brightness=100`, `auto_brightness=true` |
| `keys` | `enabled=true`, `debounce_ms=40`, `hold_ms=600`, `click_ms=350`, `combo_hold_ms=2000`, `volume_step=5` |
| `audio` | `bt_alias=Capsula Mini`, `save_ms=5000`, `last_volume` (пишет агент) |
| `network` | `watchdog_ms=30000`, `ap_after_ms=180000` |
| `server` | `port=8080` (задел: `micro_server` в `main()` не подключён) |

Эффективная яркость в UI: `base * global // 100`.

### Громкость

Pulse громкость не восстанавливает, поэтому агент сам помнит её: после
изменения и `[audio] save_ms` (5 с) простоя пишет `last_volume` в
`a_settings.ini`; при старте ставит обратно. `0` сохраняется как есть.

### Детский режим

```ini
[agent]
age_limit=10
```

Если значение меньше 18, перед текстом `/home/system.txt`
добавляется блок «Ты разговариваешь с детьми 10 лет…». При 18-120
блок не добавляется. Возраст не склоняется: всегда «N лет».

## Логи

`/home/microp/logs/ГГГГММДД-ЧЧММСС-agent.log`, ротатор - `log.py`
(128 КБ на файл, 2 МБ на каталог). Полезные строки: `WAKE`, `ASR:`,
`SPEAK`, `COMMAND`, `DIALOG ask/end`, `VOLUME restore/save`,
`RECOVER`.

До синхронизации часов после загрузки имя файла может начинаться с
`19700101-…` - это нормально.

## Ограничения

- один процесс, без потоков: длинные операции (`ASR`, синтез, LLM)
  блокируют цикл; во время записи вопроса кнопки не работают;
- микрофон один: `micro_ww` и ASR работают по очереди;
- AVRCP (`play` для телефона, треки) вживую ещё не проверен;
- `micro_server` и `/api/status` есть, но в `main()` не подключены;
- Edge TTS отложен, используется `yandexv1`;
- barge-in, точка доступа и длительный прогон ждут приёмки на плате.

## Тесты

```sh
_venv/bin/python -m unittest discover \
    -s micro_p_libs/micro_agent/tests -p 'test_*.py'
```

Проверяются машина состояний, цикл и таймеры, команды, кнопки, настройки,
модули с подменённым `micro_hal`, сквозной сценарий и диалог.

Текущий результат: **255 OK**.

## Состав пакета

```text
micro_agent/
  __init__.py      публичные имена и версия
  agent.py         Agent, build_* и main()
  config.py        значения по умолчанию и проверки
  settings.py      чтение/запись /home/a_settings.ini
  intent.py        нормализация текста
  log.py           ротатор логов
  system.txt       системный промпт по умолчанию
  core/            события, цикл, машина состояний, роутер кнопок
  modules/         звук, речь, TTS, UI-клиент, сеть, AP, веб, кнопки
  commands/        bluetooth, volume, date, face, auto
  adapters/        LLM-адаптер (EchoAssistant, LlmAssistant)
  init.d/          S99micro_agent.sh
  tests/           тесты
  docs/            PROJECT, PROGRESS, TODO, планы
```

Архитектура и решения - в `docs/PROJECT.md`, кнопки - в
`docs/PLAN_BUTTONS.md`.
