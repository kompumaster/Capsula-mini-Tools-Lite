#!/bin/sh
# ADB по TCP (порт 5555). USB-ADB в этой сборке нет.
BIN=/usr/bin/adbd-tcp
PORT=5555

start() {
    echo "Starting adbd..."
    ADB_TCP_PORT=$PORT "$BIN" &
}

stop() {
    echo "Stopping adbd..."
    killall adbd-tcp >/dev/null 2>&1
}

case "$1" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  *) echo "Usage: $0 {start|stop|restart}"; exit 1 ;;
esac
