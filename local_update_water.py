#!/usr/bin/env python3
"""Self-hosted container: build the water GRIB when Copernicus has new data (run by cron every 15 minutes).

Same rule as the workflow: check_marine.py decides, a key file in OUTDIR remembers the last build.
Needs COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD; without them it only logs.
"""
import os
import shutil
import sys

import check_marine
import marine_grib

OUTDIR = os.environ.get("OUTDIR", "/data")
KEY_FILE = ".water_key"
KEEP = 4  # timestamped water files to keep


def read_key(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def prune(outdir, keep=KEEP):
    files = sorted(f for f in os.listdir(outdir)
                   if f.startswith("copernicus_adriacenter_2") and f.endswith(".grb"))
    for old in files[:-keep]:
        os.remove(os.path.join(outdir, old))


def main():
    if not (os.getenv("COPERNICUSMARINE_SERVICE_USERNAME") and os.getenv("COPERNICUSMARINE_SERVICE_PASSWORD")):
        print("Water GRIB skipped: COPERNICUSMARINE_SERVICE_USERNAME / _PASSWORD are not set")
        return 0
    try:
        key, ref = check_marine.newest_update()
    except Exception as e:
        print(f"Water GRIB: could not read the Copernicus metadata ({type(e).__name__}: {e})")
        return 1
    key_path = os.path.join(OUTDIR, KEY_FILE)
    if read_key(key_path) == key:
        print(f"Water GRIB: no new Copernicus data (update {key})")
        return 0
    os.makedirs(OUTDIR, exist_ok=True)
    if marine_grib.main(["--timestamp", ref, "--outdir", OUTDIR]) != 0:
        return 1  # the previous file stays; the next cron run retries
    name = f"copernicus_adriacenter_{ref}.grb"
    shutil.copyfile(os.path.join(OUTDIR, name), os.path.join(OUTDIR, "copernicus_adriacenter_latest.grb.tmp"))
    os.replace(os.path.join(OUTDIR, "copernicus_adriacenter_latest.grb.tmp"),
               os.path.join(OUTDIR, "copernicus_adriacenter_latest.grb"))
    with open(key_path, "w") as f:
        f.write(key)
    prune(OUTDIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
