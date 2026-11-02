#!/bin/sh
#
# SSH-сервер dropbear: пользователь capsula/mini -> root (зашито в бинарь).
#
KEYDIR=/data/dropbear_keys
BIN=/usr/bin/dropbear
KEYGEN=/usr/bin/dropbearkey

start() {
    mkdir -p "$KEYDIR"
    if [ ! -f "$KEYDIR/ed25519" ]; then
        "$KEYGEN" -t ed25519 -f "$KEYDIR/ed25519" >/dev/null 2>&1
    fi
    if [ ! -f "$KEYDIR/rsa" ]; then
        "$KEYGEN" -t rsa -s 2048 -f "$KEYDIR/rsa" >/dev/null 2>&1
    fi
    echo "Starting dropbear..."
    "$BIN" -r "$KEYDIR/ed25519" -r "$KEYDIR/rsa" -p 22 >>/data/dropbear.log 2>&1 &
}

stop() {
    echo "Stopping dropbear..."
    killall dropbear >/dev/null 2>&1
}

case "$1" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  *) echo "Usage: $0 {start|stop|restart}"; exit 1 ;;
esac
