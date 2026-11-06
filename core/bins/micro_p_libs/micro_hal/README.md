# micro_hal: оборудование капсулы из MicroPython

Пакет для `/usr/bin/micropython` на колонке. Доступ к кольцу, дисплею,
кнопкам, микрофонам, динамику, громкости, датчику света, NTP, Bluetooth,
Wi-Fi и ODAS.

Состояние: готовы `hal_common`, `hal_pulse` (сокет Pulse), дисплей
(`hal_display`/`lib_display`, sysfs + C-транспорт), кольцо
(`hal_ring`/`lib_ring`), кнопки
(`hal_keys`/`lib_keys`), датчик света (`hal_light`), NTP (`lib_ntp`),
громкость (`hal_volume`/`lib_volume`), микрофоны
(`hal_mic`/`lib_mic`), ODAS (`hal_odas`/`lib_odas`), динамик
(`hal_speaker`/`lib_speaker`), Bluetooth (`hal_bt`/`lib_bt`) и Wi-Fi
(`hal_wifi`/`lib_wifi`); плюс точка доступа и портал
(`examples/ap_portal.py`).

## Два слоя

- `hal_*` — только железо: sysfs, ioctl, `/dev/input`, команды Pulse.
- `lib_*` — смысл: шрифты, раскладка, время, эффекты, комбинации.

`lib_*` может импортировать `hal_*`; обратное запрещено.

## Быстрый старт

На плате нет `scp`; файлы передаются через `ssh ... 'cat > ...'`:

```sh
# IP — адрес колонки в локальной сети
ssh capsula@IP 'mkdir -p /home/microp/micro_hal/bins'
for f in micro_hal/*.py; do
    ssh capsula@IP \
        "cat > /home/microp/micro_hal/$(basename $f)" < "$f"
done
ssh capsula@IP 'cat > /home/microp/micro_hal/bins/libc_ring.so' \
    < micro_hal/bins/libc_ring.so
ssh capsula@IP 'cat > /home/microp/micro_hal/bins/libc_display.so' \
    < micro_hal/bins/libc_display.so
ssh capsula@IP 'cat > /home/microp/micro_hal/bins/libc_mic.so' \
    < micro_hal/bins/libc_mic.so
ssh capsula@IP 'cat > /home/microp/micro_hal/bins/libc_speaker.so' \
    < micro_hal/bins/libc_speaker.so
```

ODAS ставится отдельно: `odaslive` →
`/data/overlay/upper/usr/bin/`, `libodas.so` → `/home/microp/`,
конфиги → `/home/microp/odas/`.

`libc_ring.so`, `libc_display.so`, `libc_mic.so` и
`libc_speaker.so` входят в рабочий комплект и ставятся в `bins/`
вместе с пакетом.

Обёртка `/home/microp/mp`:

```sh
#!/bin/sh
MICROPYPATH=/home/microp:/usr/lib/micropython \
    exec /usr/bin/micropython "$@"
```

Проверка без записи в железо:

```sh
/home/microp/mp -c "from micro_hal import format_check; print('\n'.join(format_check()))"
```

## Модули

| Устройство | Железо | Логика | Основные вызовы |
|---|---|---|---|
| Светодиодное кольцо | `hal_ring` | `lib_ring` | `fill`, `pixel`, `show` |
| Дисплей/часы | `hal_display` | `lib_display` | `text`, `clock`, `transition`, `colon` |
| Кнопки | `hal_keys` | `lib_keys` | `poll`, `wait`, `pressed` |
| Микрофоны | `hal_mic` | `lib_mic` | `hal_mic.Stream`, `MicStream`, `record`, `level` |
| Динамик | `hal_speaker` | `lib_speaker` | `tone`, `melody`, `play`, `stop` |
| Громкость | `hal_volume` | `lib_volume` | `get`, `set`, `up`, `down`, `mute` |
| Bluetooth | `hal_bt` | `lib_bt` | `enable`, `status`, `audio`, `volume` |
| Датчик света | `hal_light` | — | `available`, `read`, `lux` |
| Wi-Fi | `hal_wifi` | `lib_wifi` | `status`, `scan`, `connect`, `saved` |
| NTP | — | `lib_ntp` | `query`, `scan`, `sync` |
| ODAS | `hal_odas` | `lib_odas` | `start`, `stop`, `tracks`, `pots`, `categories`, `separated` |

