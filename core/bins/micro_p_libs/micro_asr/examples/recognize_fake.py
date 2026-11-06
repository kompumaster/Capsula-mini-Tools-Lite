#!/usr/bin/env python3
"""Распознавание буфера PCM фиктивным движком.

Запуск: `micropython /home/microp/micro_asr/examples/recognize_fake.py`
"""

import sys

HERE = __file__
if "/" in HERE:
    ROOT = HERE.rsplit("/", 3)[0]
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

from micro_asr import ASR  # noqa: E402
from micro_asr.engines.fake import FakeEngine  # noqa: E402

PCM = b"\x00\x00" * 16000   # 1 секунда, 16 кГц, моно

with ASR(engine=FakeEngine()) as asr:
    text = asr.recognize_pcm(PCM)
    status = asr.status()

print("текст:", text)
print("состояние:", status["state"],
      "длительность:", round(status["duration"], 2))
