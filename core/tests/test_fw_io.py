#!/usr/bin/env python3
"""Тесты `fw_io`: кадры чтения/записи на фейковом USB-устройстве."""

from __future__ import annotations

import io
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fw_io.cli as fw_cli  # noqa: E402
from fw_io.parts import PEB, size_for  # noqa: E402
from fw_io.transport import (  # noqa: E402
    BLOCK, Transport, UsbError, release_device, retryable)

TMP = Path(__file__).resolve().parents[2] / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)


class FakeIn:
    def __init__(self, device):
        self.device = device

    def read(self, size, timeout=0):
        return self.device.pop_pending(size)


class FakeOut:
    def __init__(self):
        self.data = bytearray()

    def write(self, data, timeout=0):
        self.data.extend(data)
        return len(data)


class FakeReadDevice:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.pending = b""
        self.seq = 0
        self.epin = FakeIn(self)

    def pop_pending(self, size: int) -> bytes:
        chunk = self.pending[:size]
        self.pending = self.pending[size:]
        return chunk

    def ctrl_transfer(self, reqtype, request, value, index, data_or_len,
                      timeout=0):
        if reqtype == 0xC0 and request == 0x33:
            chunk = self.data[self.pos:self.pos + BLOCK]
            self.pos += len(chunk)
            self.pending = chunk
            header = struct.pack("<IIII", 0xEFE8, len(chunk), self.seq, 0)
            self.seq += 1
            return header
        raise AssertionError(f"неожиданный запрос {reqtype:#x}/{request:#x}")


class FakeWriteDevice:
    def __init__(self):
        self.controls = []
        self.epout = FakeOut()

    def ctrl_transfer(self, reqtype, request, value, index, data_or_len,
                      timeout=0):
        if reqtype == 0xC0 and request == 0x31:
            return b"success"
        if reqtype in (0x40,) and request in (0x30, 0x32):
            self.controls.append(bytes(data_or_len))
            return len(data_or_len)
        raise AssertionError(f"неожиданный запрос {reqtype:#x}/{request:#x}")

    def read(self, endpoint, size, timeout=0):
        return b"OK!!"


class FakeTransport(Transport):
    def __init__(self, device):
        super().__init__(device)
        self._epin = getattr(device, "epin", None)
        self._epout = getattr(device, "epout", None)
        self.commands = []

    def keepalive(self):
        pass

    def command(self, command, timeout=15000):
        self.commands.append(command)

    def endpoints(self):
        return self._epin, self._epout


