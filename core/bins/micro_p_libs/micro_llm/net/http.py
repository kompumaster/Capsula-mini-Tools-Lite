"""Минимальный HTTP/1.1 POST поверх TLS.

Два режима:

- `post(...)` - ответ целиком (обычный JSON);
- `start(...)` - заголовки, затем `Response.read()` кусками: нужно для
  потокового ответа (SSE) без буферизации всего тела.

Без keep-alive, редиректов и куки. Не трогает железо.
"""

import socket
import ssl

from micro_llm.errors import LlmError

DEFAULT_PORT = 443
DEFAULT_TIMEOUT = 15.0
MAX_RESPONSE = 4 * 1024 * 1024
USER_AGENT = "micro_llm/0.1"
READ_CHUNK = 4096


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise LlmError("{} должен быть непустой строкой".format(name))
    return value


def _body(value):
    if value is None:
        return b""
    if not isinstance(value, (bytes, bytearray)):
        raise LlmError("тело запроса должно быть bytes")
    return bytes(value)


def _check_header(name, value):
    if not isinstance(name, str) or not name.strip():
        raise LlmError("неверное имя заголовка")
    text = str(value)
    if "\r" in text or "\n" in text or "\r" in name or "\n" in name:
        raise LlmError("неверный заголовок {}".format(name))
    return name, text


def build_request(host, path, body=b"", headers=None, port=None):
    """Собрать HTTP-запрос целиком."""
    host = _text(host, "host")
    path = _text(path, "path")
    if not path.startswith("/"):
        raise LlmError("path должен начинаться с /")
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
        raise LlmError("HTTP: пустой ответ")
    parts = lines[0].split(b" ")
    if len(parts) < 2 or not parts[0].startswith(b"HTTP/"):
        raise LlmError("HTTP: неверная строка статуса")
    try:
        status = int(parts[1].decode())
    except (ValueError, AttributeError):
        raise LlmError("HTTP: неверный код статуса")
    headers = {}
    for line in lines[1:]:
        if not line:
            continue
        if b":" not in line:
            raise LlmError("HTTP: неверный заголовок")
        name, value = line.split(b":", 1)
        headers[name.strip().lower().decode()] = value.strip().decode()
    return status, headers


def _decode_chunks(data):
    body = bytearray()
    position = 0
    while True:
        end = data.find(b"\r\n", position)
        if end < 0:
            raise LlmError("HTTP: обрыв chunked-ответа")
        line = data[position:end].split(b";")[0].strip()
        try:
            size = int(line.decode(), 16)
        except ValueError:
            raise LlmError("HTTP: неверный размер чанка")
        position = end + 2
        if size == 0:
            return bytes(body)
        if position + size > len(data):
            raise LlmError("HTTP: обрыв чанка")
        body.extend(data[position:position + size])
        position += size + 2


def parse_response(data):
    """Разобрать полный HTTP-ответ: `(status, headers, body)`."""
    if not isinstance(data, (bytes, bytearray)):
        raise LlmError("HTTP: ответ должен быть bytes")
    head, separator, tail = bytes(data).partition(b"\r\n\r\n")
    if not separator:
        raise LlmError("HTTP: нет конца заголовков")
    status, headers = _parse_head(head)
    if headers.get("transfer-encoding", "").lower() == "chunked":
        body = _decode_chunks(tail)
    elif "content-length" in headers:
        try:
            length = int(headers["content-length"])
        except ValueError:
            raise LlmError("HTTP: неверный Content-Length")
        if len(tail) < length:
            raise LlmError("HTTP: короткий ответ")
        body = tail[:length]
    else:
        body = tail
    return status, headers, body


def _connect(host, port, timeout):
    try:
        infos = socket.getaddrinfo(host, port)
    except OSError as exc:
        raise LlmError("сеть: {}".format(exc))
    if not infos:
        raise LlmError("сеть: адрес {} не найден".format(host))
    chosen = infos[0]
    for info in infos:
        if info[0] == socket.AF_INET:
            chosen = info
            break
    try:
        sock = socket.socket(chosen[0], chosen[1], chosen[2])
    except OSError as exc:
        raise LlmError("сеть: {}".format(exc))
    try:
        sock.settimeout(timeout)
        sock.connect(chosen[4])
    except OSError as exc:
        try:
            sock.close()
        except Exception:
            pass
        raise LlmError("сеть: {}".format(exc))
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
            raise LlmError("сеть: {}".format(exc))
        if not count:
            raise LlmError("сеть: соединение закрыто при отправке")
        sent += count


def _recv(sock):
    try:
        return sock.recv(READ_CHUNK)
    except OSError as exc:
        raise LlmError("сеть: {}".format(exc))


