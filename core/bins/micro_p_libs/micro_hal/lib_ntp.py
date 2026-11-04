"""NTP: запрос времени по SNTP и установка системных часов.

Сеть — чистый MicroPython: `socket`, `struct`, `time`. Отдельного
`hal_ntp` нет. По умолчанию сначала московские серверы; если пинг
больше порога, список перебирается дальше (регионы, `pool.ntp.org`).

Установка времени — `date -u -s` (BusyBox): в MicroPython `ffi` нет
`new`, поэтому собрать `struct timeval` для `settimeofday` нельзя.
Точность установки — секунда; для часов на дисплее этого достаточно.
"""

import os
import socket
import struct
import time

from micro_hal import hal_common
from micro_hal.hal_common import HalError

__all__ = [
    "NTP_PORT", "NTP_EPOCH", "TIMEOUT", "MAX_DELAY",
    "MOSCOW", "REGIONAL", "DEFAULT",
    "LOCALTIME", "ZONEINFO", "TIMEZONE_FILE",
    "query", "scan", "fastest", "sync", "set_time",
    "get_timezone", "set_timezone", "cached", "forget",
]

NTP_PORT = 123
NTP_EPOCH = 2208988800          # секунды 1900 → 1970
TIMEOUT = 2.0                   # секунд на один сервер
MAX_DELAY = 0.15                # 150 мс: выше — считаем «большим пингом»

LOCALTIME = "/etc/localtime"
ZONEINFO = "/usr/share/zoneinfo"
TIMEZONE_FILE = "/etc/timezone"

# Москва: госэталон ВНИИФТРИ, MSK-IX, российский пул.
MOSCOW = (
    "ntp1.vniiftri.ru",
    "ntp2.vniiftri.ru",
    "ntp3.vniiftri.ru",
    "ntp4.vniiftri.ru",
    "ntp.msk-ix.ru",
    "0.ru.pool.ntp.org",
    "1.ru.pool.ntp.org",
    "2.ru.pool.ntp.org",
    "3.ru.pool.ntp.org",
)

# Региональные серверы ВНИИФТРИ — если Москва далеко.
REGIONAL = (
    "ntp1.niiftri.irkutsk.ru",
    "ntp2.niiftri.irkutsk.ru",
    "vniiftri2.khv.ru",
)

DEFAULT = MOSCOW + REGIONAL + ("pool.ntp.org",)

# Лучший сервер за сессию (в памяти процесса, без записи на диск).
_cached = None


def _build_request(now):
    """Пакет 48 байт и его transmit timestamp (8 байт)."""
    seconds = int(now) + NTP_EPOCH
    fraction = int((now - int(now)) * 4294967296.0) & 0xFFFFFFFF
    packet = b"\x1b" + b"\x00" * 39 + struct.pack(
        "!II", seconds & 0xFFFFFFFF, fraction)
    return packet, packet[40:48]


def _timestamp(chunk):
    """NTP-метка (8 байт) → секунды Unix с дробной частью."""
    seconds, fraction = struct.unpack("!II", chunk)
    if seconds == 0 and fraction == 0:
        raise HalError("NTP: нулевая метка времени")
    value = seconds - NTP_EPOCH
    if value < 0:               # после 2036 года метка переполнилась
        value += 4294967296
    return value + fraction / 4294967296.0


def _parse_response(data, request, t1, t4):
    """Проверить ответ сервера и посчитать offset/delay."""
    if len(data) < 48:
        raise HalError("NTP: короткий ответ ({} байт)".format(len(data)))
    mode = data[0] & 0x07
    if mode != 4:
        raise HalError("NTP: mode {}, ожидается 4".format(mode))
    leap = (data[0] >> 6) & 0x03
    if leap == 3:
        raise HalError("NTP: сервер не синхронизирован")
    stratum = data[1]
    if stratum == 0:
        raise HalError("NTP: kiss-o'-death (stratum 0)")
    if stratum > 15:
        raise HalError("NTP: неверный stratum {}".format(stratum))
    if bytes(data[24:32]) != request[40:48]:
        raise HalError("NTP: ответ не на наш запрос")

    t2 = _timestamp(data[32:40])
    t3 = _timestamp(data[40:48])
    return {
        "offset": ((t2 - t1) + (t3 - t4)) / 2.0,
        "delay": (t4 - t1) - (t3 - t2),
        "stratum": stratum,
        "leap": leap,
    }


