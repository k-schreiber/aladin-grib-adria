#!/usr/bin/env python3
"""Build the Copernicus marine GRIB (surface currents and waves) for one reference day.

Usage: python3 marine_grib.py --timestamp YYYYMMDD00 [--outdir DIR]

Reference time = 00 UTC of the day of the newest Copernicus update, hourly steps 0..96 (region.MARINE_HOURS),
so the file always spans the 72 h of the newest ALADIN run. Native 1/24 degree Copernicus grid, same GRIB1
conventions as the wind file.
Needs COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD in the environment.
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

import numpy as np

import grib_validate
import region

# No dataset version is requested: the toolbox then uses the newest one, so the files follow Copernicus'
# model releases automatically (owner's decision). A new release can change the values on an unchanged
# grid (202611 differs from 202511 by ~0.07 m/s on average); each run records which model system it got.
CURRENTS = {"id": "cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m", "doi": "10.48670/mds-00359"}
WAVES = {"id": "cmems_mod_med_wav_anfc_4.2km_PT1H-i", "doi": "10.48670/mds-00373"}

# (variable, GRIB1 parameter, level type, source). Messages are written field by field, step by step.
FIELDS = [
    ("uo", 49, 160, "currents"),
    ("vo", 50, 160, "currents"),
    ("VHM0", 100, 1, "waves"),
    ("VMDR", 107, 1, "waves"),
    ("VTPK", 108, 1, "waves"),
    ("VHM0_WW", 102, 1, "waves"),
    ("VMDR_WW", 101, 1, "waves"),
    ("VTM01_WW", 103, 1, "waves"),
    ("VHM0_SW1", 105, 1, "waves"),
    ("VMDR_SW1", 104, 1, "waves"),
    ("VTM01_SW1", 106, 1, "waves"),
]

PAD = 0.01                # the request box is padded: the wave grid's last longitude is 2e-6 degrees past 17.5
CROP_TOLERANCE = 1e-3     # degrees, when cropping to the region
SAME_GRID_TOLERANCE = 1e-4
BITS_PER_VALUE = 12       # as in the wind GRIB
PERMANENT_ERRORS = ("CoordinatesOutOfDatasetBounds", "VariableDoesNotExistInTheDataset", "WrongDatetimeFormat")
PERMANENT_HINTS = ("credential", "username", "password", "unauthorized", "forbidden", "401", "403")


def parse_timestamp(ts):
    if not re.fullmatch(r"\d{10}", ts or ""):
        raise ValueError(f"timestamp must be YYYYMMDDHH, got {ts!r}")
    return datetime.strptime(ts, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def request_box():
    return {
        "minimum_longitude": region.LON_MIN - PAD,
        "maximum_longitude": region.LON_MAX + PAD,
        "minimum_latitude": region.LAT_MIN - PAD,
        "maximum_latitude": region.LAT_MAX + PAD,
    }


def is_permanent(error):
    """Errors that retrying cannot fix: bad credentials, wrong request."""
    text = str(error).lower()
    return type(error).__name__ in PERMANENT_ERRORS or any(hint in text for hint in PERMANENT_HINTS)


def with_retries(fn, attempts=3, pause=30, sleep=time.sleep):
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            if is_permanent(e) or attempt == attempts:
                raise
            print(f"Attempt {attempt}/{attempts} failed ({type(e).__name__}); retrying in {pause} s")
            sleep(pause)


def fetch(source, variables, t0, outdir, name):
    """Server-side subset of one dataset for the run's window; returns the NetCDF path."""
    import copernicusmarine

    t1 = t0 + timedelta(hours=region.MARINE_HOURS)
    fmt = "%Y-%m-%dT%H:%M:%S"

    def call():
        copernicusmarine.subset(
            dataset_id=source["id"],
            variables=variables,
            start_datetime=t0.strftime(fmt),
            end_datetime=t1.strftime(fmt),
            output_directory=outdir,
            output_filename=f"{name}.nc",
            file_format="netcdf",
            overwrite=True,
            disable_progress_bar=True,
            **request_box(),
        )
        return os.path.join(outdir, f"{name}.nc")

    print(f"Fetching {source['id']} ({', '.join(variables)})")
    return with_retries(call)


def crop_index(axis, lo, hi):
    """Indices of the axis points inside lo..hi (ascending, contiguous)."""
    idx = np.where((axis >= lo - CROP_TOLERANCE) & (axis <= hi + CROP_TOLERANCE))[0]
    if idx.size == 0 or (np.diff(idx) != 1).any():
        raise ValueError(f"axis has no contiguous run of points inside {lo}..{hi}")
    return idx


