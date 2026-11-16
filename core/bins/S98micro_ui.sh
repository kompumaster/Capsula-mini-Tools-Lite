#!/bin/sh
#
# micro_ui — дисплей и кольцо отдельным процессом.
# Установка: /etc/init.d/S98micro_ui.sh, права 755.
#
# UI владеет /dev/is31fl32xx и /dev/topleds. Не запускать одновременно
# с micro_agent, пока агент использует локальный UI.
#
PROG=/home/microp/micro_ui/main.py
LOGWRITER=/home/microp/micro_ui/log.py
PYTHON=/usr/bin/micropython
HEAPSIZE=16M
PIDFILE=/tmp/micro_ui.pid
LOGPIDFILE=/tmp/micro_ui_log.pid
LOGDIR=/home/microp/logs

export MICROPYPATH=/home/microp:/usr/lib/micropython:.frozen
export PYTHONUNBUFFERED=1

mkdir -p "$LOGDIR"

read_pid() {
    [ -f "$1" ] || return 1
    PID=$(cat "$1" 2>/dev/null)
    [ -n "$PID" ] || return 1
    kill -0 "$PID" 2>/dev/null
}

running() {
    read_pid "$PIDFILE"
}

writer_running() {
    read_pid "$LOGPIDFILE"
}

start_writer() {
    if writer_running; then
        return 0
    fi
    rm -f "$LOGPIDFILE"
    "$PYTHON" -X "heapsize=$HEAPSIZE" "$PROG" 2>&1 | \
        "$PYTHON" "$LOGWRITER" "$LOGDIR" \
        >/dev/null 2>&1 &
    echo $! >"$LOGPIDFILE"
    return 0
}

start() {
    if running; then
        echo "micro_ui уже запущен (PID $(cat "$PIDFILE"))"
        return 0
    fi
    echo "Запуск micro_ui, логи: $LOGDIR"
    start_writer

    i=0
    UI_PID=
    while [ "$i" -lt 20 ]; do
        UI_PID=$(pgrep -f "$PROG" | head -n 1)
        [ -n "$UI_PID" ] && break
        sleep 0.5
        i=$((i + 1))
    done
    if [ -z "$UI_PID" ]; then
        echo "micro_ui не запустился, смотрите $LOGDIR" >&2
        stop
        return 1
    fi
    echo "$UI_PID" >"$PIDFILE"
    return 0
}

stop() {
    UI=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$UI" ] && kill -0 "$UI" 2>/dev/null; then
        echo "Остановка micro_ui (PID $UI)"
        kill "$UI" 2>/dev/null
        i=0
        while [ "$i" -lt 20 ] && kill -0 "$UI" 2>/dev/null; do
            sleep 0.5
            i=$((i + 1))
        done
        if kill -0 "$UI" 2>/dev/null; then
            kill -9 "$UI" 2>/dev/null
        fi
    else
        echo "micro_ui не запущен"
    fi

    WRITER=$(cat "$LOGPIDFILE" 2>/dev/null)
    if [ -n "$WRITER" ] && kill -0 "$WRITER" 2>/dev/null; then
        kill "$WRITER" 2>/dev/null
    fi
    rm -f "$PIDFILE" "$LOGPIDFILE"
    return 0
}

status() {
    if running; then
        echo "micro_ui работает (PID $(cat "$PIDFILE"))"
        if writer_running; then
            echo "лог-ротатор работает (PID $(cat "$LOGPIDFILE"))"
        else
            echo "лог-ротатор не работает"
        fi
    else
        echo "micro_ui остановлен"
        return 1
    fi
}

case "$1" in
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 1; start ;;
    status) status ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
