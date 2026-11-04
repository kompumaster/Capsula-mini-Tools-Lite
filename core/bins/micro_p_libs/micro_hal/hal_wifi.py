"""Wi-Fi: `wpa_cli` и `dhcpcd`, только команды стека.

Политика переключения сетей (сторож, откат) — в `lib_wifi`.
`iw`/`iwconfig` на плате нет, поэтому скан идёт через `wpa_cli`.

Осторожно: `select_network` и `reconnect` рвут текущее соединение.
Поэтому `hal_wifi` их только выполняет, решение принимает `lib_wifi`.
"""

import time

from micro_hal import hal_common
from micro_hal.hal_common import HalError

__all__ = [
    "IFACE", "CONF", "WPA_CLI", "DHCPCD", "IP", "KEY_MGMT",
    "available", "interface", "status", "networks", "saved",
    "scan", "scan_results", "add_network", "set_network",
    "select_network", "remove_network", "save_config", "reconnect",
    "disconnect",
    "wait_state", "ip_address", "dhcp_renew",
]

IFACE = "wlan0"
CONF = "/etc/wpa_supplicant.conf"
WPA_CLI = "/usr/sbin/wpa_cli"
DHCPCD = "/sbin/dhcpcd"
IP = "/sbin/ip"

# Типы key_mgmt, которые умеем настраивать: открытая, WPA/WPA2, WPA3.
KEY_MGMT = ("NONE", "WPA-PSK", "SAE")


def _shell(value):
    """Значение для shell в одинарных кавычках.

    Нужно, чтобы двойные кавычки для `wpa_cli` (ssid/psk) дошли
    до него, а не были съедены оболочкой.
    """
    text = str(value)
    if "'" in text or "\n" in text or "\r" in text:
        raise HalError("недопустимое значение: {!r}".format(text))
    return "'{}'".format(text)


def _wpa(*args):
    """Выполнить `wpa_cli -i wlan0 ...` и вернуть вывод."""
    command = "{} -i {} {}".format(
        WPA_CLI, IFACE, " ".join(_shell(arg) for arg in args))
    code, text = hal_common.capture(command)
    if code != 0:
        raise HalError("wpa_cli {}: код {}: {}".format(
            " ".join(args), code, text.strip()[:120]))
    return text


def _ok(*args):
    """Команда, которая должна ответить `OK`."""
    text = _wpa(*args).strip()
    if text != "OK":
        raise HalError("wpa_cli {}: {}".format(" ".join(args),
                                               text[:80] or "нет ответа"))
    return True


def _quote_value(value):
    """Строковое значение для `wpa_cli`: в двойных кавычках."""
    text = str(value)
    if '"' in text or "\n" in text or "\r" in text:
        raise HalError("недопустимое значение: {!r}".format(text))
    return '"{}"'.format(text)


def available():
    """Есть ли `wpa_cli` и отвечает ли интерфейс."""
    if not hal_common.exists(WPA_CLI):
        return False
    try:
        info = status()
        return bool(info.get("ssid") or info.get("wpa_state"))
    except HalError:
        return False


def interface():
    return IFACE


def status():
    """Текущее состояние: ssid, bssid, freq, ip, state, id."""
    values = {}
    for line in _wpa("status").split("\n"):
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    result = dict(values)
    if "id" in result:
        try:
            result["id"] = int(result["id"])
        except ValueError:
            pass
    if "freq" in result:
        try:
            result["freq"] = int(result["freq"])
        except ValueError:
            pass
    result["state"] = values.get("wpa_state")
    return result


def networks():
    """Сети в конфиге: id, ssid, bssid, flags, current."""
    items = []
    lines = _wpa("list_networks").split("\n")
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        flags = parts[3] if len(parts) > 3 else ""
        try:
            net_id = int(parts[0])
        except ValueError:
            continue
        items.append({
            "id": net_id,
            "ssid": parts[1],
            "bssid": parts[2] if len(parts) > 2 else "any",
            "flags": flags,
            "current": "CURRENT" in flags,
        })
    return items


def saved():
    """SSID сохранённых сетей."""
    return [item["ssid"] for item in networks()]