def expected_times(t0):
    start = np.datetime64(t0.replace(tzinfo=None), "h")
    return np.arange(start, start + np.timedelta64(region.MARINE_HOURS + 1, "h"), dtype="datetime64[h]")


def check_axes(currents, waves, t0):
    """currents / waves are (lons, lats, times). Raises ValueError unless both agree and match the window."""
    want = expected_times(t0)
    for label, (_, _, times) in (("currents", currents), ("waves", waves)):
        if times.shape != want.shape or (times != want).any():
            raise ValueError(f"{label}: time axis is {times[:1]}..{times[-1:]} ({times.size} steps), "
                             f"expected {want[0]}..{want[-1]} ({want.size} hourly steps)")
    for i, label in ((0, "longitude"), (1, "latitude")):
        a, b = currents[i], waves[i]
        if a.shape != b.shape or np.abs(a - b).max() > SAME_GRID_TOLERANCE:
            raise ValueError(f"currents and waves differ in {label}")
    nx, ny = currents[0].size, currents[1].size
    if (nx, ny) != (region.MARINE_NX, region.MARINE_NY):
        raise ValueError(f"grid is {nx} x {ny} points, expected {region.MARINE_NX} x {region.MARINE_NY}")


def load_data(currents_path, waves_path, t0):
    """Read both NetCDF files, crop to the region and check them.
    Returns (data, lons, lats, model_systems) where model_systems names the system that produced each file."""
    import xarray as xr

    sources = {}
    for label, path in (("currents", currents_path), ("waves", waves_path)):
        ds = xr.open_dataset(path, engine="h5netcdf")
        lon, lat = ds["longitude"].values.astype("float64"), ds["latitude"].values.astype("float64")
        xi, yi = crop_index(lon, region.LON_MIN, region.LON_MAX), crop_index(lat, region.LAT_MIN, region.LAT_MAX)
        # seconds, not hours: truncating to hours would hide a half-hour offset of the time stamps
        sources[label] = (ds, xi, yi, (lon[xi], lat[yi], ds["time"].values.astype("datetime64[s]")))
    check_axes(sources["currents"][3], sources["waves"][3], t0)

    data = {}
    for name, _, _, source in FIELDS:
        ds, xi, yi, _ = sources[source]
        var = ds[name]
        if var.dims != ("time", "latitude", "longitude"):
            raise ValueError(f"{name}: unexpected dimensions {var.dims}")
        data[name] = var.values.astype("float64")[:, yi[0]:yi[-1] + 1, xi[0]:xi[-1] + 1]
    lons, lats = sources["currents"][3][0], sources["currents"][3][1]
    systems = {label: ds.attrs.get("source") for label, (ds, _, _, _) in sources.items()}
    for ds, _, _, _ in sources.values():
        ds.close()
    return data, lons, lats, systems


def _set_header(h, ec, lons, lats):
    ec.codes_set(h, "centre", 89)
    ec.codes_set(h, "subCentre", 0)
    ec.codes_set(h, "table2Version", 1)
    ec.codes_set(h, "generatingProcessIdentifier", 2)
    ec.codes_set(h, "gridDefinition", 255)
    ec.codes_set(h, "Ni", lons.size)
    ec.codes_set(h, "Nj", lats.size)
    ec.codes_set(h, "iScansNegatively", 0)
    ec.codes_set(h, "jScansPositively", 1)
    ec.codes_set(h, "latitudeOfFirstGridPointInDegrees", float(lats[0]))
    ec.codes_set(h, "longitudeOfFirstGridPointInDegrees", float(lons[0]))
    ec.codes_set(h, "latitudeOfLastGridPointInDegrees", float(lats[-1]))
    ec.codes_set(h, "longitudeOfLastGridPointInDegrees", float(lons[-1]))
    # GRIB1 stores increments in whole millidegrees, which cannot hold 1/24 degree: leave them out
    # and let readers derive the spacing from the corner points.
    ec.codes_set(h, "iDirectionIncrementGiven", 0)
    ec.codes_set(h, "jDirectionIncrementGiven", 0)
    ec.codes_set_missing(h, "iDirectionIncrement")
    ec.codes_set_missing(h, "jDirectionIncrement")


