"""Минимальный HTTP/1.1 POST поверх TLS.

Только то, что нужно движку: один запрос, ответ целиком. Без keep-alive,
редиректов и куки. Не трогает железо.
"""

import socket
import ssl

from micro_asr.errors import AsrError

DEFAULT_PORT = 443
DEFAULT_TIMEOUT = 15.0
MAX_RESPONSE = 4 * 1024 * 1024
USER_AGENT = "micro_asr/0.1"


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise AsrError("{} должен быть непустой строкой".format(name))
    return value


def _body(value):
    if value is None:
        return b""
    if not isinstance(value, (bytes, bytearray)):
        raise AsrError("тело запроса должно быть bytes")
    return bytes(value)


def _check_header(name, value):
    if not isinstance(name, str) or not name.strip():
        raise AsrError("неверное имя заголовка")
    text = str(value)
    if "\r" in text or "\n" in text or "\r" in name or "\n" in name:
        raise AsrError("неверный заголовок {}".format(name))
    return name, text


def build_request(host, path, body=b"", headers=None, port=None):
    """Собрать HTTP-запрос целиком."""
    host = _text(host, "host")
    path = _text(path, "path")
    if not path.startswith("/"):
        raise AsrError("path должен начинаться с /")
    body = _body(body)
    if port is None:
        target = host
    else:
        target = "{}:{}".format(host, int(port))
    lines = [
        "POST {} HTTP/1.1".format(path),
        "Host: {}".format(target),
        "Content-Length: {}".format(len(body)),
        "Connection: close",
        "User-Agent: {}".format(USER_AGENT),
    ]
    for name, value in (headers or {}).items():
        name, text = _check_header(name, value)
        lines.append("{}: {}".format(name, text))
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


def _parse_head(head):
    lines = head.split(b"\r\n")
    if not lines or not lines[0]:
        raise AsrError("HTTP: пустой ответ")
    parts = lines[0].split(b" ")
    if len(parts) < 2 or not parts[0].startswith(b"HTTP/"):
        raise AsrError("HTTP: неверная строка статуса")
    try:
        status = int(parts[1].decode())
    except (ValueError, AttributeError):
        raise AsrError("HTTP: неверный код статуса")
    headers = {}
    for line in lines[1:]:
        if not line:
            continue
        if b":" not in line:
            raise AsrError("HTTP: неверный заголовок")
        name, value = line.split(b":", 1)
        headers[name.strip().lower().decode()] = value.strip().decode()
    return status, headers


def _decode_chunks(data):
    body = bytearray()
    position = 0
    while True:
        end = data.find(b"\r\n", position)
        if end < 0:
            raise AsrError("HTTP: обрыв chunked-ответа")
        line = data[position:end].split(b";")[0].strip()
        try:
            size = int(line.decode(), 16)
        except ValueError:
            raise AsrError("HTTP: неверный размер чанка")
        position = end + 2
        if size == 0:
            return bytes(body)
        if position + size > len(data):
            raise AsrError("HTTP: обрыв чанка")
        body.extend(data[position:position + size])
        position += size + 2


def parse_response(data):
    """Разобрать полный HTTP-ответ: `(status, headers, body)`."""
    if not isinstance(data, (bytes, bytearray)):
        raise AsrError("HTTP: ответ должен быть bytes")
    head, separator, tail = bytes(data).partition(b"\r\n\r\n")
    if not separator:
        raise AsrError("HTTP: нет конца заголовков")
    status, headers = _parse_head(head)
    if headers.get("transfer-encoding", "").lower() == "chunked":
        body = _decode_chunks(tail)
    elif "content-length" in headers:
        try:
            length = int(headers["content-length"])
        except ValueError:
            raise AsrError("HTTP: неверный Content-Length")
        if len(tail) < length:
            raise AsrError("HTTP: короткий ответ")
        body = tail[:length]
    else:
        body = tail
    return status, headers, body


def _connect(host, port, timeout):
    try:
        infos = socket.getaddrinfo(host, port)
    except OSError as exc:
        raise AsrError("сеть: {}".format(exc))
    if not infos:
        raise AsrError("сеть: адрес {} не найден".format(host))
    chosen = infos[0]
    for info in infos:
        if info[0] == socket.AF_INET:
            chosen = info
            break
    try:
        sock = socket.socket(chosen[0], chosen[1], chosen[2])
    except OSError as exc:
        raise AsrError("сеть: {}".format(exc))
    try:
        sock.settimeout(timeout)
        sock.connect(chosen[4])
    except OSError as exc:
        try:
            sock.close()
        except Exception:
            pass
        raise AsrError("сеть: {}".format(exc))
    return sock


def _secure(sock, host):
    try:
        context = ssl.create_default_context()
        return context.wrap_socket(sock, server_hostname=host)
    except AttributeError:
        return ssl.wrap_socket(sock, server_hostname=host)


def _send_all(sock, data):
    sent = 0
    while sent < len(data):
        try:
            count = sock.send(data[sent:])
        except OSError as exc:
            raise AsrError("сеть: {}".format(exc))
        if not count:
            raise AsrError("сеть: соединение закрыто при отправке")
        sent += count


def _recv(sock):
    try:
        return sock.recv(4096)
    except OSError as exc:
        raise AsrError("сеть: {}".format(exc))


def _read_head(sock, limit):
    data = bytearray()
    while True:
        marker = data.find(b"\r\n\r\n")
        if marker >= 0:
            return bytes(data[:marker]), bytes(data[marker + 4:])
        if len(data) > limit:
            raise AsrError("HTTP: заголовки слишком большие")
        chunk = _recv(sock)
        if not chunk:
            raise AsrError("HTTP: соединение закрыто без ответа")
        data.extend(chunk)


def _read_exact(sock, data, length, limit):
    data = bytearray(data)
    if length > limit:
        raise AsrError("HTTP: ответ слишком большой")
    while len(data) < length:
        chunk = _recv(sock)
        if not chunk:
            raise AsrError("HTTP: короткий ответ")
        data.extend(chunk)
    return bytes(data[:length])


def _read_close(sock, data, limit):
    data = bytearray(data)
    while True:
        if len(data) > limit:
            raise AsrError("HTTP: ответ слишком большой")
        chunk = _recv(sock)
        if not chunk:
            return bytes(data)
        data.extend(chunk)


def post(host, path, body=b"", headers=None, timeout=DEFAULT_TIMEOUT,
         secure=True, port=None, limit=MAX_RESPONSE):
    """Выполнить POST; вернуть `(status, headers, body)`."""
    host = _text(host, "host")
    path = _text(path, "path")
    body = _body(body)
    if port is None:
        port = DEFAULT_PORT if secure else 80
    request = build_request(host, path, body, headers, port)
    sock = _connect(host, int(port), timeout)
    try:
        if secure:
            try:
                sock = _secure(sock, host)
            except AsrError:
                raise
            except Exception as exc:
                raise AsrError("TLS: {}".format(exc))
        _send_all(sock, request)
        head, rest = _read_head(sock, limit)
        status, reply = _parse_head(head)
        if reply.get("transfer-encoding", "").lower() == "chunked":
            inner = _read_close(sock, rest, limit)
            payload = _decode_chunks(inner)
        elif "content-length" in reply:
            try:
                length = int(reply["content-length"])
            except ValueError:
                raise AsrError("HTTP: неверный Content-Length")
            payload = _read_exact(sock, rest, length, limit)
        else:
            payload = _read_close(sock, rest, limit)
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return status, reply, payload