Все модули железа готовы; точка доступа и портал — `examples/ap_portal.py`.
Сокет Pulse общий для звука: его ищет `hal_pulse` (см. «Pulse»).

## Дисплей

```python
from micro_hal import lib_display

lib_display.text("12:34")          # цифры и обе точки
lib_display.clock()                # текущее время, 24 ч, ведущий ноль
lib_display.clock(blink=True, off_ms=250)  # точки: 250 мс off, 750 мс on
lib_display.transition("1234", "1235")     # старые цифры гаснут, новые загораются
lib_display.pulse("1234", seconds=0.9)     # ярко зажечь и погасить за 0,9 с
lib_display.colon_fade(seconds=1.0)        # точки плавно гаснут
lib_display.colon(top=True, bottom=False)
lib_display.text("1234", colon=False, value=100)
```

Низкий уровень:

```python
from micro_hal import hal_display

hal_display.set(0, 100)            # физический канал 0…29
hal_display.raw([...30 значений...])
hal_display.clear()
hal_display.scale(50)              # проценты от текущего
hal_display.probe()                # по одному каналу, с паузой
```

`lib_display.frame("1234")` возвращает 30 физических значений без записи —
удобно для тестов. `lib_display.raw_logical(values)` пишет кадр в
стоковом порядке (как в JSON-анимациях).

`transition(old, new, fade_out=1.0, fade_in=1.0, steps=20)` плавно
меняет только различающиеся сегменты: старые гаснут, новые
загораются; общие остаются. `colon=None` сохраняет текущее состояние
точек, `True`/`False`/пара задаёт их.

`pulse(string, seconds=1.0, steps=20)` показывает кадр на полной
яркости и плавно гасит до нуля за `seconds`; в конце дисплей погашен.

Запись `hal_display.raw/set/clear/scale` идёт одним ioctl через
`libc_display.so`; `get` читает sysfs. Библиотека ставится вместе с
пакетом; без неё `raw` даёт `HalError`.

## Яркость

```python
lib_display.brightness(60)                 # 0…100, запоминается
lib_display.brightness(60, gamma=True)     # кривая как в стоке
lib_display.get_brightness()               # 60
lib_display.get_gamma()                    # True/False
lib_display.level()                        # значение сегмента 0…153

lib_display.text("12:34")                  # применит текущую яркость
lib_display.text("1234", value=100)        # явная яркость, без глобальной
```

- линейный режим: `153 * percent / 100`;
- `gamma=True` — стоковая формула
  `round(255 * pow(percent*0.62862504/100 + 0.2514867, 4))`,
  при `percent = 0` — 0;
- по умолчанию `100 %` → `153`;
- `text`, `clock`, `colon` используют глобальную яркость, `value=`
  перекрывает её;
- `demo_stock` масштабирует кадры на текущую яркость
  (`scale=False` отключает).

Плавные анимации (например, затухание цифр при смене минуты) —
`libc_display.so`: дисплей пишет через C, sysfs остаётся для
чтения (`get`) и диагностики; библиотека ставится вместе с пакетом.

Шрифт, раскладка и перестановка взяты из `voice-agent`; порядок
`clock-ledN`, ориентация цифр и двоеточие проверены на плате.
Пример часов — `examples/display_clock.py`.

## Кольцо

```python
from micro_hal import hal_ring

ring = hal_ring.Ring()
ring.pixel(0, (255, 0, 0))
ring.fill((0, 0, 0))
ring.brightness(128)       # 0…255
ring.show()
ring.off()
ring.close()
```

- 12 пикселей, 36 каналов;
- пиксель 0 — 12 часов (сзади, у провода питания), далее по часовой
  стрелке;
- цвета RGB, перестановка и яркость — в `hal_ring`;
- `pixel`/`fill` меняют буфер, `show()` отправляет кадр;
- `clear()` только гасит буфер, `off()` — гасит и отправляет;
- кадр лежит в C-буфере `libc_ring.so`; Python заполняет его через
  `ffi.as_bytearray`. Прямой Python-буфер в `ring_write` не работает
  (`EINVAL`).

Эффекты — в `lib_ring`:

