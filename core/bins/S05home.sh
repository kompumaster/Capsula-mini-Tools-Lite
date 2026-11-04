#!/bin/sh
# S05home: восстановить /home -> /data/permanent/home.
#
# Запускается после S02datamount и S04overlaymount, поэтому /data уже
# смонтирован, а / (overlay) доступен на запись. Скрипт лежит в
# system_b и переживает очистку overlay: после factory reset он снова
# создаёт симлинк, данные остаются в /data/permanent/home.
#
# Настоящий каталог /home не трогаем: если это не симлинк, выходим.

[ "$1" = "start" ] || exit 0

TARGET=/data/permanent/home

# Без смонтированного /data создавать ссылку нельзя: она попадёт
# в overlay и скроет будущий раздел.
grep -q " /data " /proc/mounts || exit 0

mkdir -p "$TARGET" || exit 1

if [ -e /home ] && [ ! -L /home ]; then
    exit 0
fi

rm -f /home
ln -s "$TARGET" /home
