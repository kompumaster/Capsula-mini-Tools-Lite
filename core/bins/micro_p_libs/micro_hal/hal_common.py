"""Общие вещи для HAL-модулей MicroPython.

Здесь нет работы с конкретным железом: только пути, проверки, запуск
команд и определение конфликта с `voice-agent`. Модули `hal_*` должны
импортировать этот файл и не дублировать проверки.

Совместимость: MicroPython 1.30 (unix, AArch64) и CPython 3.9+ — чтобы
чистую логику можно было тестировать на хосте в `_venv`.
"""

import os
import time

__all__ = [
    "HalError", "exists", "read_text", "write_text", "run", "capture",
    "Lock", "lock", "locked", "self_pid",
    "processes", "stale_owner",
    "is_root", "require_root", "va_pids", "va_running",
    "require_va_stopped", "stop_va", "start_va",
    "display_channels", "check", "format_check",
    "DEV_TOP_LEDS", "DEV_INPUT", "SYSFS_LEDS", "SYSFS_LIGHT",
    "VA_INIT", "MIC_BINS", "SPK_BINS", "CAPTURE", "LOCK_DIR",
]

# Пути устройств и служебных файлов.
DEV_TOP_LEDS = "/dev/topleds"
DEV_INPUT = "/dev/input/event0"
SYSFS_LEDS = "/sys/class/leds"
SYSFS_LIGHT = (
    "/sys/devices/platform/soc/ffd00000.cbus/ffd1e000.i2c/"
    "i2c-0/0-0029/iio:device0/in_illuminance_both_input"
)
VA_INIT = "/etc/init.d/S97voice-agent.sh"
MIC_BINS = ("/usr/bin/parec",)
SPK_BINS = ("/usr/bin/paplay", "/usr/bin/pactl")
CAPTURE = "/tmp/micro_hal_capture.{}.out"   # PID подставляется в capture()
LOCK_DIR = "/tmp"

# Замки, которые держит этот процесс: имя → счётчик.
_LOCKS = {}
_SELF_PID = None


class HalError(Exception):
    """Ошибка HAL: нет устройства, нет прав, конфликт с voice-agent."""


def exists(path):
    """Есть ли путь (файл, каталог или устройство)."""
    try:
        os.stat(path)
    except OSError:
        return False
    return True


def read_text(path):
    """Прочитать текстовый файл целиком."""
    handle = open(path, "r")
    try:
        return handle.read()
    finally:
        handle.close()


def write_text(path, text):
    """Записать текст в файл (перезапись)."""
    handle = open(path, "w")
    try:
        handle.write(text)
    finally:
        handle.close()


def run(command):
    """Выполнить команду через shell и вернуть код выхода 0…255."""
    status = os.system(command)
    if status < 0:
        raise HalError("не удалось выполнить: {}".format(command))
    # os.system() возвращает wait status; интересует код выхода.
    return status >> 8 if status > 255 else status


def capture(command):
    """Выполнить команду и вернуть `(код, stdout+stderr)`.

    В MicroPython нет `os.popen`, поэтому вывод идёт через временный
    файл `CAPTURE` с PID процесса: у каждого процесса свой файл, два
    скрипта не перетирают вывод друг друга. После чтения файл
    удаляется.
    """
    path = CAPTURE.format(self_pid())
    code = run("{} > {} 2>&1".format(command, path))
    try:
        text = read_text(path)
    except OSError:
        text = ""
    try:
        os.remove(path)
    except OSError:
        pass
    return code, text


def processes():
    """Список `(pid, cmdline)` процессов; cmdline — с пробелами."""
    result = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return result
    for name in entries:
        if not name.isdigit():
            continue
        try:
            text = read_text("/proc/{}/cmdline".format(name))
        except OSError:
            continue
        if not text:
            continue
        result.append((int(name), text.replace("\x00", " ").strip()))
    return result


