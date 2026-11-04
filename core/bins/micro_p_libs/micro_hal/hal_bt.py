"""Bluetooth: адаптер BlueZ и звук A2DP через PulseAudio.

Только железо/стек: вызовы `gdbus` к `org.bluez` и `pactl` к Pulse.
Политика (когда включать, когда глушить) — в `lib_bt`.

Проверено на плате 03.11.2026: A2DP Sink регистрирует
`module-bluez5-discover`; звук с телефона приходит **источником**
`bluez_source.<MAC>.a2dp_source`, на колонку его выводит
`module-loopback source=… sink=master`; PBAP (`0x1130`) не
объявляется, потому что `bluetoothd` запущен с `--plugin=a2dp,avrc`.
"""

from micro_hal import hal_common, hal_volume
from micro_hal.hal_common import HalError

__all__ = [
    "GDBUS", "BLUEZ", "ADAPTER", "PACTL", "BLUEZ_MODULE", "SINK",
    "available", "adapter", "power", "discoverable", "pairable",
    "alias", "devices", "device", "trust", "connect", "disconnect",
    "forget",
    "sources", "bluez_module", "bluez_load", "bluez_unload",
    "loopback_module", "loopback_add", "loopback_remove",
    "loopback_input", "input_volume", "input_muted", "set_input_volume",
    "mute_input",
]

GDBUS = "/usr/bin/gdbus"
BLUEZ = "org.bluez"
ADAPTER = "/org/bluez/hci0"
PACTL = "/usr/bin/pactl"
BLUEZ_MODULE = "module-bluez5-discover"
SINK = "master"


def _quote(text):
    """Значение в одинарных кавычках; кавычки и переводы строк запрещены."""
    text = str(text)
    if "'" in text or "\n" in text or "\r" in text:
        raise HalError("недопустимое значение: {!r}".format(text))
    return "'{}'".format(text)


def _capture(command):
    code, text = hal_common.capture(command)
    if code != 0:
        raise HalError("{}: код {}: {}".format(
            command.split()[0], code, text.strip()[:120]))
    return text


def _gdbus(path, method, *args):
    command = "{} call --system --dest {} --object-path {} " \
              "--method {}".format(GDBUS, BLUEZ, _quote(path), method)
    for value in args:
        command += " " + _quote(value)
    return _capture(command).strip()


def _introspect(path="/org/bluez/hci0", recurse=False):
    command = "{} introspect --system --dest {} --object-path {}".format(
        GDBUS, BLUEZ, _quote(path))
    if recurse:
        command += " --recurse"
    return _capture(command)


def _parse_properties(text):
    """Свойства из `gdbus introspect`: имя → (тип, значение)."""
    properties = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line.endswith(";") or " = " not in line:
            continue
        left, right = line[:-1].split(" = ", 1)
        parts = left.split()
        if len(parts) < 3:
            continue
        properties[parts[2]] = (parts[1], right.strip())
    return properties


def _parse_value(kind, text):
    if kind == "b":
        return text == "true"
    if kind in ("u", "i", "q", "n"):
        return int(text)
    if kind in ("s", "o"):
        if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
            return text[1:-1]
        return text
    if kind == "as":
        body = text.strip()
        if body.startswith("[") and body.endswith("]"):
            body = body[1:-1]
        items = []
        for part in body.split(","):
            part = part.strip()
            if len(part) >= 2 and part[0] == "'" and part[-1] == "'":
                items.append(part[1:-1])
        return items
    return text


def _properties(path):
    text = _parse_properties(_introspect(path))
    return {name: _parse_value(kind, value)
            for name, (kind, value) in text.items()}


def available():
    """Есть ли gdbus, pactl и адаптер."""
    if not hal_common.exists(GDBUS) or not hal_common.exists(PACTL):
        return False
    try:
        return "org.bluez.Adapter1" in _introspect(ADAPTER)
    except HalError:
        return False


def adapter():
    """Свойства адаптера."""
    values = _properties(ADAPTER)
    return {
        "address": values.get("Address"),
        "name": values.get("Name"),
        "alias": values.get("Alias"),
        "powered": values.get("Powered"),
        "discoverable": values.get("Discoverable"),
        "pairable": values.get("Pairable"),
        "discovering": values.get("Discovering"),
        "uuids": values.get("UUIDs", []),
    }


