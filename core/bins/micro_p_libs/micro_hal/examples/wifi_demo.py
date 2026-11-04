#!/usr/bin/env python3
"""Wi-Fi: статус, скан и сохранённые сети.

Запуск на колонке:

    /home/microp/mp /home/microp/micro_hal/examples/wifi_demo.py
    /home/microp/mp .../wifi_demo.py scan
    /home/microp/mp .../wifi_demo.py connect SSID ПАРОЛЬ

По умолчанию только чтение: текущая сеть, адрес, сигнал, кэш скана и
сохранённые сети. `scan` запускает свежий скан — связь на мгновение
ухудшается. `connect` **рвёт канал**: сторож вернёт прежнюю сеть,
если новая не поднимется за минуту.
"""

import sys
import time

from micro_hal import lib_wifi


def show_status():
    value = lib_wifi.status()
    print("сеть:      %s" % value["ssid"])
    print("состояние: %s" % value["state"])
    print("адрес:     %s" % value["ip"])
    print("канал:     %s МГц" % value["freq"])
    print("сигнал:    %s дБм" % value["signal"])


def show_scan(items):
    print("сети в эфире:")
    for item in items:
        lock = "" if "PSK" not in item.get("flags", "") else " *"
        print("  %4d дБм  %s%s" % (item["signal"], item["ssid"], lock))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    show_status()
    print("сохранённые:", ", ".join(lib_wifi.saved()))

    if mode == "scan":
        print("скан (связь на мгновение ухудшится)")
        show_scan(lib_wifi.scan(fresh=True))
        return

    if mode == "connect":
        if len(sys.argv) < 4:
            print("нужно: connect SSID ПАРОЛЬ")
            return
        ssid = sys.argv[2]
        psk = sys.argv[3]
        print("подключаюсь к %r; канал может пропасть до минуты" % ssid)
        started = time.time()
        try:
            result = lib_wifi.connect(ssid, psk)
            print("готово: %s, %s, %.1f с" % (
                result["ssid"], result["ip"], result["seconds"]))
        except Exception as exc:
            print("не вышло:", type(exc).__name__, str(exc)[:100])
        print("прошло: %.1f с" % (time.time() - started))
        show_status()
        return

    show_scan(lib_wifi.scan())
    print("скан из кэша; свежий — `wifi_demo.py scan`")


if __name__ == "__main__":
    main()
