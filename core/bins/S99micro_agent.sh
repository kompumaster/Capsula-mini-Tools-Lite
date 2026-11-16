#!/bin/sh
#
# micro_agent - оркестратор колонки.
# Установка: /etc/init.d/S99micro_agent.sh, права 755.
#
PROG=/home/microp/micro_agent/agent.py
LOGWRITER=/home/microp/micro_agent/log.py
PYTHON=/usr/bin/micropython
HEAPSIZE=32M
PIDFILE=/tmp/micro_agent.pid
LOGPIDFILE=/tmp/micro_agent_log.pid
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
        echo "micro_agent уже запущен (PID $(cat "$PIDFILE"))"
        return 0
    fi
    if pgrep -x voice-agent >/dev/null 2>&1; then
        echo "voice-agent запущен - micro_agent не стартует" >&2
        echo "остановите voice-agent (патч vkvoice)" >&2
        return 1
    fi

    echo "Запуск micro_agent, логи: $LOGDIR"
    start_writer

    i=0
    AGENT_PID=
    while [ "$i" -lt 20 ]; do
        AGENT_PID=$(pgrep -f "$PROG" | head -n 1)
        [ -n "$AGENT_PID" ] && break
        sleep 0.5
        i=$((i + 1))
    done
    if [ -z "$AGENT_PID" ]; then
        echo "micro_agent не запустился, смотрите $LOGDIR" >&2
        stop
        return 1
    fi
    echo "$AGENT_PID" >"$PIDFILE"
    return 0
}

stop() {
    AGENT=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$AGENT" ] && kill -0 "$AGENT" 2>/dev/null; then
        echo "Остановка micro_agent (PID $AGENT)"
        kill "$AGENT" 2>/dev/null
        i=0
        while [ "$i" -lt 20 ] && kill -0 "$AGENT" 2>/dev/null; do
            sleep 0.5
            i=$((i + 1))
        done
        if kill -0 "$AGENT" 2>/dev/null; then
            kill -9 "$AGENT" 2>/dev/null
        fi
    else
        echo "micro_agent не запущен"
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
        echo "micro_agent работает (PID $(cat "$PIDFILE"))"
        if writer_running; then
            echo "лог-ротатор работает (PID $(cat "$LOGPIDFILE"))"
        else
            echo "лог-ротатор не работает"
        fi
    else
        echo "micro_agent остановлен"
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
