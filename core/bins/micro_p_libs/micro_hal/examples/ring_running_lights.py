#!/usr/bin/env python3
"""Кольцо: `running_lights` фиолетово-синим, яркость 30 %, в цикле.

Запуск на колонке (voice-agent остановлен):

    /home/microp/mp micro_hal/examples/ring_running_lights.py

Ctrl+C — остановить и погасить кольцо.
"""

from micro_hal import hal_ring, lib_ring

VIOLET = (160, 0, 255)
BLUE = (0, 64, 255)
DELAY = 0.18
BRIGHTNESS_PERCENT = 30


def main():
    ring = hal_ring.Ring()
    ring.brightness(ring.brightness() * BRIGHTNESS_PERCENT // 100)
    print("яркость:", ring.brightness())
    try:
        while True:
            lib_ring.running_lights(
                ring, VIOLET, BLUE, cycles=1, delay=DELAY)
    except KeyboardInterrupt:
        pass
    finally:
        ring.off()
        ring.close()


if __name__ == "__main__":
    main()
