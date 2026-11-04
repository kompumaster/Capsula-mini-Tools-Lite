"""Wi-Fi: политика и безопасное переключение сетей.

Главное правило: единственный канал управления колонкой — Wi-Fi.
Поэтому переключение сети делается только вместе со **сторожем**:
до `select_network` запускается независимый процесс, который через
`timeout` вернёт прежнюю сеть, если не появился `ok`-файл.

Сам сторож — маленький shell-скрипт в `/tmp`: он не зависит ни от
MicroPython, ни от `/home`, и переживает обрыв SSH.
"""

import os
import time

from micro_hal import hal_common, hal_wifi
from micro_hal.hal_common import HalError

__all__ = [
    "GUARD", "OK", "GUARD_LOG", "GUARD_STATE",
    "ASSOC_TIMEOUT", "DHCP_TIMEOUT",
    "status", "scan", "saved", "connect", "forget", "disconnect",
    "guard_write", "guard_start", "guard_ok", "guard_log",
]

GUARD = "/tmp/micro_hal_wifi_guard.sh"
OK = "/tmp/micro_hal_wifi.ok"
GUARD_LOG = "/tmp/micro_hal_wifi_guard.log"
GUARD_STATE = "/tmp/micro_hal_wifi.guard"
ASSOC_TIMEOUT = 25.0
DHCP_TIMEOUT = 15.0
SCAN_WAIT = 3.0

# Типы key_mgmt, которые поддерживает колонка.
MGMT_OPEN = "NONE"
MGMT_PSK = "WPA-PSK"
MGMT_SAE = "SAE"


def _key_mgmt(flags, psk=None):
    """Тип key_mgmt по флагам скана и наличию пароля.

    `PSK` — WPA/WPA2 (в переходном WPA2+WPA3 тоже: он совместимее),
    только `SAE` — WPA3, иначе открытая сеть. EAP/802.1X не умеем.
    """
    flags = str(flags or "")
    if "EAP" in flags or "802.1X" in flags:
        raise HalError("корпоративная сеть (802.1X) не поддерживается")
    if "WEP" in flags:
        raise HalError("сеть с WEP не поддерживается")
    if "PSK" in flags:
        return MGMT_PSK
    if "SAE" in flags:
        return MGMT_SAE
    if flags:
        return MGMT_OPEN
    return MGMT_PSK if psk else MGMT_OPEN

_SCRIPT = """#!/bin/sh
# Сторож Wi-Fi: нет ok-файла к моменту таймаута — вернуть старую сеть.
# Токен отменяет сторожа, если за это время запустили новый connect.
new="$1"
old="$2"
wait="$3"
dry="$4"
token="$5"
log="{log}"
ok="{ok}"
state="{state}"
sleep "$wait"
current=$(cat "$state" 2>/dev/null)
if [ "$current" != "$token" ]; then
    echo "$(date '+%H:%M:%S') откат отменён: есть более новый сторож" >> "$log"
    exit 0
fi
if [ -f "$ok" ]; then
    echo "$(date '+%H:%M:%S') ok: откат не нужен" >> "$log"
    exit 0
fi
echo "$(date '+%H:%M:%S') откат: возвращаю сеть $old" >> "$log"
if [ "$dry" = "1" ]; then
    echo "dry: wpa_cli remove_network $new" >> "$log"
    echo "dry: wpa_cli select_network $old" >> "$log"
    echo "dry: wpa_cli reconnect" >> "$log"
    exit 0
fi
wpa_cli -i {iface} remove_network "$new" >> "$log" 2>&1
wpa_cli -i {iface} select_network "$old" >> "$log" 2>&1
wpa_cli -i {iface} reconnect >> "$log" 2>&1
"""


def _script_text():
    return _SCRIPT.format(log=GUARD_LOG, ok=OK, state=GUARD_STATE,
                          iface=hal_wifi.IFACE)


def guard_write(path=None):
    """Записать сторож на диск и сделать исполняемым."""
    path = GUARD if path is None else str(path)
    hal_common.write_text(path, _script_text())
    try:
        os.chmod(path, 0o700)
    except (OSError, AttributeError):
        # В MicroPython нет os.chmod; запускаем через /bin/sh.
        pass
    return path


def guard_start(new_id, old_id, timeout=60, dry_run=False, path=None):
    """Запустить сторожа в фоне; вернуть команду.

    `dry_run=True` — только записать в лог, что сделал бы откат.
    Токен в файле состояния отменяет предыдущего сторожа: если за
    время его сна начали новый `connect`, старый откат не сработает.
    """
    path = GUARD if path is None else str(path)
    guard_write(path)
    token = "{}-{}".format(int(time.time() * 1000),
                           hal_common.self_pid())
    hal_common.write_text(GUARD_STATE, token)
    try:
        os.remove(OK)
    except OSError:
        pass
    command = (
        "nohup /bin/sh {path} {new} {old} {timeout} {dry} {token} "
        ">/dev/null 2>&1 &"
    ).format(path=path, new=int(new_id), old=int(old_id),
             timeout=int(timeout), dry="1" if dry_run else "0",
             token=token)
    hal_common.run(command)
    return command


