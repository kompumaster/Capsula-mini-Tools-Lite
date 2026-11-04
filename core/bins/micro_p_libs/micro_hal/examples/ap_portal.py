#!/usr/bin/env python3
"""Точка доступа Wi-Fi: страница настройки (captive portal).

Запуск на колонке, когда уже подняты `hostapd` на `p2p0` и `dnsmasq`
на `10.0.0.1`:

    /home/microp/mp /home/microp/micro_hal/examples/ap_portal.py

Телефон подключается к `Capsula-AP`, любой адрес ведёт на
`http://10.0.0.1/`: там текущий статус, список видимых сетей с
выбором, поле пароля и кнопка «Подключиться».

При отправке формы вызывается `lib_wifi.connect()`; AP при этом
остаётся, чтобы страница с результатом дошла. Если подключиться не
удалось — AP уже на месте, телефон видит ошибку. Если удалось —
страница предлагает выключить точку доступа.
"""

import socket
import struct
import sys
import time

from micro_hal import hal_common, lib_wifi

HOST = "0.0.0.0"
PORT = 80
AP_IFACE = "p2p0"
AP_IP = "10.0.0.1"
HOSTAPD = "/usr/bin/hostapd"
DNSMASQ = "/usr/bin/dnsmasq"
HOSTAPD_PID = "/tmp/hostapd.pid"
DNSMASQ_PID = "/tmp/dnsmasq-ap.pid"
HOSTAPD_CONF = "/tmp/hostapd.conf"
DNSMASQ_CONF = "/tmp/dnsmasq-ap.conf"

HOSTAPD_TEMPLATE = """interface={iface}
driver=nl80211
ssid=Capsula-AP
hw_mode=g
channel=6
auth_algs=1
wpa=0
"""

DNSMASQ_TEMPLATE = """interface={iface}
listen-address={ip}
bind-interfaces
except-interface=lo
no-dhcp-interface=lo
dhcp-range=10.0.0.10,10.0.0.50,12h
dhcp-option=3,{ip}
dhcp-option=6,{ip}
address=/#/{ip}
no-resolv
no-hosts
log-facility=/home/microp/dnsmasq-ap.log
"""

SERVER = None
# /stopap: сначала отдать страницу, погасить AP — после отправки.
STOP_AFTER = False
STOP_DELAY = 0.5


