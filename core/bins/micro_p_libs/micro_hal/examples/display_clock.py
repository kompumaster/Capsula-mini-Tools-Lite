#!/usr/bin/env python3
"""Часы ЧЧ:ММ на дисплее: яркость, морф минуты, затухание двоеточия.

Запуск на колонке (voice-agent должен быть остановлен):

    /home/microp/mp micro_hal/examples/display_clock.py

Яркость читается из `/home/microp/display_brightness` (0…100), файл
необязателен. При смене минуты различающиеся цифры гаснут и
загораются заново, двоеточие вспыхивает на секунде и плавно гаснет.
"""

import time

from micro_hal import lib_display

BRIGHTNESS = "/home/microp/display_brightness"


def read_brightness():
    try:
        handle = open(BRIGHTNESS)
        try:
            value = int(handle.read().strip())
        finally:
            handle.close()
        if 0 <= value <= 100:
            return value
    except (OSError, ValueError):
        pass
    return None


def sleep_to_next_second():
    target = int(time.time()) + 1
    delay = target - time.time() + 0.005
    if delay > 0:
        time.sleep(delay)


def main():
    lib_display.brightness(100)
    level = 100
    last = None
    sleep_to_next_second()

    while True:
        new_level = read_brightness()
        if new_level is not None and new_level != level:
            level = new_level
            lib_display.brightness(level)

        now = time.localtime()
        text = "%02d%02d" % (now[3], now[4])
        second = now[5]
        minute = now[4]

        def changed():
            current = time.localtime()
            return current[5] != second or current[4] != minute

        if last is not None and text != last:
            lib_display.transition(last, text, fade_out=0.1, fade_in=0.1,
                                   steps=5, colon=True)
            lib_display.colon_fade(seconds=0.8, steps=20, value=None,
                                   stop=changed)
        else:
            lib_display.text(text, colon=True)
            lib_display.colon_fade(seconds=1.0, steps=20, value=None,
                                   stop=changed)

        last = text
        while not changed():
            time.sleep(0.02)


if __name__ == "__main__":
    main()
