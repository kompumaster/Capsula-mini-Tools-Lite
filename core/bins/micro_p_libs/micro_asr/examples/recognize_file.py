#!/usr/bin/env python3
"""Распознавание файла PCM/WAV/MP3 фиктивным движком.

Запуск:
`micropython /home/microp/micro_asr/examples/recognize_file.py FILE`
"""

import sys

HERE = __file__
if "/" in HERE:
    ROOT = HERE.rsplit("/", 3)[0]
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

from micro_asr import ASR  # noqa: E402
from micro_asr.engines.fake import FakeEngine  # noqa: E402

if len(sys.argv) < 2:
    print("usage: recognize_file.py FILE")
    raise SystemExit(2)

path = sys.argv[1]

with ASR(engine=FakeEngine()) as asr:
    text = asr.recognize_file(path)
    status = asr.status()

print("файл:", path)
print("текст:", text)
print("состояние:", status["state"],
      "длительность:", round(status["duration"], 2))