def _sockaddr_ip(family, address):
    """IP из адреса `getaddrinfo`: tuple (CPython) или bytes (MicroPython)."""
    if isinstance(address, (bytes, bytearray)):
        if family == socket.AF_INET and len(address) >= 8:
            return ".".join(str(address[index]) for index in range(4, 8))
        return ""
    return address[0]


def _resolve(server):
    """Адрес сервера и семейство; IPv4 в приоритете."""
    try:
        infos = socket.getaddrinfo(server, NTP_PORT)
    except OSError as exc:
        raise HalError("NTP: не разрешить {}: {}".format(server, exc))
    if not infos:
        raise HalError("NTP: не разрешить {}".format(server))
    chosen = infos[0]
    for info in infos:
        if info[0] == socket.AF_INET:
            chosen = info
            break
    return chosen[0], chosen[4]


def _query_one(server, timeout):
    """Один NTP-запрос; вернуть offset/delay или бросить HalError."""
    family, address = _resolve(server)
    t1 = time.time()
    request, transmit = _build_request(t1)
    sock = socket.socket(family, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        sock.connect(address)
        sock.send(request)
        data = sock.recv(1024)
        t4 = time.time()
    except OSError as exc:
        raise HalError("NTP {}: {}".format(server, exc))
    finally:
        sock.close()

    result = _parse_response(data, request, t1, t4)
    result["server"] = server
    result["ip"] = _sockaddr_ip(family, address)
    return result


def _select(servers, timeout, max_delay, remember=False):
    """Перебрать серверы: первый с delay ≤ порога, иначе лучший."""
    errors = []
    tried = []
    best = None
    for server in servers:
        tried.append(server)
        try:
            result = _query_one(server, timeout)
        except HalError as exc:
            errors.append((server, str(exc)))
            if server == _cached:
                forget()
            continue
        if best is None or result["delay"] < best["delay"]:
            best = result
        if result["delay"] <= max_delay:
            result["tried"] = tried
            if remember:
                _remember(server)
            return result
    if best is not None:
        best["tried"] = tried
        if remember:
            _remember(best["server"])
        return best
    details = "; ".join(
        "{}: {}".format(server, text) for server, text in errors)
    raise HalError("NTP: нет ответа ни от одного сервера: " + details)


def cached():
    """Сервер, запомненный как лучший в этой сессии, или None."""
    return _cached


def forget():
    """Забыть запомненный сервер."""
    global _cached
    _cached = None


def _remember(server):
    global _cached
    _cached = server


def _default_servers():
    """Список по умолчанию; запомненный сервер — первым."""
    if _cached is None:
        return DEFAULT
    return (_cached,) + tuple(
        name for name in DEFAULT if name != _cached)


def _pick_servers(server, servers):
    """Явный сервер или список; без обоих — встроенный список."""
    if server is not None:
        if servers is not None:
            raise HalError("NTP: укажите что-то одно — server или servers")
        return (server,)
    if servers is None:
        return _default_servers()
    if isinstance(servers, str):
        servers = (servers,)
    servers = tuple(servers)
    if not servers:
        raise HalError("NTP: пустой список серверов")
    return servers


def query(server=None, servers=None, timeout=TIMEOUT, max_delay=MAX_DELAY):
    """Спросить время; вернуть offset, delay, stratum и кто ответил.

    `server` — только этот сервер, без перебора; `servers` — список
    для перебора; ничего не указано — встроенный список, а первым
    пробуется сервер, запомненный как лучший.
    """
    servers = _pick_servers(server, servers)
    timeout = float(timeout)
    if timeout <= 0:
        raise HalError("NTP: timeout должен быть больше нуля")
    max_delay = max(0.0, float(max_delay))
    return _select(servers, timeout, max_delay, remember=server is None)


def scan(servers=None, timeout=TIMEOUT):
    """Проверить все серверы и вернуть список, быстрые первыми.

    Каждый элемент: `server`, `ok`, а для ответивших — `ip`, `offset`,
    `delay`, `stratum`, `leap`; для остальных — `error`. Исключения
    не бросает, кроме пустого списка и неверного timeout. Лучший
    сервер запоминается на сессию.
    """
    servers = _pick_servers(None, servers)
    timeout = float(timeout)
    if timeout <= 0:
        raise HalError("NTP: timeout должен быть больше нуля")
    good = []
    bad = []
    for current in servers:
        try:
            result = _query_one(current, timeout)
        except HalError as exc:
            bad.append({
                "server": current,
                "ok": False,
                "error": str(exc),
            })
            continue
        result["ok"] = True
        good.append(result)
    good.sort(key=lambda item: item["delay"])
    if good:
        _remember(good[0]["server"])
    return good + bad


def fastest(servers=None, timeout=TIMEOUT):
    """Лучший сервер по `delay` или HalError, если никто не ответил."""
    results = scan(servers, timeout)
    for result in results:
        if result["ok"]:
            return result
    details = "; ".join(
        "{}: {}".format(item["server"], item["error"])
        for item in results)
    raise HalError("NTP: нет ответа ни от одного сервера: " + details)


def set_time(timestamp):
    """Поставить системное время в UTC через `date -u -s` (нужен root)."""
    hal_common.require_root()
    moment = time.gmtime(timestamp)
    text = "%04d-%02d-%02d %02d:%02d:%02d" % (
        moment[0], moment[1], moment[2],
        moment[3], moment[4], moment[5])
    code = hal_common.run(
        "date -u -s '{}' >/dev/null 2>&1".format(text))
    if code != 0:
        raise HalError(
            "NTP: не установить время (date -u -s), код {}".format(code))


def get_timezone():
    """Текущий пояс: из `/etc/timezone` или из ссылки `/etc/localtime`."""
    try:
        text = hal_common.read_text(TIMEZONE_FILE).strip()
    except OSError:
        text = ""
    if text:
        return text
    try:
        target = os.readlink(LOCALTIME)
    except (OSError, AttributeError):
        return ""
    marker = "/zoneinfo/"
    if marker in target:
        return target.split(marker, 1)[1]
    return ""


def _zone_path(zone):
    """Проверить имя пояса и вернуть путь в zoneinfo или HalError."""
    zone = zone.strip()
    if not zone or zone.startswith("/") or ".." in zone:
        raise HalError("NTP: неверный часовой пояс {!r}".format(zone))
    allowed = ("abcdefghijklmnopqrstuvwxyz"
               "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "0123456789/_-+.")
    for char in zone:
        if char not in allowed:
            raise HalError("NTP: неверный часовой пояс {!r}".format(zone))
    path = ZONEINFO + "/" + zone
    if not hal_common.exists(path):
        raise HalError("NTP: нет часового пояса {}".format(zone))
    return path


def set_timezone(zone):
    """Сменить системный пояс: `/etc/localtime` и `/etc/timezone` (root).

    Уже запущенные процессы могут держать старый TZ в кэше libc;
    им нужен перезапуск (в MicroPython нет `time.tzset`).
    """
    hal_common.require_root()
    zone = zone.strip()
    path = _zone_path(zone)
    code = hal_common.run(
        "ln -sf '{}' '{}'".format(path, LOCALTIME))
    if code != 0:
        raise HalError(
            "NTP: не переключить пояс {}, код {}".format(zone, code))
    try:
        hal_common.write_text(TIMEZONE_FILE, zone + "\n")
    except OSError as exc:
        raise HalError(
            "NTP: не записать {}: {}".format(TIMEZONE_FILE, exc))
    return zone


def sync(server=None, servers=None, timeout=TIMEOUT, max_delay=MAX_DELAY):
    """Спросить время и установить его; вернуть offset до установки.

    `server` — явный сервер, `servers` — список для перебора,
    ничего не указано — встроенный список.
    """
    result = query(server, servers, timeout, max_delay)
    set_time(time.time() + result["offset"])
    return result["offset"]
