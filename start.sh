#!/usr/bin/env bash
set -euxo pipefail

# Run load_and_merge_gribs.py once in background and schedule hourly updates
python3 /app/load_and_merge_gribs.py || true &
(crond -f &) &

# Start Flask server
exec python3 /app/server.py
