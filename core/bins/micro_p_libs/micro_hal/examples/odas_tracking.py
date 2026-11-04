#!/usr/bin/env python3
"""Трекинг ODAS: провести телефон с тоном слева направо.

Запуск на колонке:

    /home/microp/mp /home/microp/micro_hal/examples/odas_tracking.py

Одновременно включи непрерывный тон 1000 Гц и медленно веди телефон
слева направо перед колонкой, примерно на одной высоте с микрофонами.
Результат — краткая сводка и CSV `/tmp/odas_track.csv`.
"""

import gc
import time

from micro_hal import hal_odas, lib_odas

SECONDS = 20
EVERY = 5          # каждый 5-й кадр, ~20 Гц
CSV = "/tmp/odas_track.csv"


def _best(tracks):
    best = None
    activity = 0.0
    for track in tracks:
        value = track.get("activity", 0.0)
        if value > activity:
            activity = value
            best = track
    return best, activity


def main():
    server = lib_odas.Server()
    server.listen()
    print("listen", server.port)

    pid = hal_odas.start()
    print("started", pid)
    print("t  azimuth  elevation  activity  x  y  z")

    out = open(CSV, "w")
    out.write("t,azimuth,elevation,activity,x,y,z\n")
    started = time.time()
    deadline = started + SECONDS
    next_gc = started + 0.5
    frames = 0
    samples = 0
    lowest = None
    highest = None
    last = None

    try:
        while time.time() < deadline:
            for frame in server.poll(200):
                frames += 1
                if frames % EVERY:
                    continue
                best, activity = _best(frame.get("src", []))
                if best is None or activity < 0.3:
                    continue
                result = lib_odas.direction(best)
                azimuth = result["azimuth"]
                elevation = result["elevation"]
                x = best.get("x", 0.0)
                y = best.get("y", 0.0)
                z = best.get("z", 0.0)
                stamp = time.time() - started
                out.write("%.2f,%.1f,%.1f,%.2f,%.3f,%.3f,%.3f\n" % (
                    stamp, azimuth, elevation, activity, x, y, z))
                samples += 1
                last = result
                if lowest is None or azimuth < lowest:
                    lowest = azimuth
                if highest is None or azimuth > highest:
                    highest = azimuth
                if samples % 10 == 0:
                    print("%.1f  %.1f  %.1f  %.2f  %.3f  %.3f  %.3f" % (
                        stamp, azimuth, elevation, activity, x, y, z))
            if time.time() >= next_gc:
                gc.collect()
                next_gc += 0.5
    finally:
        out.close()
        print("stop", hal_odas.stop())
        server.close()

    print("frames", frames, "samples", samples)
    if samples:
        print("azimuth range", round(lowest, 1), round(highest, 1))
    print("last", last)
    print("csv", CSV)


if __name__ == "__main__":
    main()