def guard_ok():
    """Отметить успех: сторож не будет откатывать."""
    hal_common.write_text(OK, str(int(time.time())))
    return True


def guard_log(lines=10):
    """Последние строки журнала сторожа."""
    try:
        text = hal_common.read_text(GUARD_LOG)
    except OSError:
        return ""
    parts = [line for line in text.split("\n") if line]
    if lines > 0:
        parts = parts[-lines:]
    return "\n".join(parts)


def status():
    """Текущая сеть, адрес и уровень сигнала."""
    info = hal_wifi.status()
    signal = None
    bssid = info.get("bssid")
    if bssid:
        for item in hal_wifi.scan_results():
            if item["bssid"] == bssid:
                signal = item["signal"]
                break
    ip = None
    if info.get("state") == "COMPLETED":
        ip = hal_wifi.ip_address(timeout=2)
    return {
        "ssid": info.get("ssid"),
        "state": info.get("state"),
        "ip": ip,
        "freq": info.get("freq"),
        "id": info.get("id"),
        "signal": signal,
    }


def scan(fresh=False, wait=3.0):
    """Сети, сильные первыми, без дублей по SSID.

    `wait` — сколько ждать результатов свежего скана: при поднятом AP
    радио занято, и трёх секунд иногда мало.
    """
    items = (hal_wifi.scan(wait=wait) if fresh
             else hal_wifi.scan_results())
    best = {}
    for item in items:
        ssid = item.get("ssid") or ""
        if not ssid:
            continue
        current = best.get(ssid)
        if current is None or item["signal"] > current["signal"]:
            best[ssid] = item
    result = list(best.values())
    result.sort(key=lambda item: -item["signal"])
    return result


def _current_network():
    for item in hal_wifi.networks():
        if item["current"]:
            return item
    return None


def _visible(ssid, fresh=False):
    """Найти сеть в кэше скана; `fresh=True` — сначала новый скан."""
    if fresh:
        hal_wifi.scan(fresh=True, wait=SCAN_WAIT)
    for item in hal_wifi.scan_results():
        if item["ssid"] == ssid:
            return item
    return None


def connect(ssid, psk=None, timeout=60.0, hidden=False,
            allow_no_rollback=False, dry_run=False, key_mgmt=None):
    """Подключиться к сети с автоматическим откатом.

    Порядок: проверить → добавить сеть → **запустить сторожа** →
    `select_network` → ждать ассоциацию и адрес → `save_config`.
    При неудаче — вернуть прежнюю сеть и бросить `HalError`.

    Если SSID нет в кэше скана, делается один свежий скан; `dry_run`
    тоже может его запустить (это чтение, конфиг не меняется).

    Тип защиты берётся из флагов скана: открытая, WPA/WPA2-PSK или
    WPA3-SAE. `key_mgmt` (`NONE`/`WPA-PSK`/`SAE`) перекрывает выбор —
    нужно для скрытых сетей, которых нет в скане. `hidden=True` также
    включает `scan_ssid=1`, иначе скрытый SSID не найти.

    `dry_run=True` — только проверить и вернуть план, ничего не
    меняя.
    """
    ssid = str(ssid)
    if not ssid:
        raise HalError("пустой SSID")

    current = _current_network()
    state = hal_wifi.status()
    same = current is not None and current["ssid"] == ssid
    if same and state.get("state") == "COMPLETED":
        return {"ssid": ssid, "ip": hal_wifi.ip_address(timeout=2),
                "seconds": 0.0, "changed": False, "saved": True}

    if same:
        # Сеть уже в конфиге: не добавляем дубль, только переподключение.
        plan = {
            "ssid": ssid,
            "old_id": current["id"],
            "old_ssid": current["ssid"],
            "timeout": float(timeout),
            "key_mgmt": None,
            "reconnect": True,
        }
        if dry_run:
            return plan
        return _reconnect_current(ssid)

    visible = _visible(ssid)
    if visible is None and not hidden:
        # Кэш мог устареть: один свежий скан. Если скан занят
        # (FAIL-BUSY), ещё раз читаем кэш — он мог обновиться.
        try:
            visible = _visible(ssid, fresh=True)
        except HalError:
            visible = _visible(ssid)
    if visible is None and not hidden:
        raise HalError("сеть {} не видна; для скрытой hidden=True".format(
            ssid))
    flags = visible.get("flags", "") if visible is not None else ""
    kind = _key_mgmt(flags, psk) if key_mgmt is None else str(key_mgmt)
    if kind not in (MGMT_OPEN, MGMT_PSK, MGMT_SAE):
        raise HalError("неизвестный key_mgmt: {!r}".format(kind))
    if kind in (MGMT_PSK, MGMT_SAE) and not psk:
        raise HalError("для {} нужен пароль".format(ssid))
    if kind == MGMT_OPEN:
        psk = None
    if current is None and not allow_no_rollback:
        raise HalError("нет текущей сети для отката; нужен "
                       "allow_no_rollback=True")

    plan = {
        "ssid": ssid,
        "old_id": current["id"] if current else None,
        "old_ssid": current["ssid"] if current else None,
        "timeout": float(timeout),
        "key_mgmt": kind,
    }
    if dry_run:
        return plan

    # Один connect за раз: сторож, OK-файл и конфиг wpa общие.
    wifi_lock = hal_common.lock("wifi")
    try:
        new_id = hal_wifi.add_network(ssid, psk, key_mgmt=kind,
                                      scan_ssid=hidden)
        started = time.time()
        try:
            # Сторож ДО переключения: если SSH оборвётся, он вернёт сеть.
            if current is not None:
                guard_start(new_id, current["id"], timeout=timeout)
            hal_wifi.select_network(new_id)
            if not hal_wifi.wait_state("COMPLETED", ASSOC_TIMEOUT):
                raise HalError("не удалось подключиться к {}".format(ssid))
            ip = hal_wifi.ip_address(timeout=DHCP_TIMEOUT)
            if ip is None:
                raise HalError("нет адреса от dhcpcd для {}".format(ssid))
        except Exception as exc:
            restored = _rollback(new_id, current)
            if current is None:
                tail = "сети не было"
            elif restored:
                tail = "вернул прежнюю сеть"
            else:
                tail = "прежнюю сеть вернуть не удалось"
            raise HalError("{}: {}".format(exc, tail))

        guard_ok()
        saved = True
        try:
            hal_wifi.save_config()
        except HalError:
            saved = False
        return {"ssid": ssid, "ip": ip,
                "seconds": time.time() - started, "changed": True,
                "saved": saved}
    finally:
        wifi_lock.release()


