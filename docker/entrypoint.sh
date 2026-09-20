#!/bin/sh
set -eu
umask 022
if [ "$(id -u)" = 0 ]; then
    mkdir -p /app/data/media /app/data/logs /app/data/backups /app/staticfiles
    chown portal:portal /app/data /app/data/media /app/data/logs /app/data/backups /app/staticfiles
    exec gosu portal "$@"
fi
exec "$@"
