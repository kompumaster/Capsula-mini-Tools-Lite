"""Настройки агента в `/home/a_settings.ini`.

Формат — простой INI: секции `[agent]`, `[network]`, `[server]`,
`[ui]`, `[ww]`, `[llm]`, `[asr]`, `[tts]`, `[keys]`, `[audio]`.
Неизвестные секции и ключи сохраняются. Запись атомарная: временный
файл рядом, затем rename.
"""

import os

from micro_agent.errors import AgentError

DEFAULT_PATH = "/home/a_settings.ini"

DEFAULTS = {
    "agent": {
        "tick_ms": "10",
        "max_utterance": "25.0",
        "mic_source": "mics",
        "log_dir": "/home/microp/logs",
        "dialog": "true",
        "age_limit": "120",
    },
    "network": {
        "watchdog_ms": "30000",
        "ap_after_ms": "180000",
    },
    "server": {
        "host": "0.0.0.0",
        "port": "8080",
    },
    "ui": {
        "host": "127.0.0.1",
        "port": "8766",
        "sync_ms": "10000",
        "volume_ms": "5000",
        "display_brightness": "80",
        "ring_brightness": "24",
        "global_brightness": "100",
        "auto_brightness": "true",
        "date_seconds": "20",
    },
    "ww": {
        "model": "/home/microp/micro_ww/models/hey_jarvis.json",
        "threshold": "0.85",
        "window": "4",
        "cooldown_ms": "1000",
    },
    "asr": {
        "engine": "yandexv1",
        "threshold_db": "-48.0",
        "min_speech": "0.13",
        "silence": "1.5",
    },
    "llm": {
        "engine": "deepseek",
        "system_file": "/home/system.txt",
        "session_ttl_seconds": "600",
        "max_turns": "6",
        "max_chars": "4000",
        "max_tokens": "650",
        "temperature": "0.7",
        "thinking": "false",
        "timeout_ms": "20000",
    },
    "tts": {
        "engine": "yandexv1",
        "voice": "filipp",
        "cache": "false",
        "emotion": "neutral",
        "speed": "1.0",
        "lang": "ru-RU",
        "sample_rate": "16000",
    },
    "audio": {
        "bt_alias": "Capsula Mini",
        "save_ms": "5000",
    },
    "keys": {
        "enabled": "true",
        "debounce_ms": "40",
        "hold_ms": "600",
        "click_ms": "350",
        "combo_ms": "100",
        "combo_hold_ms": "2000",
        "step_ms": "150",
        "volume_step": "5",
    },
}

SECTION_ORDER = ("agent", "network", "server", "ui", "ww", "llm",
                 "asr", "tts", "keys", "audio")

INT_KEYS = {
    ("agent", "tick_ms"): (1, 1000),
    ("agent", "age_limit"): (1, 120),
    ("network", "watchdog_ms"): (1, None),
    ("network", "ap_after_ms"): (0, None),
    ("server", "port"): (1, 65535),
    ("ui", "port"): (1, 65535),
    ("ui", "sync_ms"): (1, None),
    ("ui", "volume_ms"): (1, None),
    ("ui", "display_brightness"): (0, 100),
    ("ui", "ring_brightness"): (0, 100),
    ("ui", "global_brightness"): (0, 100),
    ("ui", "date_seconds"): (1, 3600),
    ("ww", "window"): (1, 1000),
    ("ww", "cooldown_ms"): (0, None),
    ("llm", "session_ttl_seconds"): (1, 86400),
    ("llm", "max_turns"): (0, 100),
    ("llm", "max_chars"): (0, 100000),
    ("llm", "max_tokens"): (1, 384000),
    ("llm", "timeout_ms"): (1000, 120000),
    ("tts", "sample_rate"): (8000, 48000),
    ("keys", "debounce_ms"): (0, 1000),
    ("keys", "hold_ms"): (0, 10000),
    ("keys", "click_ms"): (0, 5000),
    ("keys", "combo_ms"): (0, 1000),
    ("keys", "combo_hold_ms"): (0, 10000),
    ("keys", "step_ms"): (1, 5000),
    ("keys", "volume_step"): (1, 50),
    ("audio", "save_ms"): (100, 60000),
}
FLOAT_KEYS = {
    ("agent", "max_utterance"): (0.1, 120.0),
    ("ww", "threshold"): (0.0, 1.0),
    ("llm", "temperature"): (0.0, 2.0),
    ("asr", "threshold_db"): (-120.0, 0.0),
    ("asr", "min_speech"): (0.01, 10.0),
    ("asr", "silence"): (0.1, 10.0),
    ("tts", "speed"): (0.1, 3.0),
}
BOOL_KEYS = (
    ("llm", "thinking"),
    ("keys", "enabled"),
    ("agent", "dialog"),
)
CHOICES = {
    ("tts", "sample_rate"): ("8000", "16000", "48000"),
    ("tts", "emotion"): ("neutral", "good", "evil"),
}


def _copy(sections):
    result = {}
    for name, values in sections.items():
        result[name] = dict(values)
    return result


def _merge_defaults(sections):
    for name, values in DEFAULTS.items():
        target = sections.setdefault(name, {})
        for key, value in values.items():
            target.setdefault(key, value)
    return sections


def _parse(text, errors):
    sections = {}
    current = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().lower()
            if not current:
                errors.append("строка {}: пустая секция".format(number))
                current = None
            else:
                sections.setdefault(current, {})
            continue
        if "=" not in line:
            errors.append("строка {}: нет =".format(number))
            continue
        if current is None:
            errors.append("строка {}: ключ вне секции".format(number))
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key:
            errors.append("строка {}: пустой ключ".format(number))
            continue
        sections[current][key] = value
    return sections


