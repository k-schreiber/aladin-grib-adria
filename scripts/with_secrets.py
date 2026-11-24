#!/usr/bin/env python3
"""Run a command with the Copernicus Marine credentials from secrets.yaml in its environment.
The values are never printed. For local testing only; CI uses the repository secrets.

Usage: python3 scripts/with_secrets.py -- python3 marine_grib.py --timestamp 2026112318 --outdir out
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SECRETS = os.environ.get("SECRETS_FILE", os.path.join(ROOT, "secrets.yaml"))
KEYS = ("COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD")


def load(path):
    values = {}
    with open(path) as f:
        for line in f:
            m = re.match(r"^\s*(" + "|".join(KEYS) + r")\s*:\s*(.*?)\s*$", line)
            if m:
                value = m.group(2)
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[m.group(1)] = value
    return values


def main(argv):
    cmd = argv[1:]
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        sys.exit(__doc__)
    values = load(SECRETS)
    missing = [k for k in KEYS if not values.get(k)]
    if missing:
        sys.exit(f"{SECRETS} is missing: {', '.join(missing)}")
    os.execvpe(cmd[0], cmd, {**os.environ, **values})


if __name__ == "__main__":
    main(sys.argv)
