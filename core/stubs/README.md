# stubs: заглушки-пустышки

Две статические AArch64-заглушки без libc:

| Файл | Исходник | Код выхода |
|---|---|---:|
| `noop` | `noop.S` | 0 |
| `noop1` | `noop1.S` | 1 |

## Сборка

```sh
aarch64-linux-gnu-gcc -nostdlib -static -s -Wl,--build-id=none \
  -o noop noop.S
aarch64-linux-gnu-gcc -nostdlib -static -s -Wl,--build-id=none \
  -o noop1 noop1.S
```
