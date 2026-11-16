"""Точка доступа: запуск и остановка портала `micro_hal`.

Портал - отдельный процесс (`ap_runner.py`), потому что он обслуживает
HTTP вечно. Оркестратор только следит за PID и гасит AP.
"""

import os

from micro_agent.errors import AgentError

RUNNER = "/home/microp/micro_agent/modules/ap_runner.py"
PID_FILE = "/tmp/micro_agent_ap.pid"
LOG_FILE = "/tmp/micro_agent_ap.log"
EXAMPLES = "/home/microp/micro_hal/examples"


def _read_pid():
    try:
        handle = open(PID_FILE, "r")
        try:
            return int(handle.read().strip())
        finally:
            handle.close()
    except (OSError, ValueError):
        return None


def _alive(pid):
    if not pid:
        return False
    try:
        os.stat("/proc/{}".format(pid))
    except OSError:
        return False
    return True


class ApPortal:
    """Портал выбора Wi-Fi на точке доступа."""

    def __init__(self):
        self._pid = None

    def running(self):
        self._pid = _read_pid()
        return _alive(self._pid)

    def start(self):
        if self.running():
            return True
        command = (
            "/usr/bin/micropython {} >> {} 2>&1 & echo $! > {}"
        ).format(RUNNER, LOG_FILE, PID_FILE)
        try:
            code = os.system(command)
        except Exception as exc:
            raise AgentError("AP: {}".format(exc))
        if code not in (0, None):
            raise AgentError("AP: код {}".format(code))
        self._pid = _read_pid()
        return True

    def stop(self):
        pid = _read_pid()
        if pid:
            try:
                os.system("kill {}".format(pid))
            except Exception:
                pass
        try:
            import sys
            if EXAMPLES not in sys.path:
                sys.path.insert(0, EXAMPLES)
            import ap_portal
            ap_portal.stop_ap()
        except Exception as exc:
            raise AgentError("AP stop: {}".format(exc))
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        self._pid = None
        return True

    def status(self):
        return {"running": self.running(), "pid": self._pid}