def _set(path, interface, name, variant):
    _gdbus(path, "org.freedesktop.DBus.Properties.Set",
           interface, name, variant)


def power(on=True):
    """Включить/выключить адаптер (`Powered`)."""
    _set(ADAPTER, "org.bluez.Adapter1", "Powered",
         "<true>" if on else "<false>")
    return bool(on)


def discoverable(on=True):
    """Видно ли колонку другим устройствам."""
    _set(ADAPTER, "org.bluez.Adapter1", "Discoverable",
         "<true>" if on else "<false>")
    return bool(on)


def pairable(on=True):
    """Можно ли подключиться (сопряжение)."""
    _set(ADAPTER, "org.bluez.Adapter1", "Pairable",
         "<true>" if on else "<false>")
    return bool(on)


def alias(name):
    """Имя, которое видит телефон."""
    name = str(name)
    if '"' in name or "\\" in name:
        raise HalError(
            "недопустимое имя (кавычка или обратная косая): {!r}".format(
                name))
    _set(ADAPTER, "org.bluez.Adapter1", "Alias",
         '<"{}">'.format(name))
    return name


def _device_path(address):
    address = str(address).upper().replace(":", "_")
    return "{}/dev_{}".format(ADAPTER, address)


def _parse_devices(text):
    """Разобрать `introspect --recurse` на устройства."""
    devices = []
    current = None
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("node "):
            path = stripped[5:-2].strip()
            # Только сами устройства: у них есть Address; вложенные
            # узлы (player0, fd0, sep1) отбрасываем.
            depth = ADAPTER.count("/") + 1
            current = (path if path.startswith(ADAPTER + "/dev_") and
                       path.count("/") == depth else None)
            continue
        if current is None:
            continue
        if stripped.startswith("interface "):
            continue
        if not stripped.endswith(";") or " = " not in stripped:
            continue
        left, right = stripped[:-1].split(" = ", 1)
        parts = left.split()
        if len(parts) < 3:
            continue
        name = parts[2]
        if name in ("Address", "Name", "Alias", "Paired", "Trusted",
                    "Connected", "RSSI"):
            if not devices or devices[-1]["path"] != current:
                devices.append({"path": current})
            devices[-1][name] = _parse_value(parts[1], right.strip())
    return devices


def devices():
    """Список устройств BlueZ с основными свойствами."""
    result = []
    for item in _parse_devices(_introspect(ADAPTER, recurse=True)):
        result.append({
            "address": item.get("Address"),
            "name": item.get("Name"),
            "alias": item.get("Alias"),
            "paired": item.get("Paired", False),
            "trusted": item.get("Trusted", False),
            "connected": item.get("Connected", False),
            "path": item["path"],
        })
    return result


def device(address):
    """Одно устройство по адресу или None."""
    address = str(address).upper()
    for item in devices():
        if item["address"] == address:
            return item
    return None


def trust(address, on=True):
    """Пометить устройство доверенным (обход агента)."""
    _set(_device_path(address), "org.bluez.Device1", "Trusted",
         "<true>" if on else "<false>")
    return bool(on)


def connect(address):
    """Подключить устройство (A2DP поднимется сам)."""
    _gdbus(_device_path(address), "org.bluez.Device1.Connect")
    return str(address).upper()


def disconnect(address):
    """Отключить устройство."""
    _gdbus(_device_path(address), "org.bluez.Device1.Disconnect")
    return str(address).upper()


def forget(address):
    """Удалить сопряжение: BlueZ забудет ключи и устройство."""
    _gdbus(ADAPTER, "org.bluez.Adapter1.RemoveDevice",
           _device_path(address))
    return str(address).upper()


def _pactl(args):
    return _capture("{} {}".format(PACTL, args))


def sources():
    """Имена источников Pulse, пришедших по Bluetooth."""
    text = _pactl("list short sources")
    names = []
    for line in text.split("\n"):
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("bluez_source."):
            names.append(parts[1])
    return names


