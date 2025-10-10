#!/usr/bin/env bash
set -euo pipefail

# Run process.sh once in background and schedule hourly updates
/app/process.sh || true &
(crond -f &) &

# Start Flask server
exec python3 /app/server.py
