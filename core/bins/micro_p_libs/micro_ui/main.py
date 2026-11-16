"""Точка входа micro_ui: дисплей, кольцо и UDP-команды."""

from micro_ui.core import UiCore
from micro_ui.server import DEFAULT_HOST, DEFAULT_PORT, UiServer


def _clock_ms():
    try:
        import time
    except ImportError:
        return 0
    ticks = getattr(time, "ticks_ms", None)
    if ticks is not None:
        return int(ticks())
    monotonic = getattr(time, "monotonic", None)
    if monotonic is not None:
        return int(monotonic() * 1000)
    return 0


def main():
    core = UiCore()
    server = UiServer(core, host=DEFAULT_HOST, port=DEFAULT_PORT,
                      log=print)
    try:
        core.open()
        server.open()
        print("UI READY", server.host, server.port)
        while True:
            now = _clock_ms()
            server.poll(now)
            core.tick(now)
            server.wait(10)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.close()
        except Exception:
            pass
        try:
            core.close()
        except Exception:
            pass
        print("UI STOP")


if __name__ == "__main__":
    main()
