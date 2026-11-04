"""Bluetooth: политика включения, маршрута звука и громкости.

Только логика поверх `hal_bt`: что включить, когда снять звук
телефона, какую громкость поставить. Команды BlueZ/Pulse — в
`hal_bt`; системные сообщения играет `lib_speaker` в `master`.

По умолчанию Bluetooth **выключен**: после старта ничего не
вызывается, пока не позовут `enable()`.
"""

from micro_hal import hal_bt
from micro_hal.hal_common import HalError

__all__ = [
    "ALIAS", "SINK",
    "enabled", "visible", "status",
    "enable", "disable",
    "devices", "device", "connect", "disconnect", "forget",
    "trust", "trust_paired",
    "audio", "audio_start", "audio_stop",
    "mute", "muted", "volume",
]

ALIAS = "Capsula Mini"
SINK = "master"


def enabled():
    """Включён ли адаптер."""
    try:
        return bool(hal_bt.adapter().get("powered"))
    except HalError:
        return False


def visible():
    """Видно ли колонку и можно ли подключиться."""
    try:
        info = hal_bt.adapter()
    except HalError:
        return False
    return bool(info.get("discoverable") and info.get("pairable"))


def status():
    """Краткая сводка: адаптер, устройство, источник, звук."""
    try:
        info = hal_bt.adapter()
    except HalError:
        return {"enabled": False, "visible": False, "device": None,
                "source": None, "audio": False, "volume": None,
                "muted": None}
    connected = None
    for item in hal_bt.devices():
        if item["connected"]:
            connected = item
            break
    names = hal_bt.sources()
    return {
        "enabled": bool(info.get("powered")),
        "visible": bool(info.get("discoverable")
                        and info.get("pairable")),
        "device": connected,
        "source": names[0] if names else None,
        "audio": hal_bt.loopback_module() is not None,
        "volume": hal_bt.input_volume(),
        "muted": hal_bt.input_muted(),
    }


def enable(alias=ALIAS):
    """Включить Bluetooth и сделать колонку видимой."""
    hal_bt.power(True)
    hal_bt.bluez_load()
    hal_bt.alias(alias)
    hal_bt.discoverable(True)
    hal_bt.pairable(True)
    return status()


def disable():
    """Снять звук, скрыть колонку и выключить адаптер."""
    audio_stop()
    hal_bt.discoverable(False)
    hal_bt.pairable(False)
    hal_bt.power(False)
    hal_bt.bluez_unload()
    return status()


def devices():
    """Сопряжённые/подключённые устройства BlueZ."""
    return hal_bt.devices()


def device(address):
    """Одно устройство или None."""
    return hal_bt.device(address)


def connect(address):
    """Подключить телефон; доверяем ему, чтобы не нужен был агент."""
    hal_bt.trust(address, True)
    hal_bt.connect(address)
    return str(address).upper()


def disconnect(address):
    """Отключить телефон."""
    return hal_bt.disconnect(address)


def trust(address, on=True):
    """Пометить телефон доверенным: без агента A2DP иначе отклонят."""
    return hal_bt.trust(address, on)


def trust_paired():
    """Пометить доверенными все сопряжённые устройства.

    Нужно после нового сопряжения: BlueZ создаёт устройство с
    `Trusted=false`, и первое подключение A2DP отклоняется
    (`Access denied`), пока агента нет.
    """
    count = 0
    for item in hal_bt.devices():
        if item["paired"] and not item["trusted"]:
            hal_bt.trust(item["address"], True)
            count += 1
    return count


def forget(address):
    """Удалить сопряжение с телефоном.

    BlueZ удаляет ключи; на телефоне колонку тоже надо «забыть»,
    иначе останутся старые ключи и сопряжение зациклится.
    """
    return hal_bt.forget(address)


def audio():
    """Идёт ли звук телефона на динамик."""
    return hal_bt.loopback_module() is not None


def audio_start(latency_msec=200):
    """Вывести звук подключённого телефона на `master`.

    True — звук уже идёт или включён; False — нет источника
    (телефон не подключён).
    """
    if hal_bt.loopback_module() is not None:
        return True
    if not hal_bt.sources():
        return False
    hal_bt.loopback_add(latency_msec=latency_msec)
    return True


def audio_stop():
    """Снять звук телефона с динамика; True, если что-то снимали."""
    return hal_bt.loopback_remove()


def mute(on=True):
    """Временно снять звук телефона, не разрывая A2DP.

    False — если звук телефона не выведен (нечего глушить).
    """
    if hal_bt.loopback_module() is None:
        return False
    return hal_bt.mute_input(on)


def muted():
    """Снят ли звук телефона; None — loopback нет."""
    return hal_bt.input_muted()


def volume(percent=None):
    """Громкость звука телефона: без аргумента — прочитать.

    Это отдельная громкость от `master`: системные сообщения идут
    на `master` и не зависят от неё.
    """
    if percent is None:
        return hal_bt.input_volume()
    return hal_bt.set_input_volume(percent)
