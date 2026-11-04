#!/usr/bin/env python3
"""Bluetooth: колонка как A2DP-приёмник по требованию.

Запуск на колонке (voice-agent должен быть остановлен):

    /home/microp/mp /home/microp/micro_hal/examples/bt_demo.py
    /home/microp/mp /home/microp/micro_hal/examples/bt_demo.py AA:BB:CC:DD:EE:FF

Без аргумента только включает и выключает Bluetooth. С адресом —
подключает телефон, выводит звук на динамик, показывает отдельную
громкость телефона, глушит его на время системного тона и снова
включает. В конце Bluetooth выключается (как по умолчанию).
"""

import sys
import time

from micro_hal import lib_bt, lib_speaker


def wait_source(timeout=10.0):
    """Ждать появления Bluetooth-источника в Pulse."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = lib_bt.status()
        if state["source"]:
            return state
        time.sleep(0.5)
    return lib_bt.status()


def show(state):
    device = state["device"]
    print("  включён: %s, видно: %s" % (state["enabled"],
                                       state["visible"]))
    print("  устройство: %s" % (device["alias"] if device else "нет"))
    print("  источник: %s, звук: %s, громкость: %s, mute: %s" % (
        state["source"], state["audio"], state["volume"],
        state["muted"]))


def main():
    address = sys.argv[1] if len(sys.argv) > 1 else None

    print("включаю Bluetooth")
    show(lib_bt.enable())

    print("устройства:")
    for item in lib_bt.devices():
        print("  %s  %-20s paired=%s connected=%s" % (
            item["address"], item["alias"], item["paired"],
            item["connected"]))

    if address is None:
        print("адрес не задан — только включение/выключение")
        print("выключаю:", lib_bt.disable()["enabled"])
        return

    print("подключаю", address)
    try:
        lib_bt.connect(address)
    except Exception as exc:
        print("  подключение:", type(exc).__name__, str(exc)[:60])

    print("жду источник")
    show(wait_source())

    print("вывожу звук телефона на динамик:", lib_bt.audio_start())
    print("громкость телефона:", lib_bt.volume())

    lib_bt.volume(30)
    print("после volume(30):", lib_bt.volume())

    print("глушу телефон на время системного тона")
    print("  mute:", lib_bt.mute(True), "muted:", lib_bt.muted())
    lib_speaker.tone(880, 0.3)
    print("  возвращаю звук:", lib_bt.mute(False), "muted:", lib_bt.muted())

    lib_bt.volume(100)
    print("громкость телефона восстановлена:", lib_bt.volume())

    print("выключаю Bluetooth:", lib_bt.disable()["enabled"])
    print("готово")


if __name__ == "__main__":
    main()