def _reconnect_current(ssid):
    """Переподключиться к уже настроенной сети, не меняя конфиг."""
    wifi_lock = hal_common.lock("wifi")
    try:
        started = time.time()
        hal_wifi.reconnect()
        if not hal_wifi.wait_state("COMPLETED", ASSOC_TIMEOUT):
            raise HalError(
                "не удалось переподключиться к {}".format(ssid))
        ip = hal_wifi.ip_address(timeout=DHCP_TIMEOUT)
        if ip is None:
            raise HalError("нет адреса от dhcpcd для {}".format(ssid))
        return {"ssid": ssid, "ip": ip,
                "seconds": time.time() - started, "changed": False,
                "saved": True}
    finally:
        wifi_lock.release()


def _wait_current(current, timeout):
    """Дождаться, что поднялась именно прежняя сеть.

    `COMPLETED` сам по себе не годится: если новая сеть
    ассоциировалась, но не получила адрес, состояние всё ещё
    `COMPLETED` от неё. Ждём совпадения id или SSID.
    """
    deadline = time.time() + float(timeout)
    while True:
        try:
            info = hal_wifi.status()
        except HalError:
            info = {}
        if (info.get("state") == "COMPLETED"
                and (info.get("id") == current["id"]
                     or info.get("ssid") == current["ssid"])):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.5)


def _rollback(new_id, current):
    """Вернуть прежнюю сеть; True, если она поднялась."""
    try:
        hal_wifi.remove_network(new_id)
    except HalError:
        pass
    if current is None:
        return False
    try:
        hal_wifi.select_network(current["id"])
        hal_wifi.reconnect()
    except HalError:
        return False
    if _wait_current(current, DHCP_TIMEOUT):
        guard_ok()
        return True
    return False


def saved():
    """Сохранённые SSID."""
    return hal_wifi.saved()


def forget(ssid):
    """Удалить сеть; текущую удалять нельзя."""
    ssid = str(ssid)
    wifi_lock = hal_common.lock("wifi")
    try:
        entries = [item for item in hal_wifi.networks()
                   if item["ssid"] == ssid]
        if not entries:
            raise HalError("нет сети {}".format(ssid))
        if any(item["current"] for item in entries):
            raise HalError("нельзя удалить текущую сеть {}".format(ssid))
        for item in entries:
            hal_wifi.remove_network(item["id"])
        hal_wifi.save_config()
        return True
    finally:
        wifi_lock.release()


def disconnect(allow=False):
    """Отключиться от сети — только с явным разрешением."""
    if not allow:
        raise HalError("disconnect рвёт канал; нужен allow=True")
    wifi_lock = hal_common.lock("wifi")
    try:
        return hal_wifi.disconnect()
    finally:
        wifi_lock.release()
