#!/usr/bin/env python3
"""Пример TTS с фиктивными движком и плеером.

Запуск на ПК из каталога проекта:

    python3 examples/say_fake.py "Привет, мир"
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from micro_tts import TTS  # noqa: E402
from micro_tts.engines.fake import FakeEngine  # noqa: E402
from micro_tts.player.fake import FakePlayer  # noqa: E402


def main():
    text = " ".join(sys.argv[1:]) or "Привет! Это пример синтеза речи."
    player = FakePlayer()
    tts = TTS(engine=FakeEngine(), player=player)
    try:
        job = tts.say(text, wait=False)
        status = tts.status()
        print("состояние:", status["state"])
        print("байт:", job.bytes, "секунд:", round(job.duration, 2))
        player.finish()
        print("после конца:", tts.status()["state"])
    finally:
        tts.close()


if __name__ == "__main__":
    main()
