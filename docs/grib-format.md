# GRIB format, times and grids

Status: the water file and all calculations are **ground truth** (written by `marine_grib.py`, enforced by `grib_validate.py`, verified on real output 2026-11-24). The wind file's header is **reconstructed** from a decoded published file (run 2026112318, written by the container's CDO 2.0.4) and from the code; there is no original spec.

## 1. Time model

All times are UTC.

| Term | Meaning | GRIB1 keys |
|---|---|---|
| run | ALADIN model run, `YYYYMMDDHH` with hour 00/06/12/18 | `dataDate` (YYYYMMDD), `dataTime` (HH00): the **reference time** of every message |
| step | forecast hour 0..72 (`region.FORECAST_HOURS` = 72, so 73 steps) | `stepUnits` = 1 (hours), `P1` = step, `P2` = 0 |
| valid time | run + step hours | what viewers show as the field's time |
| time range indicator | 0: forecast valid at reference + P1 | `timeRangeIndicator` = 0 |

- **Both files use the same reference time and steps for one run.** Example: run 2026112318 gives valid times 2026-11-23 18:00 (step 0) to 2026-11-26 18:00 (step 72).
- **CHMI side.** The timestamp in a CHMI file name is the model run. Each source file holds 73 hourly steps (checked: 1,666,298 values = 73 x 22,826 grid points; the merged GRIB's step 72 is valid 2026-11-26 18:00 for run 2026-11-23 18:00).
- **Copernicus side.** The window `[run, run + 72 h]` is requested from the hourly series, whose time stamps fall exactly on the hour (checked). Currents are **hourly means centred on the stamp** (NetCDF attribute `field_type = hourly_mean_centered_at_time_field`), waves are **instantaneous**. Both are written with time range indicator 0, i.e. a mean over the hour 17:30-18:30 is labelled 18:00 like an instantaneous field. The data are Copernicus' best estimate for those hours: the analysis for past hours and the latest forecast for later ones; which forecast cycle that is depends on when the job runs (`data_updated_utc` in `marine_meta.json` records the dataset update time; it is not part of the GRIB).
- **CDO versions encode time differently.** The container's CDO 2.0.4 writes time range indicator 0 with a one-octet `P1`; newer CDO (checked: 2.6.6) writes indicator 10 with a two-octet step. The validator reads eccodes' derived `step` key and accepts both for the wind file.

## 2. Region and grids

`region.py` (single source of truth):

| | Value |
|---|---|
| box | longitude 13.0-17.5, latitude 42.5-45.4 (45°24'N) |
| wind step `DX`, `DY` | 0.02° |
| `grid_points(lo, hi, step)` | `round((hi - lo) / step) + 1`; raises if `lo + n*step` differs from `hi` by more than 1e-9 |

`round()` is deliberate: `(45.4 - 42.5) / 0.02` evaluates to `144.99999999999991`, so `int()` would lose a row. Pinned by `tests/test_region.py`.

**Wind grid** (CDO `remapbil`/`remapnn` target, regular lat/lon, rows south to north, columns west to east):
`NX = (17.5-13.0)/0.02 + 1 = 226`, `NY = (45.4-42.5)/0.02 + 1 = 146`, 32,996 points, first point (42.5, 13.0), last (45.4, 17.5).

**Water grid** (Copernicus native, not regridded): the points of the lattice `lon = -17.291666 + k/24`, `lat = 30.1875 + k/24` that lie inside the box (tolerance 1e-4°):
`lon: k = 727..835 -> 109 points, 13.0 .. 17.5`; `lat: k = 296..365 -> 70 points, 42.5208 .. 45.3958`; 7,630 points. (`region.MARINE_LONS/LATS`.) The last row, 45.3958, is the first one past 45°22' (the previous, 45.3542, is not); the box edge 45.4 itself is not a grid line of that lattice.

Both datasets share this grid to within 2e-6° (the wave grid's last longitude is 17.50000191, which is why requests use a box padded by 0.01° and are cropped to the exact region afterwards).

**Scan order** (both files): `scanningMode` 64 = +i (west to east), +j (south to north), row by row; values are written with the longitude varying fastest.

**Stored corners** are rounded to whole millidegrees by GRIB1 (42.5208 -> 42.521, 45.3958 -> 45.396); the validator allows 2e-3° (`CORNER_TOLERANCE`).

**Grid increments.** GRIB1 stores increments in whole millidegrees, which cannot hold 1/24° (41.667 mdeg, stored as 42). The water file therefore sets `iDirectionIncrementGiven = jDirectionIncrementGiven = 0` and the increment octets to "missing" (0xFFFF); readers derive the spacing from the corners. Measured decoded position error (eccodes): about 0.06 km this way, up to about 2.5 km if the rounded 0.042 were stored (variant A in the history in [decisions.md](decisions.md)). The wind grid (0.02° = 20 mdeg) stores its increments normally.

## 3. Header contract

| Key | Wind file | Water file |
|---|---|---|
| edition | 1 | 1 |
| `centre` / `subCentre` / `table2Version` / `generatingProcessIdentifier` / `gridDefinition` | 89 / 0 / 1 / 2 / 255 | 89 / 0 / 1 / 2 / 255 (same as the wind file, so viewers treat them alike) |
| `dataDate`, `dataTime` | run | run |
| `stepUnits` / `P1` / `P2` / `timeRangeIndicator` | 1 / step / 0 / 0 (CDO 2.0.4) or 10 (newer CDO) | 1 / step / 0 / 0 |
| grid | `regular_ll` 226 x 146 | `regular_ll` 109 x 70 |
| `resolutionAndComponentFlags` | 136 (increments given) | 0 (increments not given) |
| packing | 12 bits/value, no bitmap | 12 bits/value, **bitmap** (land = missing, value 9999 inside the encoder only) |
| messages | 438 = 6 parameters x 73 steps | 803 = 11 parameters x 73 steps |

Message order: parameter by parameter, steps ascending (water file: order of `marine_grib.FIELDS`).

## 4. Parameters

### Wind file (reconstructed: parameter numbers decoded from the published file, source names from the code)

| GRIB1 param | Level type / value | CHMI variable | Content | Unit |
|---|---|---|---|---|
| 2 | 102 (mean sea level) / 0 | `MSLPRESSURE` | mean sea level pressure | Pa |
| 31 | 105 (height above ground) / 10 m | `CLSWIND_DIREC` | wind direction, **from** | degrees |
| 32 | 105 / 10 m | `CLSWIND_SPEED` | wind speed | m/s |
| 130 | 105 / 0 | `CLSU_RAF_MOD_XFU` *(inferred)* | gust, u component (maximum in the next hour) | m/s |
| 131 | 105 / 0 | `CLSV_RAF_MOD_XFU` *(inferred)* | gust, v component | m/s |
| 11 | 105 / 2 m | `CLSTEMPERATURE` | 2 m temperature | K |

130/131 are not WMO parameters (CHMI local codes); their mapping to the gust variables follows from the variable list and was not independently verified. Gust fields are "maximum in the next hour" but carry time range indicator 0 like the others.

### Water file (ground truth; `marine_grib.FIELDS`)

| GRIB1 param | Level type / value | Copernicus variable | Content | Unit |
|---|---|---|---|---|
| 49 | 160 (depth below sea level) / 0 | `uo` | current, eastward | m/s |
| 50 | 160 / 0 | `vo` | current, northward | m/s |
| 100 | 1 (surface) / 0 | `VHM0` | significant wave height | m |
| 107 | 1 / 0 | `VMDR` | mean wave direction, from (stored as "primary wave direction") | degrees |
| 108 | 1 / 0 | `VTPK` | peak wave period (stored as "primary wave mean period") | s |
| 102 / 101 / 103 | 1 / 0 | `VHM0_WW` / `VMDR_WW` / `VTM01_WW` | wind-sea height / direction (from) / mean period | m / degrees / s |
| 105 / 104 / 106 | 1 / 0 | `VHM0_SW1` / `VMDR_SW1` / `VTM01_SW1` | primary swell height / direction (from) / mean period | m / degrees / s |

Codes are NCEP GRIB1 table 2 (confirmed by eccodes for the wave names; eccodes has no names for ocean currents, which is harmless). The currents contain tides and the model's wave coupling but **not** Stokes drift. GRIB1 has no code for maximum wave height or a second swell, so those fields are not included.

## 5. Packing, missing values, precision

- 12 bits per value. Quantisation step = (field maximum - minimum) / 4096 within a message; measured round-trip errors: currents 1.2e-4 m/s, heights 4.8e-4 m, periods 1e-3 to 2e-3 s, directions 0.06°.
- **Direction overshoot:** decoded directions can exceed 360 by up to 0.04° (marine 360.04, published wind 360.002). Validators accept -0.5..360.5; consumers must wrap.
- **Missing values:** the water file has a bitmap; a point is missing for land (about 51 % of the grid, static, identical in every step and field). The validator recognises missing points **only where a bitmap exists**: wind pressure (about 101,325 Pa) is far above the 9999 marker used inside the encoder.
- A constant field packs with 0 bits (legal).

## 6. File sizes

One message = 8 (indicator) + 28 (PDS) + 32 (GDS) + [bitmap section] + data section + 4 (end) bytes; the data section is 11 bytes of header plus `ceil(12 * valid_points / 8)`, padded to an even length.

- Wind, no bitmap: `72 + 11 + ceil(12 n / 8)` (+1 if odd). For n = 32,996: 49,578 B; x 438 = **21,715,164 B** (measured on the CI container: identical). Previous box (n = 22,826): 34,322 B, 15,033,036 B.
- Water, bitmap: bitmap section = 6 + `ceil(n / 8)` (padded to even) = 960 B for n = 7,630, plus data for the valid points only. Measured: 803 messages, **5,317,466 B** (about 6.6 KB per message, 51 % land). Before the north extension (109 x 48): 4,299,262 B.
- On the Pages site every file exists twice (timestamped and `_latest`), about 54 MB in total.

## 7. What `grib_validate.py` enforces

Common: edition 1; every message has the expected reference time, `stepUnits` 1, grid size and corners (within 2e-3°); per parameter exactly 73 messages with steps 0..72 once each; no field without a valid value; finite values; values within the ranges below.

| | Wind | Water |
|---|---|---|
| messages / parameters | 438 / {2, 31, 32, 130, 131, 11} | 803 / {49, 50, 100-108} |
| time range indicator | 0 or 10 | 0 |
| ranges | MSLP 85,000-110,000 Pa; speed 0-80 m/s; direction -0.5..360.5; gust components -100..100 m/s; T2m 230-330 K | currents -3..3 m/s; wave and swell heights 0-15 m; periods 0-25 s; directions -0.5..360.5 |
| mask | - | same missing count in every step; missing share 0.25-0.75 |

The ranges are deliberately generous: they catch broken files, not unusual weather.

## 8. Viewer compatibility (evidence)

- **qtVlm** (the owner's main viewer) opened the water file in three variants (GRIB1 with increments stored, GRIB1 as published, GRIB2): all 11 fields recognised (currents as "Ocean current (Mean sea level)", waves under "Surface"), 73 dates, centre 89, resolution 0.0417°, correct coverage.
- **OpenCPN** (per a reading of its source, not tested with the files): from GRIB1 it uses parameters 49/50 and 100-103 only, so total wave direction/period (107/108) and swell (104-106) are ignored; it recomputes grid increments from the corners.
- Not tested: Expedition, Weather4D, zyGrib.

## 9. Calculation reference

- Wind components for the map (`load_and_merge_gribs.render_wind_map`), with direction `d` (degrees, from) and speed `s`: `u = -s sin(d)`, `v = -s cos(d)` (east/north components of the vector pointing where the wind blows to). Only step 0 is drawn.
- Arrow subsampling: `step = max(1, NX // 30) = 7`, giving 33 x 21 arrows. Map aspect: `1 / cos(mean latitude)`.
- Wind speed/direction are remapped separately (direction nearest-neighbour, see [wind-pipeline.md](wind-pipeline.md)); u/v are never interpolated.
- Message counts: `parameters x (FORECAST_HOURS + 1)`.
