#!/usr/bin/env bash
set -euxo pipefail

# Cron does not see the container's environment: hand the Copernicus credentials over for the water job
# (written before cron starts, readable by the owner only)
python3 - <<'PY'
import os, shlex
keep = {k: v for k, v in os.environ.items() if k == "OUTDIR" or k.startswith("COPERNICUSMARINE_SERVICE_")}
fd = os.open("/app/cron_env.sh", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("".join(f"export {k}={shlex.quote(v)}\n" for k, v in keep.items()))
PY

# Start cron daemon
cron

# Run both processors once in the background, then let cron schedule them
(python3 /app/load_and_merge_gribs.py || true) &
(python3 /app/local_update_water.py || true) &

# Start Flask server
exec python3 /app/server.py