def _read_head(sock, limit):
    data = bytearray()
    while True:
        marker = data.find(b"\r\n\r\n")
        if marker >= 0:
            return bytes(data[:marker]), bytes(data[marker + 4:])
        if len(data) > limit:
            raise LlmError("HTTP: заголовки слишком большие")
        chunk = _recv(sock)
        if not chunk:
            raise LlmError("HTTP: соединение закрыто без ответа")
        data.extend(chunk)


class Response:
    """Тело ответа по частям: `read()` до `b""`."""

    def __init__(self, sock, status, headers, rest=b""):
        self._sock = sock
        self.status = status
        self.headers = headers
        self._buffer = bytearray(rest)
        self._pos = 0
        self._eof = False
        self._done = False
        self._chunked = (
            headers.get("transfer-encoding", "").lower() == "chunked")
        self._chunk_left = 0
        self._left = None
        if not self._chunked and "content-length" in headers:
            try:
                self._left = int(headers["content-length"])
            except ValueError:
                raise LlmError("HTTP: неверный Content-Length")

    def _available(self):
        return len(self._buffer) - self._pos

    def _consume(self, count):
        self._pos += count
        if self._pos >= len(self._buffer):
            self._buffer = bytearray()
            self._pos = 0
        elif self._pos > READ_CHUNK and self._pos * 2 >= len(self._buffer):
            self._buffer = self._buffer[self._pos:]
            self._pos = 0

    def _fill(self):
        chunk = _recv(self._sock)
        if not chunk:
            self._eof = True
            return False
        self._buffer.extend(chunk)
        return True

    def _line(self):
        while True:
            index = self._buffer.find(b"\r\n", self._pos)
            if index >= 0:
                line = bytes(self._buffer[self._pos:index])
                self._pos = index + 2
                if self._pos >= len(self._buffer):
                    self._buffer = bytearray()
                    self._pos = 0
                return line
            if not self._fill():
                raise LlmError("HTTP: обрыв chunked-ответа")

    def _ensure(self):
        while self._available() == 0 and not self._eof:
            if not self._fill():
                break

    def _take(self, count, limit):
        take = min(count, limit, self._available())
        data = bytes(self._buffer[self._pos:self._pos + take])
        self._consume(take)
        return data

    def _read_chunked(self, count):
        if self._chunk_left == 0:
            line = self._line().split(b";")[0].strip()
            try:
                size = int(line.decode(), 16)
            except ValueError:
                raise LlmError("HTTP: неверный размер чанка")
            if size == 0:
                self._done = True
                return b""
            self._chunk_left = size
        self._ensure()
        if self._available() == 0:
            raise LlmError("HTTP: обрыв чанка")
        data = self._take(count, self._chunk_left)
        self._chunk_left -= len(data)
        if self._chunk_left == 0:
            self._ensure()
            if self._available() < 2:
                raise LlmError("HTTP: обрыв чанка")
            self._consume(2)
        return data

    def read(self, count=READ_CHUNK):
        """Следующий кусок тела; пустые bytes - конец."""
        if self._done:
            return b""
        if self._chunked:
            return self._read_chunked(count)
        if self._left is not None:
            if self._left <= 0:
                self._done = True
                return b""
            self._ensure()
            if self._available() == 0:
                raise LlmError("HTTP: короткий ответ")
            data = self._take(count, self._left)
            self._left -= len(data)
            return data
        self._ensure()
        if self._available() == 0:
            self._done = True
            return b""
        return self._take(count, self._available())

    def read_all(self, limit=MAX_RESPONSE):
        data = bytearray()
        while True:
            chunk = self.read()
            if not chunk:
                return bytes(data)
            data.extend(chunk)
            if len(data) > limit:
                raise LlmError("HTTP: ответ слишком большой")

    def close(self):
        sock = self._sock
        self._sock = None
        self._done = True
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def start(host, path, body=b"", headers=None, timeout=DEFAULT_TIMEOUT,
          secure=True, port=None, limit=MAX_RESPONSE):
    """Отправить запрос и вернуть `Response` после разбора заголовков."""
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
            except LlmError:
                raise
            except Exception as exc:
                raise LlmError("TLS: {}".format(exc))
        _send_all(sock, request)
        head, rest = _read_head(sock, limit)
        status, reply = _parse_head(head)
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        raise
    return Response(sock, status, reply, rest)


def post(host, path, body=b"", headers=None, timeout=DEFAULT_TIMEOUT,
         secure=True, port=None, limit=MAX_RESPONSE):
    """Выполнить POST; вернуть `(status, headers, body)`."""
    response = start(host, path, body, headers, timeout, secure, port,
                     limit)
    try:
        payload = response.read_all(limit)
    finally:
        response.close()
    return response.status, response.headers, payload
