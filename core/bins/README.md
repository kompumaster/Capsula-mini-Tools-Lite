# bins: бинарники Lite

| Файл | Что | Размер | SHA-256 |
|---|---|---:|---|
| `dropbearmulti` | SSH: `dropbear`, `dropbearkey`, `scp`, `dbclient` в одном файле | 331 264 | `c4cbdd18…` |
| `adbd` | ADB, порт 5555, glibc 2.33 + libstdc++ 10 | 1 709 704 | `2afe9c0a…ad23` |
| `micropython/micropython` | MicroPython, AArch64/glibc 2.33, куча GC 8 МБ | 921 072 | `d674c703…8f258` |
| `net/hostapd` | hostapd 2.9 для AP, nl80211 | 595 424 | `f32ec902…` |
| `net/dnsmasq` | dnsmasq 2.90 с DHCP | 338 176 | `4a4286a5…` |
| `S05home.sh` | подключить `/data/permanent/home` как `/home` | 979 | `aac7e2b1…` |
| `micropython_env.sh` | `/etc/profile.d/10-micropython.sh`: `MICROPYPATH` с `.frozen`, `TMPDIR` | 793 | `951c6ee9…` |
| `micro_p_libs/micro_hal/` | HAL: py + examples + `bins/` с `.so` | 636K | см. `SHA256SUMS` |
| `micro_p_libs/micro_tts/` | TTS: пакет и `bins/edge_token`, `bins/libc_*.so` | 432K | см. `SHA256SUMS` |
| `micro_p_libs/micro_asr/` | ASR: пакет и `bins/libc_mp3.so` | 220K | см. `SHA256SUMS` |
| `micro_p_libs/micro_server/` | веб-портал: страница `:8080`, `/api/status` | 100K | см. `SHA256SUMS` |

Дефолтная куча GC у `micropython` — 8 МБ: в исходнике правится
`ports/unix/main.c` (`long heap_size = 8 * 1024 * 1024;`), запуск с
`-X heapsize=...` по-прежнему переопределяет. На AArch64 прежний
дефолт был 2 МБ.

## Ссылки

- Dropbear: https://github.com/mkj/dropbear
- adbd: https://android.googlesource.com/platform/packages/modules/adb/
- MicroPython: https://github.com/micropython/micropython
- UbiTar: https://github.com/kompumaster/UbiTar
- mtd-utils-tar: https://github.com/kompumaster/mtd-utils-tar
