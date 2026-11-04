#!/usr/bin/env python3
"""Микрофон: уровни в реальном времени.

Запуск на колонке (voice-agent должен быть остановлен):

    /home/microp/mp /home/microp/micro_hal/examples/mic_demo.py
    /home/microp/mp /home/microp/micro_hal/examples/mic_demo.py 4
    /home/microp/mp /home/microp/micro_hal/examples/mic_demo.py 1 5

Первый аргумент — каналы потока (1 — моно, 4 — сырьё), второй —
сколько секунд слушать (0 или пусто — до Ctrl+C). Каждые 200 мс
печатается dBFS, по выходу — сводка и размер кольца.
"""

import sys
import time

from micro_hal import lib_mic

WIDTH = 32
LOW = -80.0
PERIOD_MS = 200


def bar(level):
    """Полоска уровня: от −80 dBFS до нуля."""
    if level <= LOW:
        return ""
    size = int((level - LOW) * WIDTH / -LOW)
    size = max(1, min(WIDTH, size))
    return "#" * size


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def main():
    channels = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0

    mic = lib_mic.MicStream(channels=channels, ring_seconds=2.0)
    mic.open()
    print("каналов:", mic.channels, "окно:", mic.window(),
          "кадров, кольцо:", mic.ring_frames, "кадров")
    print("dBFS: 0 — полная шкала, −80 — тишина; Ctrl+C — выход")

    levels = []
    started = time.ticks_ms()
    last = started
    try:
        while True:
            if seconds > 0:
                elapsed = time.ticks_diff(time.ticks_ms(), started)
                if elapsed >= seconds * 1000:
                    break
            mic.read()
            level = mic.level()
            levels.append(level)
            now = time.ticks_ms()
            if time.ticks_diff(now, last) >= PERIOD_MS:
                last = now
                if channels > 1:
                    extra = " ".join("%.0f" % value
                                     for value in mic.levels())
                    print("%s %6.1f dBFS  [%s]" % (
                        bar(level), level, extra))
                else:
                    print("%s %6.1f dBFS" % (bar(level), level))
    except KeyboardInterrupt:
        pass
    finally:
        data, first = mic.snapshot()
        mic.close()

    if levels:
        print()
        print("окон: %d, кадров: %d" % (len(levels), mic.frames()))
        print("dBFS мин/медиана/макс: %.1f / %.1f / %.1f" % (
            min(levels), median(levels), max(levels)))
        print("кольцо: %d байт, первый кадр %d" % (len(data), first))
    else:
        print("нет данных")


if __name__ == "__main__":
    main()