```python
from micro_hal import lib_ring

lib_ring.rainbow(ring, cycles=1, delay=0.02)
lib_ring.breathe(ring, (0, 0, 255), cycles=2)
lib_ring.comet(ring, (255, 0, 0), tail=4)
lib_ring.theater_chase(ring, (0, 255, 0))
lib_ring.color_wipe(ring, (0, 0, 255))
lib_ring.static(ring, (255, 0, 0))
lib_ring.blink(ring, (0, 255, 0))
lib_ring.fade(ring, (255, 0, 0))
lib_ring.twinkle(ring, (255, 255, 0))
lib_ring.sparkle(ring, (255, 0, 255))
lib_ring.larson_scanner(ring, (255, 0, 0))
lib_ring.bicolor_chase(ring, (255, 0, 0), (0, 0, 255))
lib_ring.tricolor_chase(ring, ((255, 0, 0), (0, 255, 0), (0, 0, 255)))
lib_ring.running_lights(ring, (255, 0, 0), (0, 0, 255))
lib_ring.fire_flicker(ring)
```

Все эффекты блокирующие; `delay` задаёт паузу между кадрами.
Примеры — `examples/ring_demo.py` и
`examples/ring_running_lights.py`.

## Кнопки

```python
from micro_hal import hal_keys, lib_keys

device = hal_keys.KeysDevice()          # csk05t, event0
keys = lib_keys.Keys(device=device)

while True:
    for name, action, count in keys.poll(100):
        print(name, action, count)
```

События: `press`, `release`, `click`, `single`, `double`, `triple`,
`hold`, `step`, `combo`, `combo_hold`, `combo_release`.

Сочетания: `vol-+vol+` (114+115), `play+vol+` (164+115),
`play+vol-` (164+114). Пока сочетание активно, одиночные события
его клавиш не выдаются. `count` — число кликов, номер шага или 0.

Тайминги по умолчанию: debounce 40 мс, hold 600 мс, click 350 мс,
combo 100 мс, step 150 мс.

`wait()` не теряет события: если один `poll()` дал `click` и `single`,
первый `wait()` вернёт `click`, следующий — `single`.

Пример — `examples/keys_demo.py`.

## Датчик света

```python
from micro_hal import hal_light

hal_light.available()   # есть ли файл
hal_light.read()        # люксы, float
hal_light.lux()         # то же, что read()
```

Драйвер BH1730FVC отдаёт готовые люксы; `clear_raw`/`ir_raw` —
только диагностика. Кэша нет, ошибки — `HalError`.

## NTP

```python
from micro_hal import lib_ntp

lib_ntp.scan()                  # все серверы, быстрые первыми
lib_ntp.cached()                # лучший за сессию
lib_ntp.query()                 # выбрать самому
lib_ntp.query(server="ntp.msk-ix.ru")
lib_ntp.sync()                  # поставить время (root)
lib_ntp.get_timezone()          # "Europe/Moscow"
lib_ntp.set_timezone("Europe/Moscow")  # root
```

Серверы: Москва (ВНИИФТРИ, MSK-IX, ru.pool), затем регионы и
`pool.ntp.org`; порог 150 мс. Время ставится в UTC через
`date -u -s`, пояс +3 берётся из `/etc/localtime`. Лучший сервер
запоминается до конца процесса.

## ODAS

```python
from micro_hal import hal_odas, lib_odas

server = lib_odas.Server()
server.listen()          # сначала сервер
hal_odas.start()         # потом odaslive
server.poll(100)
server.tracks()          # список треков
server.direction()       # азимут/возвышение
server.close()
hal_odas.stop()
```

`odaslive` — отдельный демон. При `start(verbose=True)` его вывод
пишется в `/tmp/micro_hal_odas.<pid>.log`; без `verbose` — в
`/dev/null`, чтобы не занимать RAM. Выходы:
`tracks` — JSON на `9000`, `pots` — JSON на `9001`,
`categories` — JSON на `9004`; `sss.separated`/`postfiltered` —
PCM на `9002`/`9003` (через `lib_odas.AudioServer`). Занятый порт —
`HalError` с номером порта, сокет при этом закрывается. Азимут: `0°` — спереди,
`+90°` — справа, `−90°` — слева. Пример трекинга —
`examples/odas_tracking.py`.

## Pulse

`hal_pulse` находит сокет Pulse и подставляет `PULSE_SERVER` в
команды `pactl`, `pacat`/`paplay` и `parec`; задавать переменную
вручную не нужно.

