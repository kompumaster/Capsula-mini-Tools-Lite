"""Команды включения и выключения Bluetooth."""

from micro_agent.commands.base import Command
from micro_agent.intent import has_any, has_word

BT_WORDS = ("bluetooth", "блютуз", "блютус", "блютз")
ON_WORDS = ("включ", "вруб", "активир", "старт", "подключ")
OFF_WORDS = ("выключ", "отключ", "выкл", "отруб", "стоп")


def _bt(text):
    return has_any(text, BT_WORDS) or has_word(text, "bt")


class BluetoothOff(Command):
    name = "bluetooth.off"
    order = 10
    ack_text = "блютус выключен"

    def matches(self, text):
        return (_bt(text)
                and (has_any(text, OFF_WORDS) or has_word(text, "off")))

    def run(self, context):
        return context.bt_disable()


class BluetoothOn(Command):
    name = "bluetooth.on"
    order = 11
    ack_text = "блютус включен"

    def matches(self, text):
        on = has_any(text, ON_WORDS) or has_word(text, "on")
        off = has_any(text, OFF_WORDS) or has_word(text, "off")
        return _bt(text) and on and not off

    def run(self, context):
        return context.bt_enable()
