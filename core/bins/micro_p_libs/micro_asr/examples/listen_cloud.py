#!/usr/bin/env python3
"""Запись с микрофона и распознавание через Yandex SpeechKit (yandexv1).

Ключ: `/home/.env`, переменная `ASR_YANDEX_KEY`.
Говорите после запуска; конец фразы — пауза около секунды.

Запуск: `micropython /home/microp/micro_asr/examples/listen_cloud.py`
"""

import sys
import time

HERE = __file__
if "/" in HERE:
    ROOT = HERE.rsplit("/", 3)[0]
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

from micro_asr import ASR  # noqa: E402

asr = ASR(engine="yandexv1")
try:
    print("говорите...")
    start = time.time()
    try:
        text = asr.listen(until_silence=0.8, start_timeout=8.0,
                          max_seconds=15.0)
    except Exception as exc:
        print("ошибка:", exc)
        raise SystemExit(1)
    status = asr.status()
finally:
    asr.close()

print("текст:", repr(text))
print("речь:", status["speech"],
      "длительность:", round(status["duration"], 2),
      "время:", round(time.time() - start, 2), "с")