```python
from micro_hal import hal_pulse

hal_pulse.server()   # "unix:/tmp/pulse-…/native" или None
hal_pulse.prefix()   # "PULSE_SERVER='…' " для shell-команд
hal_pulse.forget()   # сбросить кэш поиска
```

Порядок поиска: заданный `PULSE_SERVER` → `$XDG_RUNTIME_DIR/pulse/native`
→ `/run/user/*/pulse/native` → самый свежий `/tmp/pulse-*/native`.
Найденный путь кэшируется и перепроверяется: исчез — ищем заново.
В MicroPython переменная читается из `/proc/self/environ`, потому что
`os.environ` там нет.

## Громкость

```python
from micro_hal import hal_volume, lib_volume

hal_volume.sinks()
hal_volume.default_sink()          # "master"
hal_volume.get_percent("master")   # 0…100
hal_volume.set_percent("master", 50)
hal_volume.toggle_mute("master")

volume = lib_volume.Volume("master", step=5)
volume.up() / volume.down()
volume.muted() / volume.mute() / volume.unmute()
```

`pactl` управляет Pulse; `ntp-ibb-volume-syncer` повторяет за ним в
ALSA `TV-Set`. `PULSE_SERVER` подставляется автоматически
(`hal_pulse`). Пример с кнопками — `examples/volume_demo.py`.

## Динамик

```python
from micro_hal import lib_speaker

lib_speaker.tone(1000, 1.0)                    # тон 1 кГц, 1 с
lib_speaker.tone(440, 0.5, sink="alarm")       # другой sink
lib_speaker.silence(0.3)                       # пауза
lib_speaker.melody([(523, 200), (0, 100), (784, 300)])
lib_speaker.play_wav("/home/microp/voice.wav") # готовый WAV
lib_speaker.play_wav("/home/microp/voice.wav", wait=True)  # ждать конца
lib_speaker.play_pcm(pcm, rate=24000)          # PCM из памяти
lib_speaker.play_raw("/tmp/a.raw", rate=16000) # готовый s16le
lib_speaker.write_wav("/tmp/a.wav", pcm, rate=16000)
with lib_speaker.stream(rate=24000) as out:    # поток кусками
    out.write(chunk)
lib_speaker.set_volume(30)                     # громкость и mute
lib_speaker.get_volume()
lib_speaker.mute(True) / lib_speaker.toggle_mute()
lib_speaker.pause() / lib_speaker.resume() / lib_speaker.paused()
lib_speaker.stop()                             # оборвать
lib_speaker.playing()                          # PID или None
```

`lib_speaker` — фасад для проекта: подтягивает `hal_pulse`,
`hal_speaker`, `hal_volume`, `lib_volume` и `lib_wav`, поэтому
достаточно импортировать только его.

Низкий уровень:

```python
from micro_hal import hal_speaker

hal_speaker.sinks()            # ["alsa_playback", "alarm", …]
hal_speaker.default_sink()     # "master"
hal_speaker.play("/tmp/a.raw", sink="master", raw=True,
                 rate=16000, channels=1)
hal_speaker.running()          # PID или None
hal_speaker.wait(10.0)         # дождаться конца
hal_speaker.stop()
```

- sink'и: `master` (по умолчанию), `alarm`, `ring`, `call`,
  `alsa_playback`, `snapcast`; все `s16le 2ch 48000Hz`;
- `paplay` на плате — симлинк на `pacat`: WAV играет по имени
  `paplay`, сырой поток — `pacat --raw`;
- тон и мелодия генерируются в C (`libc_speaker.so`): 16 кГц, моно,
  `s16le`, Pulse ресемплирует; огибающая 10 мс на краях и на каждой
  ноте — без щелчков;
- без библиотеки работает Python-реализация (эталон для сверки),
  но примерно в 20 раз медленнее;
- громкость — отдельно, `lib_volume`; 100 % — максимум;
- `pacat`/`paplay` получают `PULSE_SERVER` от `hal_pulse`;
- `pacat` стартует ~0,15 с, поэтому длительность чуть больше
  номинала; `wait()` возвращается после конца;
- `play_wav(wait=True)` блокируется до конца WAV любой длины
  (`hal_speaker.wait(None)`), `wait=False` — не ждёт.

Поток PCM — `hal_speaker.Stream` (FIFO, память ограничена буфером):

```python
from micro_hal import hal_speaker

with hal_speaker.Stream(rate=24000, channels=1) as out:
    for chunk in chunks:
        out.write(chunk)          # блокируется по мере слива
```