class ReadPartition(unittest.TestCase):
    def test_read_two_blocks(self):
        data = bytes(range(256)) * (BLOCK // 256) * 2
        device = FakeReadDevice(data)
        transport = FakeTransport(device)
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            out = Path(tmp) / "part.bin"
            digest = transport.read_partition("system_b", len(data), out)
            self.assertEqual(out.read_bytes(), data)
            self.assertEqual(len(digest), 64)
            self.assertEqual(transport.commands,
                             [f"upload store system_b normal 0x{len(data):x}"])

    def test_refuses_existing(self):
        device = FakeReadDevice(b"\0" * BLOCK)
        transport = FakeTransport(device)
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            out = Path(tmp) / "part.bin"
            out.write_bytes(b"old")
            with self.assertRaises(FileExistsError):
                transport.read_partition("system_b", BLOCK, out)


class WritePartition(unittest.TestCase):
    def test_write_blocks_and_checksum(self):
        image = bytes(range(256)) * (BLOCK // 256) * 2
        device = FakeWriteDevice()
        transport = FakeTransport(device)
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            path = Path(tmp) / "image.bin"
            path.write_bytes(image)
            transport.write_partition("system_b", len(image), path)
        self.assertEqual(bytes(device.epout.data), image)
        self.assertEqual(len(device.controls), 3)  # download + 2 блока
        # controls[0] — download (0x30), далее две записи блоков (0x32)
        download = device.controls[0].rstrip(b"\0").decode()
        self.assertIn("download store system_b normal", download)
        blocks = device.controls[1:]
        self.assertEqual(len(blocks), 2)
        for seq, control in enumerate(blocks):
            tag, length, number, checksum, magic, extra = struct.unpack(
                "<IIIIHH", control[:20])
            self.assertEqual((tag, length, number, magic, extra),
                             (0, BLOCK, seq, 0xEF, 0x200))
            expected = sum(struct.unpack(
                "<16384I", image[seq * BLOCK:(seq + 1) * BLOCK])) & 0xFFFFFFFF
            self.assertEqual(checksum, expected)
        self.assertEqual(transport.commands,
                         ["disk_initial 0", "download get_status"])

    def test_size_mismatch(self):
        device = FakeWriteDevice()
        transport = FakeTransport(device)
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            path = Path(tmp) / "image.bin"
            path.write_bytes(b"\0" * BLOCK)
            with self.assertRaises(ValueError):
                transport.write_partition("system_b", BLOCK * 2, path)

    def test_size_not_multiple_of_block(self):
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            path = Path(tmp) / "image.bin"
            path.write_bytes(b"\0" * BLOCK)
            transport = Transport(object())
            with self.assertRaises(ValueError):
                transport.write_partition("system_b", BLOCK + 1, path)


class CliRead(unittest.TestCase):
    def test_existing_output_does_not_wait(self):
        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            out = Path(tmp) / "part.bin"
            out.write_bytes(b"old")
            with mock.patch.object(fw_cli, "wait_transport") as wait, \
                    redirect_stderr(io.StringIO()):
                code = fw_cli.main(["read", "--part", "system_b",
                                    "--out", str(out)])
            self.assertEqual(code, 1)
            wait.assert_not_called()

    def test_force_proceeds(self):
        class Fake:
            def read_partition(self, part, size, out, progress,
                               force=True, allow_short=False):
                Path(out).write_bytes(b"x")
                progress(1, 1)
                return "a" * 64

            def close(self):
                pass

        with tempfile.TemporaryDirectory(dir=TMP) as tmp:
            out = Path(tmp) / "part.bin"
            out.write_bytes(b"old")
            with mock.patch.object(fw_cli, "wait_transport",
                                   return_value=Fake()):
                code = fw_cli.main(["read", "--part", "system_b",
                                    "--out", str(out), "--force"])
            self.assertEqual(code, 0)
            self.assertEqual(out.read_bytes(), b"x")


class Sizes(unittest.TestCase):
    def test_known(self):
        self.assertEqual(size_for("system_b"), 64 * 1024 * 1024)
        self.assertEqual(size_for("data"), 620 * PEB)

    def test_unknown_needs_override(self):
        with self.assertRaises(ValueError):
            size_for("nope")
        self.assertEqual(size_for("nope", PEB), PEB)


class Retry(unittest.TestCase):
    def test_open_device_is_retryable(self):
        self.assertTrue(retryable(
            UsbError("USB-операция не поддержана: open_device")))

    def test_stage_error_is_not_retryable(self):
        self.assertFalse(retryable(
            UsbError("неподдерживаемый/заблокированный загрузчик: 00")))

    def test_usb_timeout_is_retryable(self):
        import usb.core
        self.assertTrue(retryable(usb.core.USBError("timeout")))

    def test_wait_retries_open_device(self):
        import fw_io.transport as transport_module

        class Flaky(Transport):
            attempts = 0

            def identify(self):
                type(self).attempts += 1
                if type(self).attempts == 1:
                    raise UsbError("USB-операция не поддержана: open_device")
                return bytes.fromhex("0007001000000000")

            def validate_identify(self, ident):
                pass

            def command(self, command, timeout=15000):
                pass

        with mock.patch("usb.core.find", return_value=[object()]), \
             mock.patch.object(transport_module, "make_backend",
                               return_value=None):
            transport = Flaky.wait(seconds=1, log=lambda text: None)
        self.assertIsInstance(transport, Flaky)
        self.assertEqual(Flaky.attempts, 2)

    def test_wait_stops_on_stage_error(self):
        import fw_io.transport as transport_module

        class Blocked(Transport):
            attempts = 0

            def identify(self):
                type(self).attempts += 1
                raise UsbError("неподдерживаемый/заблокированный загрузчик")

            def validate_identify(self, ident):
                pass

        with mock.patch("usb.core.find", return_value=[object()]), \
             mock.patch.object(transport_module, "make_backend",
                               return_value=None):
            with self.assertRaises(UsbError):
                Blocked.wait(seconds=5, log=lambda text: None)
        self.assertEqual(Blocked.attempts, 1)


class Close(unittest.TestCase):
    def test_release_device_finalizes_device_only(self):
        calls = []

        class Dev:
            def finalize(self):
                calls.append("dev")

        class Ctx:
            dev = Dev()
            backend = mock.Mock()

            def dispose(self, device):
                calls.append("dispose")

        device = mock.Mock()
        device._ctx = Ctx()
        release_device(device)
        self.assertEqual(calls, ["dispose", "dev"])
        Ctx.backend.finalize.assert_not_called()

    def test_close_order_and_references(self):
        calls = []

        class Dev:
            def finalize(self):
                calls.append("dev")

        class Backend:
            def finalize(self):
                calls.append("backend")

        class Ctx:
            dev = Dev()
            backend = Backend()

            def dispose(self, device):
                calls.append("dispose")

        device = mock.Mock()
        device._ctx = Ctx()
        transport = Transport(device)
        transport._epin = object()
        transport._epout = object()
        transport.close()
        self.assertEqual(calls, ["dispose", "dev", "backend"])
        self.assertIsNone(transport.device)
        self.assertIsNone(transport._epin)
        self.assertIsNone(transport._epout)

    def test_close_twice_is_safe(self):
        transport = Transport(mock.Mock())
        transport.device = None
        transport.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
