# SPDX-License-Identifier: MIT
"""USB-транспорт Amlogic TPL: чтение и запись раздела NAND.

Реализация следует MIT-транспорту Station Mini Root (на основе
pyamlboot, Neil Armstrong / BayLibre, 2018). Здесь только `identify`,
`command`, чтение и запись раздела; никаких erase-all и bootloader.

Работает через pyusb + libusb1 (Linux и Windows).
"""

from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

from common.colors import GREEN, RED, paint

USB_VENDOR_ID = 0x1B8E
USB_PRODUCT_ID = 0xC003
BLOCK = 0x10000          # 64 КиБ, блок протокола записи
READ_CHUNK = 0x10000     # 64 КиБ, кусок bulk-чтения
READ_TIMEOUT = 15000     # мс на один bulk-пакет
HEADER_TIMEOUT = 10000   # мс на заголовок чтения
IDENTIFY_TIMEOUT = 1000

# Пауза после каждого прочитанного блока на Windows: TPL не успевает
# наполнять FIFO, и поток обрывается на 13-21 МиБ (проверено на Win11;
# 2 мс мало, 5 мс уже работало, берём с запасом). На Linux не нужна.
BLOCK_GAP = 0.007

# Пауза после заголовка 0x33, перед чтением данных: даёт TPL время
# наполнить буфер. Только Windows; 2 мс — самый стабильный вариант.
PRE_READ_GAP = 0.002


class UsbError(RuntimeError):
    pass


class BackendAdapter:
    """Стоковый интерфейс плохо отвечает на GET_CONFIGURATION — отдаём 1."""

    def __init__(self, backend):
        self.backend = backend

    def get_configuration(self, handle):
        return 1

    def __getattr__(self, name):
        value = getattr(self.backend, name)
        if not callable(value):
            return value

        def call(*args, **kwargs):
            try:
                return value(*args, **kwargs)
            except NotImplementedError as exc:
                raise UsbError(f"USB-операция не поддержана: {name}") from exc

        return call


def make_backend():
    try:
        import usb.backend.libusb1
    except ImportError as exc:
        raise UsbError(
            "не установлен pyusb; выполните: "
            "python -m pip install -r requirements.txt"
        ) from exc

    backend = None
    try:
        import libusb_package
        backend = libusb_package.get_libusb1_backend()
    except (ImportError, OSError):
        pass
    if backend is None:
        backend = usb.backend.libusb1.get_backend()
    if backend is None:
        raise UsbError(
            "не загружается libusb. Linux: установите libusb-1.0; "
            "Windows: libusb-package и WinUSB-драйвер для 1B8E:C003"
        )
    return BackendAdapter(usb.backend.libusb1._LibUSB(backend.lib))


def retryable(exc: BaseException) -> bool:
    """Ошибка захвата, которую стоит повторить.

    `open_device` на Windows иногда не проходит с первой попытки:
    драйвер ещё не готов или устройство переустанавливается. Отказ
    протокола (неподдерживаемый stage, отклонённая команда) не
    повторяем.
    """
    import usb.core

    if isinstance(exc, usb.core.USBError):
        return True
    text = str(exc)
    return "open_device" in text or "не поддержана" in text


def _finalize_device(device) -> None:
    """Освобождает ссылку libusb на устройство, пока контекст жив."""
    try:
        dev = getattr(getattr(device, "_ctx", None), "dev", None)
        finalize = getattr(dev, "finalize", None)
        if finalize is not None:
            finalize()
    except Exception:
        pass


def _finalize_backend(device) -> None:
    """Завершает контекст libusb; вызывать после освобождения устройства."""
    try:
        backend = getattr(getattr(device, "_ctx", None), "backend", None)
        finalize = getattr(backend, "finalize", None)
        if finalize is not None:
            finalize()
    except Exception:
        pass


def release_device(device) -> None:
    """Закрывает handle и освобождает устройство, контекст оставляет.

    Порядок важен: при сборке мусора pyusb завершает контекст раньше
    устройства и падает в `libusb_unref_device`. Здесь устройство
    освобождается первым, а backend живёт до конца захвата.
    """
    try:
        import usb.util

        usb.util.dispose_resources(device)
    except Exception:
        pass
    _finalize_device(device)