- `open()` создаёт FIFO `/tmp/micro_hal_spk.<pid>.fifo` и запускает
  `pacat`, читающий из него; `write()` принимает `s16le` кратными
  2 байтам;
- `close()` закрывает FIFO, ждёт слива (до 5 с) и убирает файл;
  `stop()` обрывает сразу;
- пауза — `hal_speaker.pause()` / `resume()` / `paused()`:
  `pactl suspend-sink <sink>` (в pactl 16.1 нет
  `suspend-sink-input`), поэтому пауза действует на весь sink.

Пример — `examples/speaker_demo.py` (тоны, мелодия, пауза, `stop`);
поток, PCM и файлы — `examples/speaker_stream_demo.py`.

## Bluetooth

```python
from micro_hal import lib_bt

lib_bt.enable()          # power on, модуль BlueZ, колонка видна
lib_bt.status()          # enabled, visible, device, source, audio, volume
lib_bt.devices()         # сопряжённые и подключённые
lib_bt.connect("AA:BB:CC:DD:EE:FF")
lib_bt.forget("AA:BB:CC:DD:EE:FF")   # удалить сопряжение
lib_bt.trust_paired()    # доверять всем сопряжённым (после нового)
lib_bt.audio_start()     # звук телефона → master
lib_bt.mute(True)        # временно снять звук телефона
lib_bt.volume(30)        # отдельная громкость телефона, 0…100
lib_bt.disable()         # снять звук, скрыть, power off
```

- по умолчанию Bluetooth **выключен**; `enable()` включает и делает
  колонку видимой (`Discoverable`/`Pairable`), `disable()` —
  наоборот;
- A2DP Sink поднимает Pulse (`module-bluez5-discover`): телефон
  приходит **источником** `bluez_source.<MAC>.a2dp_source`, а на
  динамик его выводит `module-loopback` на `master`;
- агент сопряжения не нужен: **новое** сопряжение проходит без
  агента, но BlueZ создаёт устройство с `Trusted=false`, и первое
  подключение A2DP отклоняется (`Access denied`). После сопряжения
  вызовите `connect(address)` (он сам ставит `Trusted`) или
  `trust_paired()`;
- `mute()` глушит только звук телефона и не рвёт A2DP — удобно на
  время системного сообщения (`lib_speaker` играет в `master`);
- `volume()` — громкость телефона, отдельная от `master`;
- телефонная книга (PBAP) не поднимается: `bluetoothd` запущен с
  `--plugin=a2dp,avrc`;
- HFP (звонки) не поддерживается — нет `oFono`.

Пример — `examples/bt_demo.py`.

## Wi-Fi

```python
from micro_hal import lib_wifi

lib_wifi.status()          # ssid, state, ip, freq, signal
lib_wifi.scan()            # кэш; scan(fresh=True) — свежий
lib_wifi.saved()           # сохранённые SSID
lib_wifi.connect("HOME", "пароль")   # рвёт канал: есть сторож и откат
lib_wifi.forget("TEST")    # текущую сеть удалять нельзя
lib_wifi.disconnect(allow=True)
```

- управление — `wpa_cli` и `dhcpcd`; `iw`/`iwconfig` на плате нет;
- тип защиты берётся из флагов скана: открытая (`NONE`),
  WPA/WPA2 (`WPA-PSK`), WPA3 (`SAE`); переходный WPA2+WPA3 — через
  `WPA-PSK`; `EAP`/`802.1X` и `WEP` — `HalError`;
- `hidden=True` включает `scan_ssid=1` (иначе скрытый SSID не
  находится); тип защиты для скрытой сети задаётся явно:
  `connect(..., hidden=True, key_mgmt="SAE")`;
- если SSID нет в кэше скана, `connect()` делает один свежий скан
  (3 с); если радио занято (`FAIL-BUSY`), перечитывает кэш;
- `connect()` **до** переключения запускает сторож
  (`/tmp/micro_hal_wifi_guard.sh`): если новая сеть не поднимется за
  `timeout` (60 с), он вернёт прежнюю; `save_config` — только после
  успеха;
- при откате `guard_ok()` ставится только когда поднялась именно
  прежняя сеть (`status().id`/`ssid` + `COMPLETED`), а не любой
  `COMPLETED`;
