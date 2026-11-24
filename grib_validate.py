#!/usr/bin/env python3
"""Structural validation of the published GRIB files, decoded with eccodes.

Usage: python3 grib_validate.py wind|marine <file.grb> <YYYYMMDDHH>

Only structure and generous physical ranges are checked, so that a valid file is never rejected.
"""
import sys

import eccodes as ec
import numpy as np

import region

MISSING = 9999.0
STEPS = region.FORECAST_HOURS + 1
MARINE_STEPS = region.MARINE_HOURS + 1
CORNER_TOLERANCE = 2e-3  # GRIB1 stores corner coordinates in whole millidegrees

# parameter -> (min, max) of the valid values. Directions allow 0.5 degree for packing overshoot.
WIND_RANGES = {2: (85000, 110000), 31: (-0.5, 360.5), 32: (0, 80), 130: (-100, 100), 131: (-100, 100), 11: (230, 330)}
MARINE_RANGES = {
    49: (-3, 3), 50: (-3, 3),
    100: (0, 15), 102: (0, 15), 105: (0, 15),
    101: (-0.5, 360.5), 104: (-0.5, 360.5), 107: (-0.5, 360.5),
    103: (0, 25), 106: (0, 25), 108: (0, 25),
}
LAND_SHARE = (0.25, 0.75)


class ValidationError(Exception):
    pass


def scan(path):
    """One dict per message of the file."""
    messages = []
    with open(path, "rb") as f:
        while True:
            h = ec.codes_grib_new_from_file(f)
            if h is None:
                break
            try:
                edition = ec.codes_get(h, "editionNumber")
                if edition != 1:
                    messages.append({"edition": edition})
                    continue
                bitmap = bool(ec.codes_get(h, "bitmapPresent"))
                ec.codes_set(h, "missingValue", MISSING)
                values = ec.codes_get_values(h)
                missing = values == MISSING if bitmap else np.zeros(values.shape, dtype=bool)
                valid = values[~missing]
                messages.append({
                    "edition": edition,
                    "param": ec.codes_get(h, "indicatorOfParameter"),
                    "date": ec.codes_get(h, "dataDate"),
                    "time": ec.codes_get(h, "dataTime"),
                    "unit": ec.codes_get(h, "stepUnits"),
                    "trange": ec.codes_get(h, "timeRangeIndicator"),
                    "step": ec.codes_get(h, "step"),  # not P1: newer CDO writes P1 in two octets
                    "ni": ec.codes_get(h, "Ni"),
                    "nj": ec.codes_get(h, "Nj"),
                    "corners": (
                        ec.codes_get(h, "latitudeOfFirstGridPointInDegrees"),
                        ec.codes_get(h, "longitudeOfFirstGridPointInDegrees"),
                        ec.codes_get(h, "latitudeOfLastGridPointInDegrees"),
                        ec.codes_get(h, "longitudeOfLastGridPointInDegrees"),
                    ),
                    "bitmap": bitmap,
                    "n": values.size,
                    "missing": int(missing.sum()),
                    "finite": bool(np.isfinite(valid).all()),
                    "min": float(valid.min()) if valid.size else None,
                    "max": float(valid.max()) if valid.size else None,
                })
            finally:
                ec.codes_release(h)
    return messages


def _check(messages, ts, ranges, ni, nj, corners, steps, tranges):
    problems = []
    if not messages:
        return ["file contains no GRIB messages"]
    date, time = int(ts[:8]), int(ts[8:10]) * 100

    editions = {m["edition"] for m in messages}
    if editions != {1}:
        return [f"GRIB edition(s) {sorted(editions)}, expected 1"]

    expected = len(ranges) * steps
    if len(messages) != expected:
        problems.append(f"{len(messages)} messages, expected {expected} ({len(ranges)} parameters x {steps} steps)")

    seen_params = {m["param"] for m in messages}
    if seen_params != set(ranges):
        problems.append(f"parameters {sorted(seen_params)}, expected {sorted(ranges)}")

    for label, values, want in (
        ("reference time", {(m["date"], m["time"]) for m in messages}, {(date, time)}),
        ("step unit", {m["unit"] for m in messages}, {1}),
        ("grid size", {(m["ni"], m["nj"]) for m in messages}, {(ni, nj)}),
    ):
        if values != want:
            problems.append(f"{label} {sorted(values)}, expected {sorted(want)}")
    bad_tranges = {m["trange"] for m in messages} - set(tranges)
    if bad_tranges:
        problems.append(f"time range indicator {sorted(bad_tranges)}, expected one of {sorted(tranges)}")

    bad_corners = {m["corners"] for m in messages
                   if any(abs(a - b) > CORNER_TOLERANCE for a, b in zip(m["corners"], corners))}
    if bad_corners:
        problems.append(f"grid corners {sorted(bad_corners)}, expected about {corners}")

    for param, (lo, hi) in ranges.items():
        series = [m for m in messages if m["param"] == param]
        got = sorted(m["step"] for m in series)
        if got != list(range(steps)):
            problems.append(f"parameter {param}: steps {got[:3]}..{got[-3:]} ({len(got)}), expected 0..{steps - 1} once each")
        if any(m["missing"] == m["n"] for m in series):
            problems.append(f"parameter {param}: a field has no valid value")
        if not all(m["finite"] for m in series):
            problems.append(f"parameter {param}: non-finite values")
        mins = [m["min"] for m in series if m["min"] is not None]
        maxs = [m["max"] for m in series if m["max"] is not None]
        if mins and (min(mins) < lo or max(maxs) > hi):
            problems.append(f"parameter {param}: values {min(mins):.4g}..{max(maxs):.4g} outside {lo}..{hi}")
    return problems


def validate_wind(path, ts, ni=region.NX, nj=region.NY, steps=STEPS):
    corners = (region.LAT_MIN, region.LON_MIN, region.LAT_MAX, region.LON_MAX)
    # 0 is what the container's CDO writes, 10 is the 2-byte step encoding of newer CDO versions.
    problems = _check(scan(path), ts, WIND_RANGES, ni, nj, corners, steps, tranges=(0, 10))
    if problems:
        raise ValidationError("; ".join(problems))


def validate_marine(path, ts, lons=None, lats=None, steps=MARINE_STEPS):
    lons = region.MARINE_LONS if lons is None else lons
    lats = region.MARINE_LATS if lats is None else lats
    messages = scan(path)
    corners = (lats[0], lons[0], lats[-1], lons[-1])
    problems = _check(messages, ts, MARINE_RANGES, len(lons), len(lats), corners, steps, tranges=(0,))
    if not problems:
        for param in MARINE_RANGES:
            series = [m for m in messages if m["param"] == param]
            if len({m["missing"] for m in series}) != 1:
                problems.append(f"parameter {param}: the missing-value mask changes between steps")
            share = series[0]["missing"] / series[0]["n"]
            if not LAND_SHARE[0] <= share <= LAND_SHARE[1]:
                problems.append(f"parameter {param}: missing share {share:.2f} outside {LAND_SHARE}")
    if problems:
        raise ValidationError("; ".join(problems))


def main(argv):
    if len(argv) != 4 or argv[1] not in ("wind", "marine") or len(argv[3]) != 10 or not argv[3].isdigit():
        print(__doc__)
        return 2
    kind, path, ts = argv[1:4]
    try:
        (validate_wind if kind == "wind" else validate_marine)(path, ts)
    except (ValidationError, OSError) as e:
        print(f"INVALID {kind} GRIB {path}: {e}")
        return 1
    print(f"OK: {kind} GRIB {path} for run {ts}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