def write_grib(path, data, lons, lats, t0):
    """Write all FIELDS (arrays of shape time x lat x lon, NaN = missing) as GRIB1; returns the message count."""
    import eccodes as ec

    date, hhmm = int(t0.strftime("%Y%m%d")), t0.hour * 100
    tmp = path + ".tmp"
    count = 0
    with open(tmp, "wb") as out:
        for name, param, level_type, _ in FIELDS:
            for step, field in enumerate(data[name]):
                h = ec.codes_grib_new_from_samples("regular_ll_sfc_grib1")
                try:
                    _set_header(h, ec, lons, lats)
                    ec.codes_set(h, "dataDate", date)
                    ec.codes_set(h, "dataTime", hhmm)
                    ec.codes_set(h, "stepUnits", 1)
                    ec.codes_set(h, "timeRangeIndicator", 0)
                    ec.codes_set(h, "P1", step)
                    ec.codes_set(h, "P2", 0)
                    ec.codes_set(h, "indicatorOfParameter", param)
                    ec.codes_set(h, "indicatorOfTypeOfLevel", level_type)
                    ec.codes_set(h, "level", 0)
                    ec.codes_set(h, "bitsPerValue", BITS_PER_VALUE)
                    ec.codes_set(h, "bitmapPresent", 1)
                    ec.codes_set(h, "missingValue", grib_validate.MISSING)
                    ec.codes_set_values(h, np.where(np.isnan(field), grib_validate.MISSING, field).ravel())
                    ec.codes_write(h, out)
                    count += 1
                finally:
                    ec.codes_release(h)
    os.replace(tmp, path)
    return count


def released(part, now):
    """Whether this dataset version's release time has passed (the toolbox ignores versions not yet released)."""
    try:
        return datetime.strptime(part.released_date[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) <= now
    except (TypeError, ValueError):
        return True


def catalogue_info(now=None):
    """(latest update time, dataset version in use per dataset, retirement dates of those versions).
    The toolbox uses the newest version that is already released; this mirrors that choice.
    Informational only: any failure returns empty values and never fails the run."""
    now = now or datetime.now(timezone.utc)
    try:
        import copernicusmarine

        stamps, in_use, retires = [], {}, {}
        for key, source in (("currents", CURRENTS), ("waves", WAVES)):
            catalogue = copernicusmarine.describe(dataset_id=source["id"], show_all_versions=True,
                                                  disable_progress_bar=True)
            versions = {v.label: v for v in catalogue.products[0].datasets[0].versions}
            usable = {label: v for label, v in versions.items() if released(v.parts[0], now)} or versions
            in_use[key] = max(usable)
            part = usable[in_use[key]].parts[0]
            stamps.append(part.arco_updated_date)
            if part.retired_date:
                retires[key] = part.retired_date
        return max(stamps), in_use, retires
    except Exception as e:
        print(f"Could not read the Copernicus catalogue ({type(e).__name__}); continuing without it")
        return None, {}, {}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timestamp", required=True, help="reference time of the file, YYYYMMDDHH (00 UTC of the day of the Copernicus update)")
    parser.add_argument("--outdir", default=os.getenv("OUTDIR", "/data"))
    args = parser.parse_args(argv)

    try:
        t0 = parse_timestamp(args.timestamp)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    for key in ("COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD"):
        if not os.getenv(key):
            print(f"Error: {key} is not set")
            return 1
    os.makedirs(args.outdir, exist_ok=True)
    final = os.path.join(args.outdir, f"copernicus_adriacenter_{args.timestamp}.grb")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            currents = fetch(CURRENTS, ["uo", "vo"], t0, tmp, "currents")
            waves = fetch(WAVES, [name for name, _, _, source in FIELDS if source == "waves"], t0, tmp, "waves")
            data, lons, lats, systems = load_data(currents, waves, t0)
        count = write_grib(final, data, lons, lats, t0)
        try:
            grib_validate.validate_marine(final, args.timestamp)
        except grib_validate.ValidationError:
            os.remove(final)
            raise
        updated, in_use, retires = catalogue_info()
        print(f"Copernicus model systems used: {systems}; dataset versions in use: {in_use}")
        if retires:
            print(f"WARNING: the dataset versions in use are scheduled for retirement: {retires}")
        meta = {
            "schema": 1,
            "timestamp": args.timestamp,
            "datasets": {"currents": CURRENTS, "waves": WAVES},
            "data_updated_utc": updated,
            "model_systems": systems,
            "versions_in_use": in_use,
            "retires_utc": retires,
            "grid": {"ni": int(lons.size), "nj": int(lats.size)},
            "messages": count,
        }
        with open(os.path.join(args.outdir, "marine_meta.json"), "w") as f:
            json.dump(meta, f, indent=1)
    except Exception as e:
        print(f"Error: marine GRIB failed: {type(e).__name__}: {e}")
        return 1

    print(f"Wrote {final}: {count} messages, grid {lons.size} x {lats.size}, "
          f"{os.path.getsize(final) / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