- `connect()` берёт `lock("wifi")` на всё переключение: второй процесс
  получает `HalError("ресурс wifi занят…")`; у сторожа есть токен, так
  что сторож прошлого подключения не откатит новый сеанс;
- повторный `connect()` к уже настроенной сети (но не `COMPLETED`)
  делает `reconnect` без новой записи; результат содержит
  `saved: True/False` (`False` — конфиг не сохранился, сеть работает);
- `forget()`/`disconnect()` берут тот же замок;
- текущую сеть библиотека не трогает, `forget()` её запрещает;
- `disconnect()` без `allow=True` бросает `HalError`;
- проверено на железе: подключение к выдуманной сети → обрыв 13,9 с
  → откат вернул прежнюю сеть и адрес, конфиг не изменился;
- точка доступа и captive portal — `examples/ap_portal.py`:
  `hostapd` на `p2p0`, `dnsmasq` с DHCP, страница на `10.0.0.1:80`;
  `/stopap` сначала отдаёт страницу, затем гасит AP (иначе ответ
  теряется вместе с адресом);
- `start_ap()` проверяет коды `hostapd`/`ip`/`dnsmasq` и возвращает
  текст ошибок; `_ap_running()` требует оба процесса и адрес
  `10.0.0.1` — портал показывает проблему на странице.

Пример — `examples/wifi_demo.py`.

## Микрофоны

```python
from micro_hal import hal_mic, lib_mic

hal_mic.sources()
hal_mic.available("mics")
lib_mic.record("/home/microp/voice.wav", 3)

data = open("/home/microp/voice.wav", "rb").read()[44:]
lib_mic.level(data)          # общий RMS 0…1
lib_mic.levels(data)         # по каналам
lib_mic.mono(data)           # s16le моно
```

`mics` — 4 канала / 16 кГц / s16le. Внутри `parec` запускается с
`--no-remap`: без него Pulse отдаёт нули. Запись идёт фоновым
процессом, PID хранится в `/tmp/micro_hal_mic.<pid>.pid`.

Непрерывный захват — C-хелпер `libc_mic.so` из `bins/`:
`mic_open(source, rate, channels, window_ms, settle_ms)`, `mic_read`
по окну 20 мс, `mic_mono`, `mic_stats`.

- `channels=4` — сырьё `aux0…aux3` (эквивалент `parec --no-remap`);
- `channels=1` — Pulse сводит 4 → 1 (среднее, как
  `pulse:mics/16000/1` у стока);
- `settle_ms` отбрасывает оседание постоянной составляющей после
  старта (около секунды); уровни считаются по переменной части.

`parec --channels=1 --no-remap` — это **только `aux0`**, не микс.

Непрерывный поток:

```python
from micro_hal import lib_mic

mic = lib_mic.MicStream(channels=1, ring_seconds=2.0)
mic.open()
for chunk in mic.chunks():
    level = mic.level()          # dBFS текущего окна
    raw = mic.read_raw()         # сырое окно последнего read()
    data, first = mic.snapshot(0.5)   # последние 0,5 с моно
mic.close()
```

`read()` отдаёт моно-кусок (20 мс), кольцо хранит последние
`ring_seconds`, `snapshot()` — пре-ролл. VAD, тишины и границ фраз
здесь нет — это дело вызывающего.

В C счётчик кадров 64-битный, наружу отдаётся `int` с насыщением
(`INT32_MAX`): после очень долгого захвата `frames()` не уходит в
минус.

Долгие записи в файлы на колонке не храним: ~100 МБ RAM и ~70 МБ
раздела, `record()` — только короткая отладка.

Пример — `examples/mic_demo.py`: полоска dBFS каждые 200 мс,
аргументы «каналы» и «секунды», по выходу сводка и размер кольца.

Направление и треки — через ODAS:

```python
from micro_hal import hal_odas, lib_mic

lib_mic.open_odas()          # слушать все выходы до запуска
hal_odas.start()
lib_mic.wait_ready(5.0)      # первые кадры ~ через 2,2 с
lib_mic.direction()          # {"azimuth", "elevation", "activity", "id"}
lib_mic.tracks()             # список треков
lib_mic.close_odas()
hal_odas.stop()
```

Набор выходов фиксируется при открытии: если ODAS уже открыт без
SSS, а нужен SSS (или наоборот), будет `HalError` — сначала
`close_odas()`.

Разделение (SSS):