def scan_results():
    """Кэш сканирования: ssid, bssid, freq, signal, flags."""
    items = []
    lines = _wpa("scan_results").split("\n")
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        try:
            freq = int(parts[1])
            signal = int(parts[2])
        except ValueError:
            continue
        items.append({
            "bssid": parts[0],
            "freq": freq,
            "signal": signal,
            "flags": parts[3],
            "ssid": parts[4] if len(parts) > 4 else "",
        })
    return items


def scan(fresh=True, wait=3.0):
    """Запустить скан (рвёт связь на мгновение) и вернуть результаты."""
    if fresh:
        _ok("scan")
        if wait > 0:
            time.sleep(float(wait))
    return scan_results()


def add_network(ssid, psk=None, key_mgmt=None, scan_ssid=False):
    """Добавить сеть; вернуть её id. Конфиг на диск не пишется.

    `key_mgmt=None` — по паролю: с паролем `WPA-PSK`, без — `NONE`
    (открытая сеть). Допустимы `NONE`, `WPA-PSK` и `SAE` (WPA3).
    Для открытой сети пароль не записывается.

    `scan_ssid=True` — искать сеть по имени в probe-запросах: нужно
    для скрытых SSID, иначе `wpa_supplicant` её не найдёт.
    """
    if not ssid:
        raise HalError("пустой SSID")
    if key_mgmt is None:
        key_mgmt = "WPA-PSK" if psk else "NONE"
    key_mgmt = str(key_mgmt)
    if key_mgmt not in KEY_MGMT:
        raise HalError("неизвестный key_mgmt: {!r}".format(key_mgmt))
    text = _wpa("add_network").strip()
    try:
        net_id = int(text)
    except ValueError:
        raise HalError("wpa_cli add_network: {!r}".format(text[:60]))
    try:
        _ok("set_network", str(net_id), "ssid", _quote_value(ssid))
        if psk and key_mgmt != "NONE":
            _ok("set_network", str(net_id), "psk", _psk_value(psk))
        _ok("set_network", str(net_id), "key_mgmt", key_mgmt)
        if scan_ssid:
            _ok("set_network", str(net_id), "scan_ssid", "1")
    except Exception:
        try:
            _ok("remove_network", str(net_id))
        except HalError:
            pass
        raise
    return net_id


def _psk_value(psk):
    """PSK: 64 hex — как есть, иначе в кавычках."""
    text = str(psk)
    if len(text) == 64:
        try:
            int(text, 16)
            return text
        except ValueError:
            pass
    return _quote_value(text)


def set_network(net_id, **fields):
    """Изменить поля сети (ssid, psk, key_mgmt, scan_ssid)."""
    if not fields:
        raise HalError("нет полей для set_network")
    for key, value in fields.items():
        if key == "ssid":
            value = _quote_value(value)
        elif key == "psk":
            value = _psk_value(value)
        _ok("set_network", str(int(net_id)), key, str(value))
    return True


def select_network(net_id):
    """Выбрать сеть. Рвёт текущее соединение."""
    return _ok("select_network", str(int(net_id)))


def remove_network(net_id):
    """Удалить сеть из конфига в памяти."""
    return _ok("remove_network", str(int(net_id)))


def save_config():
    """Записать текущий конфиг на диск."""
    return _ok("save_config")


def reconnect():
    """Переподключиться. Рвёт текущее соединение."""
    return _ok("reconnect")


def disconnect():
    """Отключиться от сети. Рвёт текущее соединение."""
    return _ok("disconnect")


def wait_state(state="COMPLETED", timeout=25.0):
    """Ждать `wpa_state`; True, если дождались."""
    deadline = time.time() + float(timeout)
    while True:
        try:
            current = status().get("state")
        except HalError:
            current = None
        if current == state:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.5)


def ip_address(timeout=15.0):
    """IPv4-адрес интерфейса или None."""
    deadline = time.time() + float(timeout)
    while True:
        code, text = hal_common.capture(
            "{} -4 addr show {}".format(IP, IFACE))
        if code == 0:
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("inet "):
                    return line.split()[1].split("/")[0]
        if time.time() >= deadline:
            return None
        time.sleep(0.5)


def dhcp_renew():
    """Попросить dhcpcd перезапросить адрес."""
    code, text = hal_common.capture(
        "{} -n {}".format(DHCPCD, IFACE))
    if code != 0:
        raise HalError("dhcpcd -n: код {}: {}".format(
            code, text.strip()[:100]))
    return True
