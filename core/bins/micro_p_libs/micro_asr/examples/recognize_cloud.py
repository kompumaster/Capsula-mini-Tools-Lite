#!/usr/bin/env python3
"""Распознавание файла через Yandex SpeechKit (движок yandexv1).

Ключ: `/home/.env`, переменная `ASR_YANDEX_KEY`.
Запуск:
`micropython /home/microp/micro_asr/examples/recognize_cloud.py FILE`
"""

import sys
import time

HERE = __file__
if "/" in HERE:
    ROOT = HERE.rsplit("/", 3)[0]
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

from micro_asr import ASR  # noqa: E402

if len(sys.argv) < 2:
    print("usage: recognize_cloud.py FILE")
    raise SystemExit(2)

path = sys.argv[1]

asr = ASR(engine="yandexv1")
try:
    start = time.time()
    text = asr.recognize_file(path)
    status = asr.status()
finally:
    asr.close()

print("файл:", path)
print("текст:", text)
print("состояние:", status["state"],
      "длительность:", round(status["duration"], 2),
      "время:", round(time.time() - start, 2), "с")
