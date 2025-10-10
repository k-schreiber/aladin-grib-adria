#!/usr/bin/env bash
set -euo pipefail

echo "0 * * * * /app/process.sh >> /var/log/process.log 2>&1" > /etc/cron.d/gribproc
chmod 0644 /etc/cron.d/gribproc
crontab /etc/cron.d/gribproc

/app/process.sh || true &
(crond -f &) &

exec python3 /app/server.py
