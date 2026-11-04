#!/usr/bin/env python3
"""Динамик: тон, мелодия, пауза и остановка.

Запуск на колонке (voice-agent должен быть остановлен):

    /home/microp/mp /home/microp/micro_hal/examples/speaker_demo.py
    /home/microp/mp /home/microp/micro_hal/examples/speaker_demo.py alarm

Аргумент — sink (по умолчанию `master`). Шаги: три тона, мелодия,
пауза, длинный тон с остановкой через секунду. Громкость не
меняется — ей управляет `lib_volume`.
"""

import sys
import time

from micro_hal import hal_speaker, lib_speaker, lib_volume


def main():
    sink = sys.argv[1] if len(sys.argv) > 1 else hal_speaker.SINK
    print("sinks:", ", ".join(hal_speaker.sinks()))
    print("sink:", sink, "громкость:", lib_volume.Volume("master").get(), "%")
    print("играет:", lib_speaker.playing())

    for freq in (440, 880, 1760):
        started = time.time()
        lib_speaker.tone(freq, 0.5, sink=sink)
        print("тон %d Гц: %.3f с" % (freq, time.time() - started))

    started = time.time()
    lib_speaker.melody([(523, 200), (659, 200), (784, 200), (1046, 400)],
                       sink=sink)
    print("мелодия: %.3f с" % (time.time() - started))

    started = time.time()
    lib_speaker.silence(0.3, sink=sink)
    print("пауза: %.3f с" % (time.time() - started))

    lib_speaker.tone(660, 5.0, sink=sink, wait=False)
    time.sleep(1.0)
    print("перед stop:", lib_speaker.playing())
    print("stop:", lib_speaker.stop())
    print("после stop:", lib_speaker.playing())


if __name__ == "__main__":
    main()
