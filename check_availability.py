#!/usr/bin/env python3
"""
Checks if a new, complete ALADIN GRIB run is available at CHMI.
Prints timestamp (YYYYMMDDHH) to stdout and exits 0 if found.
Exits 1 otherwise (no data or incomplete).
"""
import sys
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://opendata.chmi.cz/meteorology/weather/nwp_aladin/Lambert_2.3km/"
RUN_DIRS = ["00", "06", "12", "18"]
REQUIRED_VARS = {
    "MSLPRESSURE", "CLSWIND_DIREC", "CLSWIND_SPEED",
    "CLSU_RAF_MOD_XFU", "CLSV_RAF_MOD_XFU", "CLSTEMPERATURE",
}


def scan_run_dir(run):
    """Returns {timestamp: set(var_codes)} for files found in this run directory."""
    try:
        resp = requests.get(f"{BASE_URL}{run}/", timeout=30)
        if resp.status_code != 200:
            return {}
    except requests.RequestException:
        return {}

    ts_vars = {}
    for a in BeautifulSoup(resp.text, "html.parser").find_all("a"):
        name = a.get("href", "")
        if not name.startswith("ALADLAMB4opendata_"):
            continue
        # Filename: ALADLAMB4opendata_{YYYYMMDDHH}_{VARCODE}.grb[.bz2]
        # Split on first two underscores only so multi-part var codes like
        # CLSU_RAF_MOD_XFU are kept intact.
        parts = name.split("_", 2)
        if len(parts) != 3:
            continue
        ts = parts[1]
        var = parts[2].split(".")[0]  # strip .grb or .grb.bz2
        ts_vars.setdefault(ts, set()).add(var)
    return ts_vars


# Collect all timestamps and their available variables across all run directories
all_ts: dict[str, set] = {}
for run in RUN_DIRS:
    for ts, vars_ in scan_run_dir(run).items():
        all_ts.setdefault(ts, set()).update(vars_)

# Find newest timestamp with all required variables present
for ts in sorted(all_ts, reverse=True):
    if REQUIRED_VARS.issubset(all_ts[ts]):
        print(ts)
        sys.exit(0)

print("No complete run available yet.", file=sys.stderr)
sys.exit(1)
