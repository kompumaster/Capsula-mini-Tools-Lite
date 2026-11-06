#!/usr/bin/env python3
"""Динамик: PCM из памяти, файлы, поток, пауза и остановка.

Запуск на колонке (voice-agent должен быть остановлен):

    /home/microp/mp \
        /home/microp/micro_hal/examples/speaker_stream_demo.py
    /home/microp/mp \
        /home/microp/micro_hal/examples/speaker_stream_demo.py alarm

Аргумент — sink (по умолчанию `master`). Все вызовы — через
`lib_speaker`; громкость не меняется.
"""

import os
import sys
import time

from micro_hal import hal_speaker, lib_speaker

WAV = "/tmp/micro_hal_stream_demo.wav"
RAW = "/tmp/micro_hal_stream_demo.raw"


def _remove(*paths):
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    sink = sys.argv[1] if len(sys.argv) > 1 else hal_speaker.SINK
    print("sink:", sink, "громкость:", lib_speaker.get_volume(), "%")

    pcm = lib_speaker.tone_pcm(880, 0.5)
    started = time.time()
    lib_speaker.play_pcm(pcm, rate=lib_speaker.RATE, sink=sink,
                         wait=True)
    print("PCM из памяти: %.3f с" % (time.time() - started))

    lib_speaker.write_wav(WAV, pcm, rate=lib_speaker.RATE)
    started = time.time()
    lib_speaker.play_wav(WAV, sink=sink, wait=True)
    print("WAV: %.3f с" % (time.time() - started))

    handle = open(RAW, "wb")
    handle.write(pcm)
    handle.close()
    started = time.time()
    lib_speaker.play_raw(RAW, rate=lib_speaker.RATE, sink=sink, wait=True)
    print("raw-файл: %.3f с" % (time.time() - started))

    chunk = lib_speaker.tone_pcm(660, 0.1)
    stream = lib_speaker.stream(sink=sink, rate=lib_speaker.RATE)
    stream.open()
    started = time.time()
    for _index in range(10):
        stream.write(chunk)
    print("пауза:", lib_speaker.pause(), "paused:", lib_speaker.paused())
    time.sleep(0.5)
    print("продолжить:", lib_speaker.resume(),
          "paused:", lib_speaker.paused())
    for _index in range(10):
        stream.write(chunk)
    closed = stream.close()
    print("поток: %.3f с, close: %s" % (time.time() - started, closed))

    lib_speaker.tone(440, 3.0, sink=sink, wait=False)
    time.sleep(1.0)
    print("играет:", lib_speaker.playing())
    print("stop:", lib_speaker.stop(), "после:", lib_speaker.playing())

    _remove(WAV, RAW)


if __name__ == "__main__":
    main()
