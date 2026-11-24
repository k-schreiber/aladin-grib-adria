"""Processing region: the single place to change the bounding box."""
import math

LON_MIN = 13.0
LON_MAX = 17.5
LAT_MIN = 42.5
LAT_MAX = 45.4  # 45°24'N: a whole number of DY steps, and reaches 45°22'N on the wind and Copernicus grids
DX = 0.02
DY = 0.02

FORECAST_HOURS = 72  # the wind GRIB holds the hourly steps 0..FORECAST_HOURS of one ALADIN run
# The water GRIB is independent of ALADIN runs: its reference time is 00 UTC of the day of the newest
# Copernicus update and it holds MARINE_HOURS + 1 hourly steps. Worst case, the newest wind run (18 UTC) ends
# 90 h after 00 UTC of its day, and its water file may only be replaced the next morning, so 96 h always covers it.
MARINE_HOURS = 96

# Copernicus Med-MFC grid (currents and waves share it): 1/24 degree from this origin.
COPERNICUS_LON0 = -17.291666
COPERNICUS_LAT0 = 30.1875
COPERNICUS_STEP = 1 / 24


def grid_points(lo, hi, step):
    """Number of points on a regular grid from lo to hi; the box must be a whole number of steps."""
    n = round((hi - lo) / step)
    if abs(lo + n * step - hi) > 1e-9:
        raise ValueError(f"{lo}..{hi} is not a whole number of {step} degree steps")
    return n + 1


def native_axis(origin, lo, hi, step=COPERNICUS_STEP, tol=1e-4):
    """The points of a regular axis (origin + k * step) that lie within lo..hi."""
    first = math.ceil((lo - tol - origin) / step)
    last = math.floor((hi + tol - origin) / step)
    return [origin + k * step for k in range(first, last + 1)]


NX = grid_points(LON_MIN, LON_MAX, DX)
NY = grid_points(LAT_MIN, LAT_MAX, DY)

MARINE_LONS = native_axis(COPERNICUS_LON0, LON_MIN, LON_MAX)
MARINE_LATS = native_axis(COPERNICUS_LAT0, LAT_MIN, LAT_MAX)
MARINE_NX = len(MARINE_LONS)
MARINE_NY = len(MARINE_LATS)