class Transport:
    def __init__(self, device):
        self.device = device
        self._epin = None
        self._epout = None

    @classmethod
    def wait(cls, seconds: int = 300, log=print):
        """Ждёт загрузчик 1B8E:C003 и захватывает его.

        Ошибки `open_device` и USB-таймауты повторяются до конца
        отведённого времени: на Windows первая попытка часто не
        проходит, пока драйвер не готов.
        """
        import usb.core

        backend = make_backend()
        deadline = time.monotonic() + seconds
        last_error = None
        tty = getattr(sys.stdout, "isatty", lambda: False)()

        def status(remaining: int) -> str:
            return ("жду загрузчик "
                    + paint(f"(подключите/передёрните колонку, "
                            f"жду {remaining} с)", RED))

        def finish_line() -> None:
            if tty:
                sys.stdout.write("\n")
                sys.stdout.flush()

        shown = seconds
        if tty:
            sys.stdout.write(status(seconds))
            sys.stdout.flush()
        else:
            log(status(seconds))

        while time.monotonic() < deadline:
            if tty:
                remaining = max(0, int(deadline - time.monotonic()) + 1)
                if remaining != shown:
                    shown = remaining
                    sys.stdout.write("\r" + status(remaining) + "    ")
                    sys.stdout.flush()
            devices = list(usb.core.find(
                find_all=True, idVendor=USB_VENDOR_ID,
                idProduct=USB_PRODUCT_ID, backend=backend))
            if len(devices) > 1:
                finish_line()
                raise UsbError("подключено больше одной колонки в загрузчике")
            if devices:
                transport = cls(devices[0])
                try:
                    ident = transport.identify()
                    transport.validate_identify(ident)
                    transport.command("    low_power")
                    finish_line()
                    log("")
                    log(paint(f"загрузчик захвачен: {ident.hex(' ')}",
                              GREEN))
                    log("")
                    return transport
                except Exception as exc:
                    last_error = str(exc)
                    release_device(devices[0])
                    if not retryable(exc):
                        finish_line()
                        raise
            time.sleep(0.05)
        finish_line()
        hint = (" Проверьте USB-кабель и WinUSB-драйвер для 1B8E:C003."
                if sys.platform == "win32" else " Проверьте USB-кабель и права доступа.")
        if (last_error and sys.platform == "win32"
                and "open_device" in last_error):
            hint = (" Windows не открывает 1B8E:C003: нужен WinUSB именно "
                    "для этого устройства; лишние libusb0/libusbK удалить, "
                    "кабель переподключить.")
        raise UsbError("загрузчик не найден за отведённое время"
                       + (f": {last_error}" if last_error else "")
                       + hint)

    @staticmethod
    def validate_identify(ident: bytes) -> None:
        if len(ident) < 5 or ident[3] != 0x10 or ident[4] != 0:
            raise UsbError(
                f"неподдерживаемый/заблокированный загрузчик: {ident.hex()}; "
                "нужен stage=0x10"
            )

    def identify(self) -> bytes:
        return bytes(self.device.ctrl_transfer(0xC0, 0x20, 0, 0, 8,
                                              timeout=IDENTIFY_TIMEOUT))

    def keepalive(self) -> None:
        self.validate_identify(self.identify())

    def close(self) -> None:
        """Закрывает устройство и детерминированно освобождает libusb.

        Без этого pyusb при выходе завершает контекст раньше устройства
        и печатает `access violation` из `libusb_unref_device`.
        """
        import gc
        import usb.util

        device = self.device
        self.device = None
        self._epin = None
        self._epout = None
        if device is None:
            return
        try:
            usb.util.dispose_resources(device)
        except Exception:
            pass
        _finalize_device(device)
        _finalize_backend(device)
        del device
        gc.collect()

    def endpoints(self):
        import usb.util
        if self._epin is None:
            interface = self.device.get_active_configuration()[(0, 0)]
            self._epin = usb.util.find_descriptor(
                interface,
                custom_match=lambda ep: usb.util.endpoint_direction(
                    ep.bEndpointAddress) == usb.util.ENDPOINT_IN)
            self._epout = usb.util.find_descriptor(
                interface,
                custom_match=lambda ep: usb.util.endpoint_direction(
                    ep.bEndpointAddress) == usb.util.ENDPOINT_OUT)
            if self._epin is None or self._epout is None:
                raise UsbError("не найдены bulk endpoints")
        return self._epin, self._epout

    def command(self, command: str, timeout: int = 15000) -> None:
        payload = command.encode("ascii") + b"\0"
        if len(payload) >= 128:
            raise ValueError("слишком длинная команда")
        self.device.ctrl_transfer(0x40, 0x34, 0, 2, payload, timeout=1000)
        deadline = time.monotonic() + timeout / 1000
        while True:
            response = bytes(self.device.read(0x81, 512,
                                             timeout=timeout)).rstrip(b"\0")
            if response.startswith(b"Continue:34"):
                if time.monotonic() > deadline:
                    raise UsbError(f"таймаут команды {command!r}")
                time.sleep(0.1)
                continue
            if response != b"success":
                raise UsbError(f"TPL отклонил {command!r}: {response!r}")
            return

    def _read_blocks(self, part: str, size: int, on_block,
                     progress, allow_short: bool) -> int:
        """Читает раздел блоками и отдаёт их в on_block; без записи."""
        import usb.core

        self.keepalive()
        received = 0
        epin, _ = self.endpoints()
        self.command(f"upload store {part} normal 0x{size:x}")
        while received < size:
            try:
                request = bytes(self.device.ctrl_transfer(
                    0xC0, 0x33, 0, 0, 16, timeout=HEADER_TIMEOUT))
            except usb.core.USBError as exc:
                if allow_short and received > 0:
                    break
                raise UsbError(
                    f"чтение прервано на {received} из {size} Б: {exc}") from exc
            if len(request) != 16:
                if allow_short and received > 0:
                    break
                raise UsbError("повреждён заголовок чтения")
            magic, length, sequence, _checksum = struct.unpack(
                "<IIII", request)
            if magic != 0xEFE8 or not 0 < length <= BLOCK:
                if allow_short and received > 0:
                    break
                raise UsbError(
                    f"некорректный блок: magic={magic:#x}, len={length}")
            if received + length > size:
                if allow_short and received > 0:
                    break
                raise UsbError("блок выходит за размер раздела")
            if sys.platform == "win32":
                time.sleep(PRE_READ_GAP)
            block = bytearray()
            while len(block) < length:
                try:
                    part_data = bytes(epin.read(
                        min(READ_CHUNK, length - len(block)),
                        timeout=READ_TIMEOUT))
                except usb.core.USBError as exc:
                    if allow_short and received + len(block) > 0:
                        break
                    raise UsbError(
                        f"чтение данных прервано на "
                        f"{received + len(block)} из {size} Б: {exc}") from exc
                if not part_data or len(part_data) > length - len(block):
                    if allow_short and received + len(block) > 0:
                        break
                    raise UsbError("пустой/слишком длинный USB-пакет")
                block.extend(part_data)
            if len(block) < length:
                if allow_short and received + len(block) > 0:
                    on_block(block)
                    received += len(block)
                    progress(received, size)
                break
            on_block(block)
            received += length
            progress(received, size)
            if sys.platform == "win32":
                time.sleep(BLOCK_GAP)
        return received

    def read_partition(self, part: str, size: int, output: Path,
                       progress=lambda n, total: None,
                       force: bool = False,
                       allow_short: bool = False) -> str:
        """Читает раздел, пишет файл, возвращает SHA-256.

        `allow_short` — принять частичное чтение (зонд размера): при
        ошибке/конце раздела файл остаётся с прочитанным.
        """
        import hashlib

        if output.exists():
            if not force:
                raise FileExistsError(output)
            output.unlink()
        digest = hashlib.sha256()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            def sink(block):
                stream.write(block)
                digest.update(block)

            self._read_blocks(part, size, sink, progress, allow_short)
        return digest.hexdigest()

    def read_hash(self, part: str, size: int,
                  progress=lambda n, total: None,
                  allow_short: bool = False) -> tuple[str, int]:
        """Читает раздел без записи: (sha256, прочитано байт)."""
        import hashlib

        digest = hashlib.sha256()

        def sink(block):
            digest.update(block)

        received = self._read_blocks(part, size, sink, progress, allow_short)
        return digest.hexdigest(), received

    def write_partition(self, part: str, size: int, image: Path,
                        progress=lambda n, total: None) -> None:
        """Пишет образ в раздел; размер должен совпадать точно."""
        if size <= 0 or size % BLOCK:
            raise ValueError(f"{size} Б не кратно блоку {BLOCK}")
        if image.stat().st_size != size:
            raise ValueError(
                f"{image}: размер {image.stat().st_size}, ожидался {size}")
        self.keepalive()
        _, epout = self.endpoints()
        self.command("disk_initial 0", timeout=60000)
        payload = f"download store {part} normal 0x{size:x}\0".encode("ascii")
        self.device.ctrl_transfer(0x40, 0x30, 0, 1, payload, timeout=1000)
        status = bytes(self.device.ctrl_transfer(
            0xC0, 0x31, 0, 0, 64, timeout=60000)).rstrip(b"\0")
        if status != b"success":
            raise UsbError(f"TPL отклонил download: {status!r}")

        sent = 0
        with image.open("rb") as stream:
            for seq in range(size // BLOCK):
                data = stream.read(BLOCK)
                if len(data) != BLOCK:
                    raise UsbError("образ изменился во время записи")
                checksum = sum(struct.unpack("<16384I", data)) & 0xFFFFFFFF
                control = struct.pack("<IIIIHH", 0, len(data), seq,
                                      checksum, 0xEF, 0x200)
                self.device.ctrl_transfer(0x40, 0x32, 1, 0xFFFF,
                                          control.ljust(32, b"\0"),
                                          timeout=5000)
                if epout.write(data, timeout=15000) != len(data):
                    raise UsbError("неполная USB-запись")
                deadline = time.monotonic() + 60
                while True:
                    ack = bytes(self.device.read(0x81, 512, timeout=60000))
                    if ack.startswith(b"Continue:32") and time.monotonic() < deadline:
                        continue
                    if not ack.startswith(b"OK!!"):
                        raise UsbError(
                            f"ошибка подтверждения блока {seq}: {ack[:80]!r}")
                    break
                sent += len(data)
                progress(sent, size)
        self.command("download get_status", timeout=60000)

    def reboot(self) -> None:
        import usb.core
        try:
            self.device.ctrl_transfer(0x40, 0x34, 0, 2, b"reset\0",
                                     timeout=1000)
        except usb.core.USBError as exc:
            if exc.errno != 19 and getattr(exc, "backend_error_code", None) != -4:
                raise
