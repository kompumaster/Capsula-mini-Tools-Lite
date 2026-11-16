# yse: PATH и HOME для пакетов Entware и .yap.
[ -d /data/opt/bin ] && PATH="/data/opt/bin:$PATH"
[ -d /opt/bin ] && PATH="/opt/bin:/opt/sbin:$PATH"
export PATH
export HOME=/data/opt/home; mkdir -p "$HOME" 2>/dev/null
[ -r /opt/etc/profile ] && . /opt/etc/profile
