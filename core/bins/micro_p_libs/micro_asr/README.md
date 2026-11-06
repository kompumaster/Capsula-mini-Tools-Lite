# micro_asr: распознавание речи для колонки

Пакет для MicroPython на VK Капсуле Мини. Записывает звук с
микрофона, берёт готовый буфер или файл, передаёт аудио движку и
возвращает текст. Библиотека не решает, когда слушать: это делает
вызывающий код.

Версия 0.2.0. Движки: `fake` (без сети) и `yandexv1` (Yandex
SpeechKit, синхронный REST).

## Что умеет

- запись с микрофона через `micro_hal`;
- остановка по тишине (VAD) или строго по времени;
- аудио из памяти и из файла: PCM, WAV, MP3;
- облачное распознавание Yandex SpeechKit (`yandexv1`);
- движки через реестр: свой движок подключается регистрацией;
- состояния задачи и отмена;
- внутренний формат — PCM `s16le`, моно, 16 кГц.

## Что нужно на колонке

- MicroPython;
- `micro_hal` для микрофона;
- свободный микрофон (если его держит `voice-agent`, запись не
  пойдёт);
- сеть и ключ Yandex SpeechKit в `/home/.env` (`ASR_YANDEX_KEY`) —
  для движка `yandexv1`;
- `MICROPYPATH` с `/home/microp` и `.frozen`:

  ```sh
  MICROPYPATH=/home/microp:/usr/lib/micropython:.frozen
  ```

## Куда ставится

```text
/home/microp/micro_asr/          пакет
/home/microp/micro_asr/bins/     C-хелперы (MP3)
/home/microp/micro_hal/          микрофон и Pulse
```

После этого работает `from micro_asr import ASR`.

## Быстрый старт

```python
from micro_asr import ASR

asr = ASR(engine="fake", language="ru-RU")
try:
    print(asr.recognize_pcm(pcm))
finally:
    asr.close()
```

`ASR` можно использовать как контекстный менеджер:

```python
with ASR(engine="fake") as asr:
    print(asr.recognize_file("/home/microp/voice.wav"))
```

## Слушание с микрофона

```python
text = asr.listen(seconds=4.0)        # ровно 4 секунды
text = asr.listen(max_seconds=25.0)   # до тишины, но не дольше 25 с
text = asr.listen(silence=0.8,        # 0,8 с тишины — конец фразы
                  start_timeout=5.0,  # ждать речь не дольше 5 с
                  max_seconds=25.0,
                  min_speech=0.3)     # короче 0,3 с — не речь

pcm = asr.capture(until_silence=0.8, max_seconds=25.0)
```

| Параметр | Смысл |
|---|---|
| `seconds` | ровно столько секунд, VAD выключен |
| `silence` | сколько тишины считать концом фразы |
| `start_timeout` | сколько ждать начало речи |
| `max_seconds` | жёсткий предел записи |
| `min_speech` | минимальная длительность речи |
| `threshold_db` | порог речи, по умолчанию −45 dBFS |

Если речи не было, возвращается пустая строка — это не ошибка.

## Файлы и память

```python
text = asr.recognize_pcm(pcm)                       # bytes, s16le моно
text = asr.recognize_file("/home/microp/voice.wav")
text = asr.recognize_file("/home/microp/voice.pcm")
text = asr.recognize_file("/home/microp/voice.mp3")
```

Файлы других частот приводятся к 16 кГц; стерео сводится в моно.

## Основные вызовы

| Вызов | Что делает |
|---|---|
| `recognize_pcm(pcm)` | распознать буфер |
| `recognize_file(path)` | распознать файл |
| `listen(...)` | записать с микрофона и распознать |
| `capture(...)` | только запись, без распознавания |
| `submit(source)` / `pump()` | кооперативный режим |
| `status()` | снимок состояния |
| `stop()` | отменить запись и распознавание |

## Движки

- `fake` — детерминированный текст, работает без сети;
- `yandexv1` — Yandex SpeechKit, синхронный REST: ключ в
  `/home/.env` (`ASR_YANDEX_KEY`), лимиты 30 с и 1 МБ, без
  частичных результатов.

```python
asr = ASR(engine="yandexv1")
text = asr.recognize_file("/home/microp/voice.mp3")
```

Свой движок регистрируется так:

```python
from micro_asr import register_engine

register_engine("myservice", MyEngine)
asr = ASR(engine="myservice")
```

## Настройки `ASR`

| Параметр | Назначение |
|---|---|
| `engine` | имя движка или объект |
| `language` | язык распознавания, по умолчанию `ru-RU` |
| `sample_rate` | частота для движка, по умолчанию 16 000 |
| `engine_options` | параметры конкретного движка |

## Примеры

В пакете `examples/`:

- `recognize_fake.py` — буфер в памяти, движок `fake`;
- `recognize_file.py FILE` — файл PCM/WAV/MP3, движок `fake`;
- `listen_fake.py` — микрофон и VAD, движок `fake`;
- `recognize_cloud.py FILE` — файл через `yandexv1`;
- `listen_cloud.py` — микрофон через `yandexv1`.

На колонке:

```sh
/usr/bin/micropython /home/microp/micro_asr/examples/recognize_fake.py
/usr/bin/micropython /home/microp/micro_asr/examples/recognize_file.py /home/microp/voice.mp3
/usr/bin/micropython /home/microp/micro_asr/examples/listen_fake.py

/usr/bin/micropython /home/microp/micro_asr/examples/recognize_cloud.py /home/microp/voice.mp3
/usr/bin/micropython /home/microp/micro_asr/examples/listen_cloud.py
```

`fake` возвращает текст `распознано`, но проходит весь путь
«аудио → движок → текст». Примеры с `cloud` обращаются к Yandex и
требуют ключ.

## Ограничения

- VAD: фиксированный порог −45 dBFS; в шумном помещении или при
  тихом голосе подберите `threshold_db`;
- микрофон один: во время записи его не должен держать другой процесс;
- аудио нигде не сохраняется; временные файлы удаляются в `stop()` и
  `close()`;
- по умолчанию запись ограничена 25 с (движок принимает до 30 с и
  1 МБ; 25 с при 16 кГц — 800 КБ);
- звук уходит в облако Yandex; библиотека его не хранит;
- частичных результатов (текст по мере речи) пока нет.

## Состав пакета

```text
micro_asr/
  __init__.py      публичные имена и версия
  asr.py           объект ASR и сценарии
  job.py           задача и состояния
  audio.py         PCM/WAV, проверки, ресемплинг
  vad.py           детектор речи и тишины
  config.py        настройки
  errors.py        AsrError
  mp3.py           MP3-декодер (ffi/ctypes)
  sources/         память, файл, микрофон
  engines/         интерфейс движка, реестр, fake, yandexv1
  net/             HTTP/TLS для облачного движка
  bins/            C-хелперы, включая libc_mp3.so
  examples/        примеры запуска
```
