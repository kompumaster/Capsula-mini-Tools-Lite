"""Помощники HTTP-запроса и ответа.

Основано на MicroPyServer (MIT), Copyright (c) 2019 troublegum,
https://github.com/troublegum/micropyserver. Текст лицензии —
в `THIRD_PARTY.md`.
"""

"""Коды ответов HTTP."""
HTTP_CODES = {
    200: "Ok",
    201: "Created",
    204: "No content",
    301: "Moved permanently",
    302: "Found",
    304: "Not modified",
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    405: "Method not allowed",
    408: "Request timeout",
    409: "Conflict",
    413: "Request entity too large",
    415: "Unsupported media type",
    429: "Too many requests",
    500: "Internal server error",
    501: "Not implemented",
    503: "Service unavailable",
}


def send_response(server, response, http_code=200, content_type="text/html",
                  headers=None):
    """Отправить полный HTTP-ответ."""
    if isinstance(response, str):
        body = response.encode()
    elif isinstance(response, (bytes, bytearray)):
        body = bytes(response)
    else:
        body = str(response).encode()
    reason = HTTP_CODES.get(http_code, "")
    lines = [
        "HTTP/1.1 {} {}".format(http_code, reason).rstrip(),
        "Content-Type: {}".format(content_type),
        "Content-Length: {}".format(len(body)),
        "Connection: close",
    ]
    for header in (headers or []):
        text = str(header)
        if "\r" in text or "\n" in text:
            raise ValueError("неверный заголовок")
        lines.append(text)
    head = ("\r\n".join(lines) + "\r\n\r\n").encode()
    server.send(head + body)


def _request_line(request):
    if not isinstance(request, str) or not request:
        raise ValueError("пустой запрос")
    return request.split("\r\n", 1)[0]


def get_request_method(request):
    """Метод запроса: GET, POST, ..."""
    parts = _request_line(request).split(" ")
    if not parts or not parts[0]:
        raise ValueError("нет метода")
    return parts[0].upper()


def get_request_path(request):
    """Путь без query-строки."""
    parts = _request_line(request).split(" ")
    target = parts[1] if len(parts) > 1 else "/"
    if "?" in target:
        target = target.split("?", 1)[0]
    return target or "/"


def get_request_query_string(request):
    """Строка query без `?` или пустая."""
    parts = _request_line(request).split(" ")
    target = parts[1] if len(parts) > 1 else ""
    if "?" not in target:
        return ""
    return target.split("?", 1)[1]


def parse_query_string(query_string):
    """Разобрать `a=1&b=2` в словарь."""
    result = {}
    if not query_string:
        return result
    for item in query_string.split("&"):
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
        else:
            key, value = item, ""
        result[unquote(key)] = unquote(value)
    return result


def get_request_query_params(request):
    """Параметры query-строки."""
    return parse_query_string(get_request_query_string(request))


def get_request_post_params(request):
    """Параметры тела POST (форма urlencoded) или None."""
    if get_request_method(request) != "POST":
        return None
    if "\r\n\r\n" not in request:
        return {}
    return parse_query_string(request.split("\r\n\r\n", 1)[1])


def unquote(string):
    """Декодировать percent-encoding; `+` — пробел."""
    if not string:
        return ""
    if isinstance(string, str):
        string = string.replace("+", " ").encode("utf-8")
    else:
        string = bytes(string).replace(b"+", b" ")
    if b"%" not in string:
        return string.decode("utf-8", "replace")
    result = bytearray()
    position = 0
    while position < len(string):
        char = string[position:position + 1]
        if char == b"%":
            pair = string[position + 1:position + 3]
            try:
                result.append(int(pair, 16))
                position += 3
                continue
            except ValueError:
                pass
        result.extend(char)
        position += 1
    return bytes(result).decode("utf-8", "replace")


def get_cookies(request):
    """Словарь cookies из заголовка `Cookie`."""
    cookies = {}
    for line in request.split("\r\n"):
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        if name.strip().lower() != "cookie":
            continue
        for item in value.split(";"):
            item = item.strip()
            if not item or "=" not in item:
                continue
            key, val = item.split("=", 1)
            cookies[key.strip()] = val.strip()
    return cookies


def create_cookie(name, value, path="/", domain=None, expires=None):
    """Собрать строку `Set-Cookie`."""
    cookie = "Set-Cookie: {}={}".format(name, value)
    if path:
        cookie += "; path={}".format(path)
    if domain:
        cookie += "; domain={}".format(domain)
    if expires:
        cookie += "; expires={}".format(expires)
    return cookie
