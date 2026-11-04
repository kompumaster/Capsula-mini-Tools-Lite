#!/usr/bin/env python3
"""Громкость с кнопок: vol+/vol-, play дважды, mic, vol-+vol+.

Запуск на колонке (voice-agent должен быть остановлен):

    /home/microp/mp micro_hal/examples/volume_demo.py

vol+ / vol- — шаг 5, play дважды или vol-+vol+ — mute,
mic — напечатать текущую громкость и состояние mute.
"""

from micro_hal import hal_keys, lib_keys, lib_volume


def main():
    device = hal_keys.KeysDevice()
    keys = lib_keys.Keys(device=device)
    volume = lib_volume.Volume("master")
    print("громкость:", volume.get(), "mute:", volume.muted())
    try:
        while True:
            for name, action, count in keys.poll(100):
                if action == "click":
                    if name == "vol+":
                        print("громкость:", volume.up())
                    elif name == "vol-":
                        print("громкость:", volume.down())
                    elif name == "play" and count == 2:
                        print("mute:", volume.toggle())
                    elif name == "mic":
                        print("громкость:", volume.get(),
                              "mute:", volume.muted())
                elif action == "combo" and name == "vol-+vol+":
                    print("mute:", volume.toggle())
    except KeyboardInterrupt:
        pass
    finally:
        keys.close()


if __name__ == "__main__":
    main()
