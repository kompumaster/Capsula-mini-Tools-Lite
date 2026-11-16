"""Настройки micro_agent и их проверки.

Значения по умолчанию; ничего не открывает и не трогает железо.
"""

LOG_DIR = "/home/microp/logs"
DEFAULT_MAX_UTTERANCE = 25.0
DEFAULT_WATCHDOG_MS = 30000
DEFAULT_AP_AFTER_MS = 180000
DEFAULT_TICK_MS = 10
DEFAULT_SERVER_PORT = 8080
DEFAULT_MIC_SOURCE = "mics"


def _number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{} должен быть числом".format(name))
    value = float(value)
    if value != value or value < low or (high is not None and value > high):
        raise ValueError("{} вне допустимого диапазона".format(name))
    return value


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("{} должен быть целым числом".format(name))
    if value < low or (high is not None and value > high):
        raise ValueError("{} вне допустимого диапазона".format(name))
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{} должен быть непустой строкой".format(name))
    return value.strip()


class Config:
    """Проверенные настройки агента."""

    def __init__(self, max_utterance=DEFAULT_MAX_UTTERANCE,
                 watchdog_ms=DEFAULT_WATCHDOG_MS,
                 ap_after_ms=DEFAULT_AP_AFTER_MS,
                 tick_ms=DEFAULT_TICK_MS,
                 server_port=DEFAULT_SERVER_PORT,
                 mic_source=DEFAULT_MIC_SOURCE,
                 log_dir=LOG_DIR):
        self.max_utterance = _number(
            max_utterance, "max_utterance", 0.1, 120.0)
        self.watchdog_ms = _integer(
            watchdog_ms, "watchdog_ms", 1, None)
        self.ap_after_ms = _integer(ap_after_ms, "ap_after_ms", 0, None)
        self.tick_ms = _integer(tick_ms, "tick_ms", 1, 1000)
        self.server_port = _integer(
            server_port, "server_port", 1, 65535)
        self.mic_source = _text(mic_source, "mic_source")
        self.log_dir = _text(log_dir, "log_dir")

    def as_dict(self):
        return {
            "max_utterance": self.max_utterance,
            "watchdog_ms": self.watchdog_ms,
            "ap_after_ms": self.ap_after_ms,
            "tick_ms": self.tick_ms,
            "server_port": self.server_port,
            "mic_source": self.mic_source,
            "log_dir": self.log_dir,
        }