def _open_server():
    """Слушающий сокет портала."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,
                      struct.pack("i", 1))
    server.bind(socket.getaddrinfo(HOST, PORT)[0][-1])
    server.listen(1)
    return server


def _process(pid, marker):
    """Живой процесс с `marker` в cmdline (защита от переиспользования PID)."""
    if not hal_common.exists("/proc/{}".format(pid)):
        return False
    try:
        cmdline = hal_common.read_text(
            "/proc/{}/cmdline".format(pid)).replace("\x00", " ")
    except OSError:
        return False
    return marker in cmdline


def _kill_pid(path, marker):
    pid = _pid_alive(path, marker)
    if pid is None:
        return False
    try:
        hal_common.run("kill {}".format(pid))
    except Exception:
        return False
    return True


def _pid_alive(path, marker):
    """PID из файла, если это действительно наш процесс, иначе None."""
    try:
        pid = int(hal_common.read_text(path).strip())
    except (OSError, ValueError):
        return None
    return pid if _process(pid, marker) else None


def _has_address():
    code, text = hal_common.capture(
        "ip -4 addr show {}".format(AP_IFACE))
    return code == 0 and (AP_IP + "/") in text


def _ap_running():
    """Живы ли hostapd и dnsmasq и стоит ли адрес."""
    return (_pid_alive(HOSTAPD_PID, "hostapd") is not None
            and _pid_alive(DNSMASQ_PID, "dnsmasq") is not None
            and _has_address())


def _run(label, command, problems):
    """Выполнить команду; ошибка или код ≠ 0 — в список проблем."""
    try:
        code = hal_common.run(command)
    except Exception as exc:
        problems.append("{}: {}".format(label, exc))
        return -1
    if code != 0:
        problems.append("{} (код {})".format(label, code))
    return code


def stop_ap():
    """Погасить AP и DHCP; вернуть текст проблем или ""."""
    _kill_pid(HOSTAPD_PID, "hostapd")
    _kill_pid(DNSMASQ_PID, "dnsmasq")
    problems = []
    _run("flush", "ip addr flush dev {}".format(AP_IFACE), problems)
    _run("down", "ip link set {} down".format(AP_IFACE), problems)
    return "; ".join(problems)


def _ensure_ap():
    """Проверить AP и при необходимости поднять; не бросает."""
    try:
        if _ap_running():
            return ""
        return start_ap()
    except Exception as exc:
        return "AP: {}".format(exc)


def start_ap():
    """Поднять AP и DHCP заново; вернуть "" или текст ошибок.

    Слушающий сокет закрываем на время запуска: иначе hostapd
    унаследует его и будет держать порт 80, даже когда портал умрёт.
    """
    global SERVER
    if SERVER is not None:
        try:
            SERVER.close()
        except OSError:
            pass
        SERVER = None
    try:
        hal_common.write_text(HOSTAPD_CONF,
                              HOSTAPD_TEMPLATE.format(iface=AP_IFACE))
        hal_common.write_text(DNSMASQ_CONF,
                              DNSMASQ_TEMPLATE.format(iface=AP_IFACE,
                                                      ip=AP_IP))
    except OSError as exc:
        return "не записать конфиг: {}".format(exc)

    problems = []
    if _pid_alive(HOSTAPD_PID, "hostapd") is None:
        _run("hostapd", "{} -B -P {} {}".format(
            HOSTAPD, HOSTAPD_PID, HOSTAPD_CONF), problems)
    if not _has_address():
        _run("адрес", "ip addr add {}/24 dev {}".format(
            AP_IP, AP_IFACE), problems)
    _run("link", "ip link set {} up".format(AP_IFACE), problems)
    if _pid_alive(DNSMASQ_PID, "dnsmasq") is None:
        _run("dnsmasq", "{} -C {} -x {}".format(
            DNSMASQ, DNSMASQ_CONF, DNSMASQ_PID), problems)
    try:
        SERVER = _open_server()
    except OSError as exc:
        problems.append("портал (порт {}): {}".format(PORT, exc))
    if not _ap_running():
        problems.append("AP не отвечает")
    return "; ".join(problems)


def _unquote(text):
    text = text.replace("+", " ")
    out = bytearray()
    index = 0
    while index < len(text):
        char = text[index]
        if char == "%" and index + 2 < len(text):
            try:
                out.append(int(text[index + 1:index + 3], 16))
                index += 3
                continue
            except ValueError:
                pass
        out.extend(char.encode())
        index += 1
    return out.decode("utf-8", "replace")


def _form(body):
    values = {}
    for pair in body.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            values[_unquote(key)] = _unquote(value)
    return values


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _network_rows(networks, selected):
    rows = []
    for item in networks:
        ssid = item.get("ssid") or ""
        if not ssid:
            continue
        mark = " 🔒" if "PSK" in item.get("flags", "") else ""
        checked = " checked" if ssid == selected else ""
        rows.append(
            '<label class="net"><input type="radio" name="ssid" '
            'value="{value}"{checked}><span>{name}</span>'
            '<small>{signal} дБм{mark}</small></label>'.format(
                value=_esc(ssid), checked=checked, name=_esc(ssid),
                signal=item.get("signal", 0), mark=mark))
    return "".join(rows) or '<small>список пуст — нажмите «Обновить»</small>'


def page(message="", selected=""):
    state = lib_wifi.status()
    saved = ", ".join(lib_wifi.saved()) or "нет"
    networks = lib_wifi.scan()
    return """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Capsula Mini</title>