def stale_owner(pid, prefix="micro_hal_"):
    """Остался ли процесс `pid` без живого владельца.

    В `/tmp` ищутся файлы `<prefix><owner>.pid`, где записан `pid`.
    Если владелец из имени файла уже мёртв — процесс осиротел и его
    можно остановить из другого скрипта. Живого владельца не трогаем.
    """
    pid = str(int(pid))
    try:
        names = os.listdir("/tmp")
    except OSError:
        return False
    for name in names:
        if not name.startswith(prefix) or not name.endswith(".pid"):
            continue
        owner = name[len(prefix):-len(".pid")]
        if not owner.isdigit():
            continue
        try:
            text = read_text("/tmp/" + name).strip()
        except OSError:
            continue
        if text == pid and not exists("/proc/" + owner):
            return True
    return False


def is_root():
    """Запущены ли мы от root (по /proc/self/status)."""
    try:
        text = read_text("/proc/self/status")
    except OSError:
        return False
    for line in text.split("\n"):
        if line.startswith("Uid:"):
            parts = line.split()
            return len(parts) > 1 and parts[1] == "0"
    return False


def require_root():
    """Бросить HalError, если нет root."""
    if not is_root():
        raise HalError("нужен root: доступ к /dev, sysfs и Pulse")


def va_pids():
    """PID процессов `voice-agent` (пустой список, если не запущен)."""
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    pids = []
    for name in entries:
        if not name.isdigit():
            continue
        try:
            comm = read_text("/proc/{}/comm".format(name)).strip()
        except OSError:
            continue
        if comm == "voice-agent":
            pids.append(int(name))
    return pids


def va_running():
    """Запущен ли стоковый `voice-agent`."""
    return len(va_pids()) > 0


def require_va_stopped(what="устройство"):
    """Предупредить, что voice-agent владеет железом."""
    if va_running():
        raise HalError(
            "voice-agent запущен и владеет {}: остановите его "
            "(S97voice-agent.sh stop) или используйте vkvoice".format(what)
        )


def stop_va():
    """Остановить voice-agent (только по явному вызову)."""
    require_root()
    if not va_running():
        return 0
    return run("{} stop".format(VA_INIT))


def start_va():
    """Запустить voice-agent обратно."""
    require_root()
    return run("{} start".format(VA_INIT))


def display_channels():
    """Сколько каналов `clock-led*` есть в sysfs (0 — дисплея нет)."""
    try:
        names = os.listdir(SYSFS_LEDS)
    except OSError:
        return 0
    return len([name for name in names if name.startswith("clock-led")])


def check():
    """Список (что, состояние) без записи в железо."""
    channels = display_channels()
    return [
        ("root", "да" if is_root() else "нет"),
        ("voice-agent", "запущен" if va_running() else "остановлен"),
        ("ring", "есть" if exists(DEV_TOP_LEDS) else "нет"),
        ("display", "{} каналов".format(channels) if channels else "нет"),
        ("keys", "есть" if exists(DEV_INPUT) else "нет"),
        ("light", "есть" if exists(SYSFS_LIGHT) else "нет"),
        ("mic", "есть" if all(exists(p) for p in MIC_BINS) else "нет"),
        ("speaker", "есть" if all(exists(p) for p in SPK_BINS) else "нет"),
    ]


def format_check():
    """`check()` в виде готовых строк для печати."""
    return ["{:<14} {}".format(name, value) for name, value in check()]


def _self_pid():
    """PID текущего процесса.

    В MicroPython нет `os.getpid`, зато есть `/proc/self/stat`.
    """
    global _SELF_PID
    if _SELF_PID is not None:
        return _SELF_PID
    try:
        _SELF_PID = int(os.getpid())
        return _SELF_PID
    except AttributeError:
        pass
    try:
        _SELF_PID = int(read_text("/proc/self/stat").split(" ", 1)[0])
    except (OSError, ValueError, IndexError):
        _SELF_PID = 0
    return _SELF_PID


def _lock_path(name):
    return "{}/micro_hal_{}.lock".format(LOCK_DIR, name)


def _lock_pid(path):
    """PID владельца из файла замка или None."""
    try:
        text = read_text("{}/pid".format(path)).strip()
    except OSError:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _pid_alive(pid):
    return exists("/proc/{}".format(pid))


def _lock_is_dir(path):
    """Каталог ли это (а не мусорный файл на месте замка)."""
    try:
        info = os.stat(path)
    except OSError:
        return False
    try:
        mode = info[0]
    except (IndexError, TypeError):
        mode = info.st_mode
    return (mode & 0o170000) == 0o040000


