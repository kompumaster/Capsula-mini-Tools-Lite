# MicroPython: путь импорта и временный каталог.
#
# Подключается из /etc/profile (каталог /etc/profile.d). Нужен, чтобы
# `micropython` видел встроенные модули прошивки: без `.frozen` нет
# `ssl` и Edge TTS не работает.
#
# Ставится патчем `mpython` в overlay раздела data:
# `/etc/profile.d/10-micropython.sh`.

if [ -z "$MICROPYPATH" ]; then
    MICROPYPATH=/home/microp:/usr/lib/micropython:.frozen
else
    case ":$MICROPYPATH:" in
        *:.frozen:*) ;;
        *) MICROPYPATH="$MICROPYPATH:.frozen" ;;
    esac
fi
export MICROPYPATH

# adb выставляет свой TMPDIR; не перетираем его.
[ -n "$TMPDIR" ] || TMPDIR=/tmp
export TMPDIR