<style>
body{{font-family:sans-serif;margin:0;padding:24px;background:#f5f5f7}}
h1{{font-size:22px}} .card{{background:#fff;border-radius:12px;
padding:16px;margin-bottom:16px}}
input[type=text],input[type=password]{{width:100%;padding:10px;
margin:6px 0;box-sizing:border-box}}
button{{width:100%;padding:12px;border:0;border-radius:8px;
background:#2b6cb0;color:#fff;font-size:16px}}
.net{{display:flex;align-items:center;gap:8px;padding:8px 0;
border-bottom:1px solid #eee}}
.net span{{flex:1}} .net small{{color:#666}}
.msg{{color:#b00020}} .ok{{color:#1b5e20}}
a{{color:#2b6cb0}} small{{color:#666}}
</style></head><body>
<h1>Capsula Mini</h1>
<div class="card"><b>Сейчас:</b> {ssid} ({state})<br>
<small>адрес: {ip}</small><br>
<small>сохранённые: {saved}</small></div>
<div class="card">{message}</div>
<form method="post" action="/connect">
<div class="card"><b>Сети в эфире</b>
<div class="nets">{networks}</div>
<small><a href="/scan">Обновить список</a> — связь на пару секунд
может прерваться</small>
<input type="text" name="ssid_manual"
 placeholder="или введите имя сети вручную">
</div>
<div class="card"><b>Пароль</b>
<input type="password" name="psk" placeholder="пароль сети">
<button type="submit">Подключиться</button>
<small>Если не получится, точка доступа останется.</small>
</div>
</form>
</body></html>""".format(ssid=_esc(state["ssid"] or "—"),
                         state=_esc(state["state"] or "—"),
                         ip=_esc(state["ip"] or "—"), saved=_esc(saved),
                         networks=_network_rows(networks, selected),
                         message=message)


def _response(body, status="200 OK", location=None):
    data = body.encode("utf-8")
    head = ("HTTP/1.1 {}\r\nContent-Type: text/html; charset=utf-8\r\n"
            "Content-Length: {}\r\nConnection: close\r\n").format(
                status, len(data))
    if location:
        head += "Location: {}\r\n".format(location)
    return head.encode("utf-8") + b"\r\n" + data


def _redirect(location):
    return _response("", "303 See Other", location)


def handle(request):
    global STOP_AFTER

    lines = request.split("\r\n")
    if not lines:
        return _response(page(), "400 Bad Request")
    parts = lines[0].split()
    if len(parts) < 2:
        return _response(page(), "400 Bad Request")
    method, path = parts[0], parts[1]

    if method == "GET" and path == "/scan":
        lib_wifi.scan(fresh=True, wait=5.0)
        return _redirect("/")

    if method == "GET" and path == "/stopap":
        # Сначала ответ: после снятия 10.0.0.1 это соединение оборвётся.
        answer = _response(page(
            '<span class="ok">Точка доступа выключается…</span> '
            'Если страница не обновилась — это нормально.'))
        STOP_AFTER = True
        return answer

    if method == "POST" and path == "/connect":
        body = request.split("\r\n\r\n", 1)[-1]
        values = _form(body)
        manual = (values.get("ssid_manual") or "").strip()
        chosen = (values.get("ssid") or "").strip()
        ssid = manual or chosen
        psk = (values.get("psk") or "").strip()
        if not ssid:
            return _response(page(
                '<span class="msg">Выберите сеть или введите SSID.</span>'))
        try:
            result = lib_wifi.connect(ssid, psk or None, hidden=True,
                                      allow_no_rollback=True,
                                      timeout=60)
        except Exception as exc:
            note = _ensure_ap()
            message = '<span class="msg">Не вышло: {}.</span>'.format(
                _esc(str(exc)[:120]))
            if note:
                message += ' <span class="msg">AP: {}.</span>'.format(
                    _esc(note))
            return _response(page(message, ssid))
        note = _ensure_ap()
        message = ('<span class="ok">Подключено: {} ({}).</span> Точку '
                   'доступа можно <a href="/stopap">выключить</a>.'.format(
                       _esc(result["ssid"]), _esc(result["ip"] or "—")))
        if note:
            message += ' <span class="msg">AP: {}.</span>'.format(
                _esc(note))
        return _response(page(message, ssid))

    return _response(page())


def main():
    global SERVER, STOP_AFTER
    # Скан до первого запроса: список сетей готов сразу.
    try:
        print("сетей найдено:", len(lib_wifi.scan(fresh=True, wait=5.0)))
    except Exception as exc:
        print("скан:", type(exc).__name__, str(exc)[:60])
    sys.stdout.flush()
    SERVER = _open_server()
    print("портал: http://{}:{}/".format(AP_IP, PORT))
    sys.stdout.flush()
    try:
        while True:
            client, _addr = SERVER.accept()
            try:
                # Телефон может открыть соединение и молчать: без
                # таймаута сервер застревает в recv.
                client.settimeout(2.0)
                data = client.recv(4096)
                if b"\r\n\r\n" not in data:
                    data += client.recv(4096)
                request = data.decode("utf-8", "replace")
                if "Content-Length:" in request:
                    length = int(request.split("Content-Length:")[1]
                                 .split("\r\n")[0].strip())
                    body = request.split("\r\n\r\n", 1)[-1]
                    while len(body) < length:
                        chunk = client.recv(1024)
                        if not chunk:
                            break
                        body += chunk.decode("utf-8", "replace")
                    request = request.split("\r\n\r\n", 1)[0] + \
                        "\r\n\r\n" + body
                client.send(handle(request))
            except Exception as exc:
                print("клиент:", type(exc).__name__, str(exc)[:80])
            finally:
                try:
                    client.close()
                except OSError:
                    pass
            if STOP_AFTER:
                # Дать ответу уйти, потом гасить AP.
                STOP_AFTER = False
                print("выключаю AP")
                sys.stdout.flush()
                time.sleep(STOP_DELAY)
                problem = stop_ap()
                if problem:
                    print("stopap:", problem)
    finally:
        if SERVER is not None:
            SERVER.close()


if __name__ == "__main__":
    main()
