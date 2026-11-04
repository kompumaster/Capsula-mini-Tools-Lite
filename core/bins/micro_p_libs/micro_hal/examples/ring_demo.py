#!/usr/bin/env python3
"""Демо кольца: 15 эффектов `lib_ring` на реальном `hal_ring.Ring`.

Запуск на колонке (voice-agent должен быть остановлен):

    /home/microp/mp micro_hal/examples/ring_demo.py

Эффекты идут по одному разу, как в `test_micro_hal_ring_effects.py`,
но с живыми паузами. Ctrl+C — остановить и погасить кольцо.
"""

from micro_hal import hal_ring, lib_ring

EFFECTS = (
    ("rainbow", lambda ring: lib_ring.rainbow(
        ring, cycles=1, delay=0.02)),
    ("breathe", lambda ring: lib_ring.breathe(
        ring, (0, 0, 255), cycles=1, delay=0.02)),
    ("comet", lambda ring: lib_ring.comet(
        ring, (255, 0, 0), tail=4, cycles=1, delay=0.05)),
    ("theater_chase", lambda ring: lib_ring.theater_chase(
        ring, (0, 255, 0), cycles=1, delay=0.08)),
    ("color_wipe", lambda ring: lib_ring.color_wipe(
        ring, (0, 0, 255), cycles=1, delay=0.03)),
    ("static", lambda ring: lib_ring.static(ring, (255, 0, 0))),
    ("blink", lambda ring: lib_ring.blink(
        ring, (0, 255, 0), cycles=2, delay=0.2)),
    ("fade", lambda ring: lib_ring.fade(
        ring, (255, 0, 0), cycles=1, delay=0.02)),
    ("twinkle", lambda ring: lib_ring.twinkle(
        ring, (255, 255, 0), cycles=5, delay=0.1)),
    ("sparkle", lambda ring: lib_ring.sparkle(
        ring, (255, 0, 255), cycles=5, delay=0.05)),
    ("larson_scanner", lambda ring: lib_ring.larson_scanner(
        ring, (255, 0, 0), cycles=1, delay=0.03)),
    ("bicolor_chase", lambda ring: lib_ring.bicolor_chase(
        ring, (255, 0, 0), (0, 0, 255), cycles=1, delay=0.08)),
    ("tricolor_chase", lambda ring: lib_ring.tricolor_chase(
        ring, ((255, 0, 0), (0, 255, 0), (0, 0, 255)),
        cycles=1, delay=0.08)),
    ("running_lights", lambda ring: lib_ring.running_lights(
        ring, (255, 0, 0), (0, 0, 255), cycles=1, delay=0.04)),
    ("fire_flicker", lambda ring: lib_ring.fire_flicker(
        ring, cycles=10, delay=0.05)),
)


def main():
    ring = hal_ring.Ring()
    print("эффектов:", len(EFFECTS))
    try:
        for name, effect in EFFECTS:
            print(name)
            effect(ring)
    except KeyboardInterrupt:
        print("stop")
    finally:
        ring.off()
        ring.close()


if __name__ == "__main__":
    main()
