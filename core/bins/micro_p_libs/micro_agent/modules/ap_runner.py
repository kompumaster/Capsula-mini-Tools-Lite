"""Запуск портала AP из отдельного процесса.

`ap_portal.start_ap()` создаёт сокет портала; `main()` не должен
открывать второй, поэтому `_open_server` подменяется на возврат уже
созданного сокета.
"""

import sys

sys.path.insert(0, "/home/microp/micro_hal/examples")

import ap_portal  # noqa: E402


def main():
    ap_portal._open_server = lambda: ap_portal.SERVER
    problem = ap_portal.start_ap()
    print("AP:", problem or "ok")
    sys.stdout.flush()
    try:
        ap_portal.main()
    finally:
        try:
            ap_portal.stop_ap()
        except Exception as exc:
            print("stop_ap:", exc)


if __name__ == "__main__":
    main()
