# yse — пакетный менеджер Entware и .yap

`yse` — пакетный менеджер для Яндекс Станций (проект hackalice): ставит
пакеты из **Entware** (opkg) и из **.yap-реестров** на GitHub. Всё — в
`/data/opt`, системные файлы не трогает. Клиент — один shell-скрипт.

Источник: https://hackalice.me/start/packages/

Ассеты патча `yse` (toggle, раздел `data`): клиент, статический curl и
профиль PATH.

## Файлы

| Файл | Что |
|---|---|
| `yse` | клиент (shell), с фиксом `LD_LIBRARY_PATH` в `opkg()` |
| `curl` | статический curl (musl, mbedTLS), 1.6 МБ — для HTTPS-загрузок `.yap` |
| `yse_profile.sh` | профиль PATH (`/opt/bin`, `/data/opt/bin`) |

## Куда кладёт патч

| Ассет | На плате |
|---|---|
| `yse` | `/data/opt/bin/yse` |
| `curl` | `/data/opt/entware/bin/curl` (= `/opt/bin/curl`) |
| `yse_profile.sh` | `/etc/profile.d/yse.sh` |

Плюс симлинк `/opt` → `/data/opt/entware` (Entware пишет на `data`).

## Использование

```sh
ssh → yse bootstrap        # Entware (один раз, нужна сеть)
yse install gawk           # awk для .yap (в busybox колонки его нет)
yse install htop           # пакет из Entware
yse install yap:btop       # пакет из .yap-реестра GitHub
```

## Почему свой curl

Штатный Entware-`curl` в канале `aarch64-k3.10` сломан (собран под
glibc 2.28+, а `libc` там 2.27), а busybox-`wget` не умеет TLS. Поэтому
в патче лежит статический musl-curl на mbedTLS — он не зависит от glibc.

Также в `yse` из обёртки `opkg()` убран `LD_LIBRARY_PATH`: системная
glibc 2.33 обратно совместима с Entware-овской 2.27, а системный
busybox-`wget` (нужный `opkg`) ломается, получив `/opt/lib` (2.27).
