#!/usr/bin/env bash
set -euxo pipefail

# Start cron daemon
cron

# Cron does not see the container's environment: hand the Copernicus credentials over for the water job
python3 - <<'PY'
import os, shlex
keep = {k: v for k, v in os.environ.items() if k == "OUTDIR" or k.startswith("COPERNICUSMARINE_SERVICE_")}
with open("/app/cron_env.sh", "w") as f:
    f.write("".join(f"export {k}={shlex.quote(v)}\n" for k, v in keep.items()))
os.chmod("/app/cron_env.sh", 0o600)
PY

# Run both processors once in the background, then let cron schedule them
(python3 /app/load_and_merge_gribs.py || true) &
(python3 /app/local_update_water.py || true) &

# Start Flask server
exec python3 /app/server.py