def _lock_age(path):
    """Сколько секунд каталогу замка, или None."""
    try:
        info = os.stat(path)
    except OSError:
        return None
    try:
        moment = info[8]
    except (IndexError, TypeError):
        moment = info.st_mtime
    return time.time() - moment


def _lock_drop(path):
    """Удалить замок: pid, каталог или мусорный файл."""
    try:
        os.remove("{}/pid".format(path))
    except OSError:
        pass
    try:
        os.rmdir(path)
        return
    except OSError:
        pass
    try:
        os.remove(path)
    except OSError:
        pass


class Lock:
    """Замок на ресурс: атомарный каталог с PID владельца.

    `os.mkdir` на плате и на хосте атомарен: второй процесс получает
    `EEXIST`. Замок с мёртвым PID перехватывается.
    """

    def __init__(self, name, path):
        self.name = name
        self.path = path
        self._released = False

    def owner(self):
        """PID владельца замка или None."""
        return _lock_pid(self.path)

    def release(self):
        """Освободить; True, если замок был наш."""
        if self._released:
            return False
        self._released = True
        count = _LOCKS.get(self.name, 1) - 1
        if count > 0:
            _LOCKS[self.name] = count
            return True
        _LOCKS.pop(self.name, None)
        owner = _lock_pid(self.path)
        if owner is None or owner == _self_pid():
            # Нет pid — значит запись не удалась (или её подменили
            # в тесте); свой замок всё равно надо снять.
            _lock_drop(self.path)
        return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()


def self_pid():
    """PID текущего процесса (0, если не удалось узнать)."""
    return _self_pid()


def _lock_state(path):
    """Состояние замка: `free`, `stale` или `busy`, и PID владельца.

    Общее правило для `lock()` и `locked()`: пустой каталог без `pid`
    считается занятым, пока ему меньше 10 с (процесс мог умереть между
    `mkdir` и записью pid); позже — устаревшим.
    """
    if not exists(path):
        return "free", None
    owner = _lock_pid(path)
    if not _lock_is_dir(path):
        return "stale", owner
    if owner is not None:
        if _pid_alive(owner):
            return "busy", owner
        return "stale", owner
    age = _lock_age(path)
    if age is None or age > 10.0:
        return "stale", None
    return "busy", None


def lock(name, timeout=0.0):
    """Взять замок на ресурс; `HalError`, если занято.

    `timeout` — сколько секунд ждать чужой замок (0 — сразу).
    Замок с мёртвым PID или пустой старше 10 с перехватывается.
    """
    name = str(name)
    if not name:
        raise HalError("пустое имя замка")
    allowed = ("abcdefghijklmnopqrstuvwxyz"
               "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    for char in name:
        if char not in allowed:
            raise HalError("неверное имя замка: {!r}".format(name))
    path = _lock_path(name)

    if name in _LOCKS:
        _LOCKS[name] += 1
        return Lock(name, path)

    deadline = time.time() + max(0.0, float(timeout))
    attempts = 0
    while True:
        try:
            os.mkdir(path)
        except OSError as exc:
            if not exists(path):
                # Не «уже занято», а нет каталога/прав/места: иначе
                # цикл ниже крутился бы вечно.
                raise HalError(
                    "ресурс {}: не создать замок: {}".format(name, exc))
            state, owner = _lock_state(path)
            if state == "free":
                continue
            if state == "stale":
                attempts += 1
                if attempts > 5:
                    raise HalError(
                        "ресурс {}: не удаётся снять старый замок".format(
                            name))
                _lock_drop(path)
                continue
            if time.time() >= deadline:
                if owner is None:
                    raise HalError(
                        "ресурс {} занят: замок без pid".format(name))
                raise HalError("ресурс {} занят процессом {}".format(
                    name, owner))
            time.sleep(0.05)
            continue
        try:
            write_text("{}/pid".format(path), str(_self_pid()))
        except OSError:
            _lock_drop(path)
            raise
        _LOCKS[name] = 1
        return Lock(name, path)


def locked(name):
    """Занят ли ресурс кем-либо (включая этот процесс)."""
    name = str(name)
    if name in _LOCKS:
        return True
    state, _owner = _lock_state(_lock_path(name))
    return state == "busy"