```python
from micro_hal import lib_odas

server = lib_odas.AudioServer(port=lib_odas.POSTFILTERED_PORT)
server.listen()                     # до hal_odas.start(SSS_CONFIG)
chunk = server.latest()
index = server.pick(lib_mic.tracks())   # канал активного источника
data = server.channel(index)            # PCM одного источника
```

## `hal_common`

| Функция | Что делает |
|---|---|
| `exists(path)` | есть ли путь |
| `read_text(path)` / `write_text(path, text)` | файл целиком |
| `quote(path)` | путь в кавычках для shell |
| `run(command)` | `os.system`, код 0…255 |
| `capture(command)` | `(код, stdout+stderr)` через файл с PID процесса |
| `is_root()` / `require_root()` | проверка root |
| `va_pids()` / `va_running()` | процессы `voice-agent` |
| `require_va_stopped(what)` | `HalError`, если VA жив |
| `stop_va()` / `start_va()` | `S97voice-agent.sh stop/start`; только явно |
| `display_channels()` | число `clock-led*` в sysfs |
| `check()` / `format_check()` | состояние без записи в железо |
| `lock(name)` / `locked(name)` | замок на ресурс: каталог с PID, `HalError`, если занято |
| `processes()` | список `(pid, cmdline)` для поиска осиротевших процессов |
| `stale_owner(pid, prefix)` | есть ли у процесса pid-файл с мёртвым владельцем |

Ресурсы с одним владельцем: `display`, `ring`, `keys`, `mic`
(файловая запись), `odas`. Замок берётся при открытии и снимается
в `close()`/`stop()`/`forget()`, а также при ошибке инициализации;
второй процесс получает
`HalError("ресурс … занят процессом N")`. Потоковые микрофоны
(`MicStream`) и воспроизведение делятся через Pulse.

Пустой каталог замка без `pid` считается занятым первые 10 секунд
(процесс мог умереть между `mkdir` и записью pid) — одинаково для
`lock()` и `locked()`; после этого он устаревший и перехватывается.

`running()` в `hal_mic`, `hal_speaker` и `hal_odas` находит и
осиротевший процесс: `parec`/`pacat` помечены
`--client-name=micro_hal-mic`/`micro_hal-spk`, `odaslive` ищется по
`-c`; процесс считается своим, только если его pid-файл остался от
мёртвого владельца. `stop()` его останавливает, живого владельца не
трогает.

Пути и константы: `DEV_TOP_LEDS`, `DEV_INPUT`, `SYSFS_LEDS`,
`SYSFS_LIGHT`, `VA_INIT`, `MIC_BINS`, `SPK_BINS`, `CAPTURE`.

## Конфликт с voice-agent

`voice-agent` владеет кольцом, дисплеем, кнопками и звуком. Пока он
запущен, наша запись живёт недолго, а кнопки обрабатываются дважды.

Перед работой с UI:

```sh
/etc/init.d/S97voice-agent.sh stop
```

`hal_display` сам проверяет это при первом обращении и бросает
`HalError`. `stop_va()` вызывается только явно.

Остановка VA может оставить watchdog взведённым
(`watchdog0: watchdog did not stop!`), и плата перезагрузится без
пинга. После тестов сразу возвращайте VA:

```sh
/etc/init.d/S97voice-agent.sh start
```

## Установка

`/data/permanent` переживает factory reset; overlay — нет.

Без обёртки `mp`:

```python
import sys
sys.path.append("/home/microp")
from micro_hal import lib_display
```

## Правила для новых модулей

- `hal_<устройство>.py` — железо, `lib_<устройство>.py` — логика;
- при импорте ничего не открывать и не писать;
- `ffi` и прочие системные библиотеки импортировать внутри функции;
- ошибки — `HalError`, тексты по-русски;
- общие проверки — из `hal_common`;
- чистую логику тестировать на хосте, без платы.

## Тесты

Тесты идут на CPython, без платы и без настоящего Pulse — 677 штук.
На колонке пакет разворачивается в `/home/microp/micro_hal`.

## Благодарности

- [GyverButton](https://github.com/GyverLibs/GyverButton) — идеи
  обработки кнопок: дебаунс, удержание, клики, автоповтор.
- [WS2812FX](https://github.com/kitesurfer1404/WS2812FX) — идеи
  эффектов для светодиодного кольца.

Ссылки — справочные; код библиотек в проект не копируется.