def _modules():
    text = _pactl("list modules short")
    items = []
    for line in text.split("\n"):
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip().isdigit():
            items.append({"id": int(parts[0]), "name": parts[1],
                          "args": parts[2] if len(parts) > 2 else ""})
    return items


def bluez_module():
    """id `module-bluez5-discover` или None."""
    for item in _modules():
        if item["name"] == BLUEZ_MODULE:
            return item["id"]
    return None


def bluez_load():
    """Загрузить `module-bluez5-discover`; вернуть id."""
    current = bluez_module()
    if current is not None:
        return current
    text = _pactl("load-module {}".format(BLUEZ_MODULE)).strip()
    try:
        return int(text)
    except ValueError:
        raise HalError("pactl: неожиданный ответ {!r}".format(text))


def bluez_unload():
    """Выгрузить модуль BlueZ; True, если он был."""
    current = bluez_module()
    if current is None:
        return False
    _pactl("unload-module {}".format(current))
    return True


def loopback_module(source=None):
    """id `module-loopback` для Bluetooth-источника или None."""
    for item in _modules():
        if item["name"] != "module-loopback":
            continue
        if source is None and "bluez_source." in item["args"]:
            return item["id"]
        if source is not None and item["args"].find(source) >= 0:
            return item["id"]
    return None


def loopback_add(source=None, sink=SINK, latency_msec=200):
    """Свести звук телефона на `sink`; вернуть id модуля."""
    if source is None:
        names = sources()
        if not names:
            raise HalError("нет Bluetooth-источника")
        source = names[0]
    command = ("load-module module-loopback source={} sink={} "
               "latency_msec={}").format(source, sink, int(latency_msec))
    text = _pactl(command).strip()
    try:
        return int(text)
    except ValueError:
        raise HalError("pactl: неожиданный ответ {!r}".format(text))


def loopback_remove():
    """Снять loopback; True, если он был."""
    current = loopback_module()
    if current is None:
        return False
    _pactl("unload-module {}".format(current))
    return True


def _sink_inputs():
    """Блоки `pactl list sink-inputs` с индексом, модулем и драйвером."""
    text = _pactl("list sink-inputs")
    items = []
    current = None
    for line in text.split("\n"):
        if line.startswith("Sink Input #"):
            current = {"index": int(line.split("#")[1]), "module": None,
                       "driver": "", "mute": None, "volume": None}
            items.append(current)
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        value = value.strip()
        if key == "Owner Module":
            try:
                current["module"] = int(value)
            except ValueError:
                current["module"] = None
        elif key == "Driver":
            current["driver"] = value
        elif key == "Mute":
            current["mute"] = value == "yes"
        elif key == "Volume":
            current["volume"] = hal_volume.parse_percent(value)
    return items


def loopback_input():
    """Индекс sink-input модуля loopback или None."""
    module = loopback_module()
    if module is None:
        return None
    for item in _sink_inputs():
        if item["module"] == module and item["driver"].startswith(
                "module-loopback"):
            return item["index"]
    return None


def input_volume():
    """Громкость звука телефона в процентах или None."""
    index = loopback_input()
    if index is None:
        return None
    for item in _sink_inputs():
        if item["index"] == index:
            return item["volume"]
    return None


def input_muted():
    """Временно ли снят звук телефона; None — loopback нет."""
    index = loopback_input()
    if index is None:
        return None
    for item in _sink_inputs():
        if item["index"] == index:
            return item["mute"]
    return None


def set_input_volume(percent):
    """Громкость звука телефона, 0…100."""
    percent = int(percent)
    if percent < 0 or percent > 100:
        raise HalError("громкость должна быть в 0…100")
    index = loopback_input()
    if index is None:
        raise HalError("звук телефона не выведен на динамик")
    _pactl("set-sink-input-volume {} {}%".format(index, percent))
    return percent


def mute_input(on=True):
    """Временно снять звук телефона (A2DP не рвётся)."""
    index = loopback_input()
    if index is None:
        raise HalError("звук телефона не выведен на динамик")
    _pactl("set-sink-input-mute {} {}".format(index, 1 if on else 0))
    return bool(on)
