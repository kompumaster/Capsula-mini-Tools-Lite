# micro_tts: синтез речи для колонки

Пакет для MicroPython на VK Капсуле Мини. Принимает текст, синтезирует
его и отдаёт звук на динамик. Библиотека не решает, что и когда
говорить: это задача вызывающего кода.

Версия 0.2.0.

## Что умеет

- короткие фразы и длинный текст;
- Edge TTS: русские голоса `ru-RU-DmitryNeural` и
  `ru-RU-SvetlanaNeural`;
- кеш MP3: повторные фразы звучат без сети;
- потоковый вывод: звук играет по мере синтеза;
- пауза, продолжение, остановка;
- отложенный вывод: подготовить сейчас, сыграть позже;
- смена движка, плеера и нормализатора без правки вызывающего кода.

## Что нужно на колонке

- MicroPython со `ssl`, `ffi` и `.frozen` в `MICROPYPATH`:

  ```sh
  MICROPYPATH=/home/microp:/usr/lib/micropython:.frozen
  ```

- `micro_hal` для вывода звука;
- сеть и верное время (NTP) для новых фраз;
- каталог кеша `/home/microp/tts_cache` — создаётся сам.

## Куда ставится

```text
/home/microp/micro_tts/          пакет
/home/microp/micro_tts/bins/     libc_mp3.so, libc_edge.so, edge_token
/home/microp/micro_hal/          HAL: динамик, громкость, Pulse
/home/microp/tts_cache/          кеш MP3
```

После этого работает `from micro_tts import TTS`.

## Быстрый старт

```python
from micro_tts import TTS

tts = TTS(engine="edge", voice="ru-RU-DmitryNeural")
try:
    tts.say("Привет! Сейчас двенадцать часов тридцать четыре минуты.")
finally:
    tts.close()
```

`TTS` можно использовать как контекстный менеджер:

```python
with TTS(engine="edge") as tts:
    tts.say("Колонка готова")
```

## Основные вызовы

| Вызов | Что делает |
|---|---|
| `say(text, cache=False, wait=True)` | синтез и воспроизведение |
| `prepare(text, cache=False)` | только синтез, без звука |
| `play(job)` | сыграть подготовленное |
| `pause()` / `resume()` | пауза и продолжение |
| `stop()` | остановить звук и синтез |
| `status()` | снимок состояния |
| `playing()` | идёт ли воспроизведение |
| `cache_info()` / `clear_cache()` | кеш |

Кеш и поток:

```python
tts.say("Bluetooth включён", cache=True)   # записать и сыграть
tts.prepare("Нет сети", cache=True)        # только записать в кеш
tts.say(long_text, stream=True)            # играть по мере синтеза

tts.pause()
tts.resume()
tts.stop()
```

Отложенный вывод:

```python
job = tts.prepare("Батарея заряжена")
# ... позже
tts.play(job)
```

## Кеш

- включается запросом: `cache=True`, по умолчанию выключен;
- хранит MP3, полученный от Edge, без перекодирования;
- лимиты: 16 МБ, 256 записей, текст до 300 символов;
- старые записи вытесняются по LRU;
- `prepare(..., cache=True)` записывает фразу без звука — потом она
  звучит офлайн;
- ошибка кеша не мешает синтезу.

## Движки

- `edge` — сетевой Edge TTS, MP3 24 кГц, русские голоса;
- `fake` — тишина для проверок, работает без сети и по умолчанию.

Свой движок подключается регистрацией:

```python
from micro_tts import register_engine

register_engine("mytts", MyEngine)
tts = TTS(engine="mytts")
```

## Настройки `TTS`

| Параметр | Назначение |
|---|---|
| `engine` | имя движка или объект |
| `voice` | голос движка |
| `rate`, `pitch` | темп и высота, 0,5…2,0 |
| `volume` | 0…100; сохраняется, применяет вызывающий код |
| `sink` | sink Pulse, по умолчанию `master` |
| `chunk_chars` | предел символов в чанке, по умолчанию 200 |
| `player` | свой плеер или `None` (через `micro_hal`) |
| `normalizer` | своя подготовка текста или `None` |
| `cache`, `cache_dir` | кеш по умолчанию и его каталог |
| `options` | параметры конкретного движка |

## Ограничения

- новые фразы требуют сети и верного времени; при ошибке 403
  проверьте NTP;
- Edge иногда закрывает соединение: библиотека делает 2 повтора по
  0,5 с;
- пауза действует на весь sink, а не на одну фразу;
- громкость библиотека не меняет и `voice-agent` не останавливает —
  это делает вызывающий код;
- позиция внутри фразы недоступна: статус показывает состояние, а не
  время.

## Состав пакета

```text
micro_tts/
  __init__.py      публичные имена и версия
  tts.py           объект TTS и сценарии
  job.py           задача и состояния
  audio.py         PCM и WAV
  config.py        проверка настроек
  errors.py        TtsError
  text/            нормализация и разбиение текста
  engine/          интерфейс движка и реестр
  engines/         edge, fake, MP3, DRM
  net/             WebSocket/TLS
  player/          интерфейс плеера и адаптер micro_hal
  cache/           MP3/WAV-кеш, LRU
  bins/            C-библиотеки и edge_token
  examples/        примеры запуска
```

`examples/say_fake.py` запускается без сети и платы.
