"""Helpers for building small synthetic GRIB1 files in tests."""
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HAVE_ECCODES = importlib.util.find_spec("eccodes") is not None
HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
HAVE_NETCDF = all(importlib.util.find_spec(m) is not None for m in ("xarray", "h5netcdf", "h5py"))
MISSING = 9999.0


def write_grib1(path, messages):
    """messages: dicts with param, step, ts (YYYYMMDDHH), lons, lats, values (flat list, None = missing),
    optional bitmap (default True if a value is None), edition (1 or 2), trange."""
    import eccodes as ec

    with open(path, "wb") as out:
        for m in messages:
            if m.get("edition", 1) == 2:
                h = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
                ec.codes_write(h, out)
                ec.codes_release(h)
                continue
            h = ec.codes_grib_new_from_samples("regular_ll_sfc_grib1")
            lons, lats = m["lons"], m["lats"]
            ec.codes_set(h, "centre", 89)
            ec.codes_set(h, "table2Version", 1)
            ec.codes_set(h, "Ni", len(lons))
            ec.codes_set(h, "Nj", len(lats))
            ec.codes_set(h, "jScansPositively", 1)
            ec.codes_set(h, "latitudeOfFirstGridPointInDegrees", float(lats[0]))
            ec.codes_set(h, "longitudeOfFirstGridPointInDegrees", float(lons[0]))
            ec.codes_set(h, "latitudeOfLastGridPointInDegrees", float(lats[-1]))
            ec.codes_set(h, "longitudeOfLastGridPointInDegrees", float(lons[-1]))
            ec.codes_set(h, "iDirectionIncrementGiven", 0)
            ec.codes_set(h, "jDirectionIncrementGiven", 0)
            ec.codes_set(h, "dataDate", int(m["ts"][:8]))
            ec.codes_set(h, "dataTime", int(m["ts"][8:10]) * 100)
            ec.codes_set(h, "stepUnits", 1)
            trange = m.get("trange", 0)
            ec.codes_set(h, "timeRangeIndicator", trange)
            if trange == 10:  # the step is a 16-bit number spanning octets P1 and P2
                ec.codes_set(h, "P1", m["step"] // 256)
                ec.codes_set(h, "P2", m["step"] % 256)
            else:
                ec.codes_set(h, "P1", m["step"])
            ec.codes_set(h, "indicatorOfParameter", m["param"])
            ec.codes_set(h, "bitsPerValue", 16)
            has_missing = any(v is None for v in m["values"])
            if m.get("bitmap", has_missing):
                ec.codes_set(h, "bitmapPresent", 1)
            ec.codes_set(h, "missingValue", MISSING)
            ec.codes_set_values(h, [MISSING if v is None else v for v in m["values"]])
            ec.codes_write(h, out)
            ec.codes_release(h)
