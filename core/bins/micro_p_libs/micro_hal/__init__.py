"""micro_hal: доступ к оборудованию капсулы из MicroPython.

Слои:

- `hal_*` — только железо (sysfs, ioctl, `/dev/input`, Pulse);
- `lib_*` — логика поверх железа (шрифты, раскладка, эффекты).

Модули по устройствам:

- `hal_ring` / `lib_ring` — светодиодное кольцо;
- `hal_display` / `lib_display` — дисплей и часы;
- `hal_keys` / `lib_keys` — кнопки;
- `hal_mic` / `lib_mic` — микрофоны;
- `hal_speaker` / `lib_speaker` — динамик;
- `hal_light` — датчик света;
- `lib_ntp` — синхронизация времени по NTP;
- `hal_volume` / `lib_volume` — громкость;
- `hal_pulse` — поиск сокета Pulse (`PULSE_SERVER`);
- `hal_odas` / `lib_odas` — ODAS: процесс и JSON tracks.

Этот файл не импортирует их сразу: пакет должен открываться и на
CPython — для тестов чистой логики.
"""

from micro_hal.hal_common import HalError, check, format_check

__version__ = "0.2.0"

__all__ = ["HalError", "check", "format_check", "__version__"]
