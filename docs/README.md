# Documentation

Developer documentation for aladin-grib-adria: what the system produces, how, and why. It is the basis for future development: change the docs in the same pull request as the code they describe.

## What to read

| If you want to... | Read |
|---|---|
| understand the whole system in five minutes | [architecture.md](architecture.md) |
| know exactly what is inside a published GRIB (parameters, times, grids, sizes) | [grib-format.md](grib-format.md) |
| change how wind data is downloaded or processed | [wind-pipeline.md](wind-pipeline.md) |
| change the Copernicus water file | [marine-pipeline.md](marine-pipeline.md) |
| change what ends up on GitHub Pages, or understand a stale warning | [publishing.md](publishing.md) |
| run, test, force or debug the pipeline; routine maintenance | [operations.md](operations.md) |
| add or change tests | [testing.md](testing.md) |
| know why something is the way it is, or what was rejected | [decisions.md](decisions.md) |

Reading order for a new developer: architecture, grib-format, then the pipeline you touch.

## How far to trust each file

| File | Status |
|---|---|
| architecture, marine-pipeline, publishing, testing, operations (except the Fly.io note), and the marine parts of grib-format and decisions | **Ground truth.** Written together with the code, checked against tests, real runs and real output (2026-11-24). |
| wind-pipeline, the wind parts of grib-format, and the older entries of decisions | **Reconstructed.** Derived from the code, the git history and a decoded published file; no specification existed. Statements that could not be checked are marked *(inferred)* or *(not verified)*. |

If a document and the code disagree, one of them is wrong: fix it in the same change. Invariants that are easy to break have a test (see [testing.md](testing.md)); the docs name the test where there is one.

## Conventions

- All times are **UTC**. A **run** is an ALADIN model run, identified by `YYYYMMDDHH` (00, 06, 12 or 18 UTC). A **step** is the forecast hour after the reference time: for the wind file (reference time = the run) 0 to 72, for the water file (reference time = 00 UTC of a Copernicus update day) 0 to 108. **Valid time** = reference time + step hours.
- The **wind file** is `aladin_adriacenter_<run>.grb` (CHMI ALADIN). The **water file** is `copernicus_adriacenter_<YYYYMMDD00>.grb` (Copernicus Marine currents and waves). Each also exists as `*_latest.grb` (a copy, not a link, on `gh-pages`).
- Coordinates are degrees; longitude east, latitude north. Directions of wind and waves are "from" directions (meteorological convention) unless stated.
- File and function references are to the repository root.
