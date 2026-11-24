"""Processing region: the single place to change the bounding box."""

LON_MIN = 13.0
LON_MAX = 17.5
LAT_MIN = 42.5
LAT_MAX = 45.4  # 45°24'N: a whole number of DY steps, and reaches 45°22'N on the wind and Copernicus grids
DX = 0.02
DY = 0.02


def grid_points(lo, hi, step):
    """Number of points on a regular grid from lo to hi; the box must be a whole number of steps."""
    n = round((hi - lo) / step)
    if abs(lo + n * step - hi) > 1e-9:
        raise ValueError(f"{lo}..{hi} is not a whole number of {step} degree steps")
    return n + 1


NX = grid_points(LON_MIN, LON_MAX, DX)
NY = grid_points(LAT_MIN, LAT_MAX, DY)
