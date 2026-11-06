#!/usr/bin/env python3
"""Запись с микрофона до тишины и распознавание фиктивным движком.

Запуск: `micropython /home/microp/micro_asr/examples/listen_fake.py`
"""

import sys

HERE = __file__
if "/" in HERE:
    ROOT = HERE.rsplit("/", 3)[0]
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

from micro_asr import ASR  # noqa: E402
from micro_asr.engines.fake import FakeEngine  # noqa: E402

with ASR(engine=FakeEngine()) as asr:
    try:
        text = asr.listen(until_silence=0.8, start_timeout=5.0,
                          max_seconds=10.0)
    except Exception as exc:
        print("микрофон недоступен:", exc)
        raise SystemExit(1)
    status = asr.status()

print("текст:", repr(text))
print("речь:", status["speech"],
      "длительность:", round(status["duration"], 2))
