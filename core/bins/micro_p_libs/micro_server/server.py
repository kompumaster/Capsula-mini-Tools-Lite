"""HTTP-сервер для MicroPython.

Основано на MicroPyServer (MIT), Copyright (c) 2019 troublegum,
https://github.com/troublegum/micropyserver. Текст лицензии —
в `THIRD_PARTY.md`.

Сервер блокирующий: `serve_forever()` крутится, пока не вызван
`stop()` (из другого потока) или пока не закрыт сокет.
"""

import socket

from micro_server import utils
from micro_server.config import (
    ACCEPT_TIMEOUT, DEFAULT_HOST, DEFAULT_PORT, DEFAULT_TIMEOUT,
    MAX_BODY, MAX_HEADER)
from micro_server.errors import ServerError


class MicroServer:
    """Минимальный HTTP-сервер с таблицей маршрутов."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 timeout=DEFAULT_TIMEOUT, max_body=MAX_BODY):
        if not isinstance(host, str) or not host.strip():
            raise ServerError("host должен быть непустой строкой")
        if isinstance(port, bool) or not isinstance(port, int):
            raise ServerError("port должен быть целым числом")
        if port < 0 or port > 65535:
            raise ServerError("port должен быть в 0…65535")
        self._host = host
        self._port = port
        self.port = port
        self.timeout = float(timeout)
        self.max_body = int(max_body)
        self._routes = []
        self._sock = None
        self._connect = None
        self._running = False
        self._on_request_handler = None
        self._on_not_found_handler = None
        self._on_error_handler = None

    # --- маршруты и обработчики -----------------------------------

    def add_route(self, path, handler, method="GET"):
        """Добавить маршрут: точный путь и метод."""
        if not isinstance(path, str) or not path.startswith("/"):
            raise ServerError("путь должен начинаться с /")
        if not callable(handler):
            raise ServerError("обработчик маршрута не вызывается")
        method = str(method).upper()
        self._routes.append(
            {"path": path, "handler": handler, "method": method})
        return self

    def on_request(self, handler):
        """Обработчик до маршрута: `(request, address) -> bool`."""
        self._on_request_handler = handler

    def on_not_found(self, handler):
        self._on_not_found_handler = handler

    def on_error(self, handler):
        self._on_error_handler = handler

    # --- запуск и остановка ---------------------------------------

    def start(self):
        if self._sock is not None:
            raise ServerError("сервер уже запущен")
        try:
            address = socket.getaddrinfo(
                self._host, self._port, socket.AF_INET,
                socket.SOCK_STREAM)[0][-1]
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(address)
            sock.listen(1)
            sock.settimeout(ACCEPT_TIMEOUT)
        except OSError as exc:
            raise ServerError("не открыть порт {}: {}".format(
                self._port, exc))
        self._sock = sock
        try:
            self.port = sock.getsockname()[1]
        except Exception:
            # MicroPython не даёт getsockname; порт остаётся заданным.
            self.port = self._port
        self._running = True
        return self

    def stop(self):
        """Остановить сервер; безопасно повторно."""
        self._running = False
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        conn = self._connect
        self._connect = None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def close(self):
        self.stop()

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def serve_forever(self):
        """Обслуживать запросы, пока сервер не остановлен."""
        if self._sock is None:
            self.start()
        while self._running:
            self.handle_once(ACCEPT_TIMEOUT)

    def poll(self, timeout=0.0):
        """Один шаг для оркестратора; псевдоним `handle_once`."""
        return self.handle_once(timeout)

    def handle_once(self, timeout=0.0):
        """Обработать не больше одного запроса.

        `timeout` — сколько ждать соединение. `0` — не ждать.
        `True`, если запрос был принят и обработан.
        """
        if self._sock is None:
            raise ServerError("сервер не запущен")
        try:
            self._sock.settimeout(float(timeout))
        except OSError as exc:
            raise ServerError("не задать таймаут: {}".format(exc))
        try:
            connection, address = self._sock.accept()
        except OSError:
            return False
        self._connect = connection
        handled = True
        try:
            connection.settimeout(self.timeout)
            request = self.get_request()
            if not request:
                handled = False
            else:
                if self._on_request_handler:
                    if not self._on_request_handler(request, address):
                        handled = False
                if handled:
                    route = self.find_route(request)
                    if route is not None:
                        route["handler"](request)
                    else:
                        self._route_not_found(request)
        except ServerError as exc:
            self._internal_error(exc)
        except Exception as exc:
            self._internal_error(exc)
        finally:
            try:
                connection.close()
            except Exception:
                pass
            self._connect = None
            try:
                self._sock.settimeout(ACCEPT_TIMEOUT)
            except Exception:
                pass
        return handled

    # --- запрос и ответ -------------------------------------------

    def send(self, data):
        """Отправить данные в текущее соединение."""
        if self._connect is None:
            raise ServerError("нет соединения для ответа")
        if isinstance(data, str):
            data = data.encode()
        elif not isinstance(data, (bytes, bytearray)):
            data = str(data).encode()
        try:
            self._connect.sendall(data)
        except OSError as exc:
            raise ServerError("не отправить ответ: {}".format(exc))

    def get_request(self):
        """Прочитать запрос целиком: заголовки и тело."""
        raw = bytearray()
        while b"\r\n\r\n" not in raw:
            chunk = self._recv(1024)
            if not chunk:
                return ""
            raw.extend(chunk)
            if len(raw) > MAX_HEADER:
                raise ServerError("слишком большие заголовки")
        head, _separator, rest = bytes(raw).partition(b"\r\n\r\n")
        length = self._content_length(head)
        if length > self.max_body:
            raise ServerError("слишком большое тело")
        body = bytearray(rest)
        while len(body) < length:
            chunk = self._recv(min(4096, length - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        if len(body) < length:
            raise ServerError("короткое тело запроса")
        result = head + b"\r\n\r\n" + bytes(body[:length])
        return result.decode("utf-8", "replace")

    def _recv(self, size):
        try:
            return self._connect.recv(size)
        except OSError as exc:
            raise ServerError("не прочитать запрос: {}".format(exc))

    @staticmethod
    def _content_length(head):
        for line in head.split(b"\r\n")[1:]:
            if b":" not in line:
                continue
            name, value = line.split(b":", 1)
            if name.strip().lower() != b"content-length":
                continue
            try:
                length = int(value.strip())
            except ValueError:
                raise ServerError("неверный Content-Length")
            if length < 0:
                raise ServerError("неверный Content-Length")
            return length
        return 0

    def find_route(self, request):
        """Найти маршрут по методу и пути."""
        try:
            method = utils.get_request_method(request)
            path = utils.get_request_path(request)
        except ValueError:
            return None
        for route in self._routes:
            if route["method"] != method:
                continue
            if route["path"] == path:
                return route
        return None

    def _route_not_found(self, request):
        if self._on_not_found_handler:
            self._on_not_found_handler(request)
            return
        utils.send_response(
            self, '{"error": "not found"}', 404, "application/json")

    def _internal_error(self, error):
        if self._on_error_handler:
            self._on_error_handler(error)
            return
        try:
            utils.send_response(
                self, '{"error": "internal"}', 500, "application/json")
        except Exception:
            pass
