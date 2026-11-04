"""Демо кнопок CSK05T: hal_keys + lib_keys."""

from micro_hal import hal_keys, lib_keys


def main():
    device = hal_keys.KeysDevice()
    keys = lib_keys.Keys(device=device)
    print("device: %s (%s)" % (device.path, device.name))
    print("нажмите кнопки; Ctrl+C — выход")
    try:
        while True:
            for name, action, count in keys.poll(100):
                print("%-8s %-12s %d" % (name, action, count))
    except KeyboardInterrupt:
        print("stop")
    finally:
        keys.close()


if __name__ == "__main__":
    main()
