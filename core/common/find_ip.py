"""Поиск колонки в локальной сети.

Порядок:

1. mDNS: сервисы `_spotify-connect._tcp` и `_http._tcp`, отбираем
   instance/SRV-хост с префиксом `Capsula-mini`;
2. скан локальных IPv4-подсетей: `GET /info`, у колонки в `device_id`
   есть `capsula_mini`.

`find_capsula()` вызывается без параметров и возвращает IPv4-адрес
или `None`. Сеть опрашивается только чтением.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

NAME_PREFIX = "capsula-mini"
MARKER = "capsula_mini"

MDNS_TIMEOUT = 2.0       # окно ожидания mDNS
SCAN_TIMEOUT = 0.45      # таймаут одного /info
WORKERS = 64             # параллельных проверок при скане
MAX_HOSTS = 1024         # предел сканируемых адресов

SERVICES = (
    "_spotify-connect._tcp.local.",
    "_http._tcp.local.",
)

# Куда «подключаемся» UDP-сокетом, чтобы узнать свой адрес.
# Пакеты не отправляются, нужен только маршрут по умолчанию.
ROUTE_TARGETS = ("192.168.1.1", "8.8.8.8", "1.1.1.1")


def _log(log, message: str) -> None:
    if log is not None:
        log(message)


def _matches(name: str) -> bool:
    """Имя сервиса или хоста принадлежит колонке."""
    return name.rstrip(".").lower().startswith(NAME_PREFIX)


def _is_capsula_info(data) -> bool:
    """В `/info` есть признак колонки."""
    if not isinstance(data, dict):
        return False
    return MARKER in str(data.get("device_id", "")).lower()


def _ipv4_from_addresses(info) -> str | None:
    """Первый IPv4 из ServiceInfo, IPv6 пропускаем."""
    try:
        addresses = list(info.parsed_addresses())
    except Exception:
        addresses = []
    if not addresses:
        for raw in getattr(info, "addresses", None) or []:
            if isinstance(raw, bytes) and len(raw) == 4:
                addresses.append(socket.inet_ntoa(raw))
    for address in addresses:
        try:
            ipaddress.IPv4Address(address)
        except ValueError:
            continue
        return address
    return None


def _find_mdns(log=None) -> str | None:
    """Ищет колонку по mDNS; без zeroconf просто пропускает шаг."""
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError:
        _log(log, "zeroconf не установлен: mDNS пропущен")
        return None

    found: list[str] = []
    lock = threading.Lock()

    class Listener:
        def add_service(self, zc, service_type, name):
            if not _matches(name):
                return
            info = zc.get_service_info(service_type, name, timeout=1000)
            if info is None:
                return
            server = getattr(info, "server", "") or ""
            if not (_matches(name) or _matches(server)):
                return
            ip = _ipv4_from_addresses(info)
            if ip:
                with lock:
                    found.append(ip)

        def update_service(self, *args):
            pass

        def remove_service(self, *args):
            pass

    zeroconf = None
    browsers = []
    try:
        try:
            zeroconf = Zeroconf()
        except OSError as exc:
            _log(log, f"mDNS не поднялся: {exc}")
            return None
        for service in SERVICES:
            browsers.append(ServiceBrowser(zeroconf, service, Listener()))
        deadline = time.monotonic() + MDNS_TIMEOUT
        while time.monotonic() < deadline:
            with lock:
                if found:
                    return found[0]
            time.sleep(0.05)
    finally:
        for browser in browsers:
            browser.cancel()
        if zeroconf is not None:
            zeroconf.close()
    return None


def _network_for(ip: str, prefix: int):
    """IPv4-сеть интерфейса; слишком широкую сужаем до /24."""
    try:
        interface = ipaddress.IPv4Interface(f"{ip}/{prefix}")
    except ValueError:
        return None
    network = interface.network
    if network.is_loopback or network.is_link_local:
        return None
    if network.prefixlen < 22:
        network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
    return network


def _fallback_ipv4() -> str | None:
    """Свой IPv4, если ifaddr недоступен."""
    for target in ROUTE_TARGETS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target, 80))
                ip = sock.getsockname()[0]
        except OSError:
            continue
        if ip and ip != "0.0.0.0" and not ip.startswith("127."):
            return ip
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        return None
    if ip and ip != "0.0.0.0" and not ip.startswith("127."):
        return ip
    return None


def _local_networks() -> list:
    """Локальные IPv4-подсети без loopback и link-local."""
    networks = []
    try:
        import ifaddr
        adapters = ifaddr.get_adapters()
    except (ImportError, OSError):
        adapters = []
    for adapter in adapters:
        for address in adapter.ips:
            if not isinstance(address.ip, str):
                continue
            network = _network_for(address.ip, address.network_prefix)
            if network is not None:
                networks.append(network)
    if not networks:
        fallback = _fallback_ipv4()
        if fallback:
            network = _network_for(fallback, 24)
            if network is not None:
                networks.append(network)

    unique = []
    seen = set()
    for network in networks:
        if network in seen:
            continue
        seen.add(network)
        unique.append(network)
    unique.sort(key=lambda net: (int(net.network_address), net.prefixlen))
    return unique


def _hosts(networks) -> list[str]:
    """Адреса для скана, не больше MAX_HOSTS."""
    hosts = []
    for network in networks:
        for host in network.hosts():
            hosts.append(str(host))
            if len(hosts) >= MAX_HOSTS:
                return hosts
    return hosts


def _probe(host: str) -> str | None:
    """Проверяет один адрес через `/info`."""
    connection = None
    try:
        connection = http.client.HTTPConnection(
            host, 80, timeout=SCAN_TIMEOUT)
        connection.request("GET", "/info")
        response = connection.getresponse()
        if response.status != 200:
            return None
        body = response.read(65536)
        data = json.loads(body.decode("utf-8", "replace"))
        return host if _is_capsula_info(data) else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        if connection is not None:
            connection.close()


def _find_scan(log=None) -> str | None:
    """Сканирует локальные подсети и ищет `/info` колонки."""
    networks = _local_networks()
    hosts = _hosts(networks)
    if not hosts:
        _log(log, "не найдено локальных IPv4-подсетей")
        return None
    _log(log, f"скан {len(hosts)} адресов ...")
    executor = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        futures = [executor.submit(_probe, host) for host in hosts]
        for future in as_completed(futures):
            result = future.result()
            if result:
                return result
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return None


def _discover(log=None) -> str | None:
    try:
        ip = _find_mdns(log)
    except Exception as exc:  # mDNS не должен мешать скану
        _log(log, f"mDNS не удался: {exc}")
        ip = None
    if ip is not None:
        _log(log, f"найдена по mDNS: {ip}")
        return ip
    ip = _find_scan(log)
    if ip is not None:
        _log(log, f"найдена сканом: {ip}")
    return ip


def find_capsula() -> str | None:
    """Ищет колонку в локальной сети. Возвращает IPv4 или None.

    Параметров нет: сначала mDNS, затем скан локальных подсетей.
    """
    return _discover()


def main() -> int:
    """Ручной запуск: IP в stdout, ход поиска в stderr."""
    def log(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    ip = _discover(log)
    if ip is None:
        print("error: колонка не найдена", file=sys.stderr)
        return 1
    print(ip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