class Settings:
    """Прочитанные настройки с проверкой известных значений."""

    def __init__(self, path=DEFAULT_PATH, text=None):
        self.path = str(path)
        self.sections = {}
        self.errors = []
        self.loaded = False
        if text is None:
            self._read()
        else:
            self._apply(text, loaded=True)

    def _apply(self, text, loaded):
        sections = _parse(text, self.errors)
        self.sections = _merge_defaults(sections)
        self.loaded = loaded
        self._validate()

    @classmethod
    def load(cls, path=DEFAULT_PATH):
        return cls(path=path)

    def _read(self):
        try:
            handle = open(self.path, "r")
        except OSError:
            self.sections = _copy(DEFAULTS)
            self.loaded = False
            return self
        try:
            text = handle.read()
        finally:
            handle.close()
        self._apply(text, loaded=True)
        return self

    @classmethod
    def from_text(cls, text, path="<text>"):
        return cls(path=path, text=text)

    def _default(self, section, key):
        return DEFAULTS.get(section, {}).get(key)

    def _validate(self):
        for (section, key), (low, high) in INT_KEYS.items():
            try:
                self.get_int(section, key, low, high)
            except AgentError as exc:
                self.errors.append("{}: {}".format(key, exc))
                self.sections[section][key] = self._default(section, key)
        for (section, key), (low, high) in FLOAT_KEYS.items():
            try:
                self.get_float(section, key, low, high)
            except AgentError as exc:
                self.errors.append("{}: {}".format(key, exc))
                self.sections[section][key] = self._default(section, key)
        for (section, key), values in CHOICES.items():
            value = str(self.get(section, key, "")).strip().lower()
            if value not in values:
                self.errors.append("{}: допустимо {}".format(
                    key, ", ".join(values)))
                self.sections[section][key] = self._default(section, key)
        for section, key in BOOL_KEYS:
            try:
                self.get_bool(section, key)
            except AgentError as exc:
                self.errors.append("{}: {}".format(key, exc))
                self.sections[section][key] = self._default(section, key)

    def get(self, section, key, default=None):
        return self.sections.get(section, {}).get(key, default)

    def get_int(self, section, key, low=None, high=None):
        value = self.get(section, key)
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise AgentError("{}: не целое число".format(key))
        if low is not None and value < low:
            raise AgentError("{}: меньше {}".format(key, low))
        if high is not None and value > high:
            raise AgentError("{}: больше {}".format(key, high))
        return value

    def get_float(self, section, key, low=None, high=None):
        value = self.get(section, key)
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise AgentError("{}: не число".format(key))
        if value != value:
            raise AgentError("{}: NaN".format(key))
        if low is not None and value < low:
            raise AgentError("{}: меньше {}".format(key, low))
        if high is not None and value > high:
            raise AgentError("{}: больше {}".format(key, high))
        return value

    def get_bool(self, section, key, default=False):
        value = self.get(section, key)
        if value is None:
            return default
        value = str(value).strip().lower()
        if value in ("1", "true", "yes", "on", "да"):
            return True
        if value in ("0", "false", "no", "off", "нет"):
            return False
        raise AgentError("{}: не True/False".format(key))

    def last_volume(self):
        """Сохранённая громкость `[audio] last_volume`; None — не было."""
        value = self.get("audio", "last_volume")
        if value is None or str(value).strip() == "":
            return None
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            self._error("last_volume: не целое число")
            return None
        if number < 0 or number > 100:
            self._error("last_volume: вне 0…100")
            return None
        return number

    def _error(self, message):
        if message not in self.errors:
            self.errors.append(message)

    def set(self, section, key, value):
        self.sections.setdefault(str(section), {})[str(key)] = str(value)
        return self

    def agent_config(self):
        from micro_agent.config import Config
        return Config(
            max_utterance=self.get_float("agent", "max_utterance",
                                         0.1, 120.0),
            watchdog_ms=self.get_int("network", "watchdog_ms", 1),
            ap_after_ms=self.get_int("network", "ap_after_ms", 0),
            tick_ms=self.get_int("agent", "tick_ms", 1, 1000),
            server_port=self.get_int("server", "port", 1, 65535),
            mic_source=self.get("agent", "mic_source"),
            log_dir=self.get("agent", "log_dir"),
        )

    def as_dict(self):
        return _copy(self.sections)

    def save(self, path=None):
        target = str(path or self.path)
        folder = target.rsplit("/", 1)[0] if "/" in target else "."
        if folder and not _exists(folder):
            raise AgentError("нет каталога для настроек: {}".format(folder))
        lines = []
        names = [name for name in SECTION_ORDER if name in self.sections]
        names += sorted(name for name in self.sections
                        if name not in SECTION_ORDER)
        for name in names:
            lines.append("[{}]".format(name))
            values = self.sections[name]
            for key in sorted(values.keys()):
                lines.append("{}={}".format(key, values[key]))
            lines.append("")
        text = "\n".join(lines) + "\n"
        temp = target + ".tmp"
        handle = None
        try:
            handle = open(temp, "w")
            handle.write(text)
            handle.close()
            handle = None
            os.rename(temp, target)
        except Exception as exc:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
            try:
                os.remove(temp)
            except OSError:
                pass
            raise AgentError("сохранить настройки: {}".format(exc))
        return target


def _exists(path):
    try:
        os.stat(path)
    except OSError:
        return False
    return True
