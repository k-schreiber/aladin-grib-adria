# Architecture

Status: ground truth for the workflow, the water file and publishing; the wind flow is reconstructed (see [README](README.md)).

## Purpose and outputs

Whenever new data appears the system turns public forecast data into two GRIB files for the central Adriatic and publishes them on GitHub Pages (`k-schreiber.github.io/aladin-grib-adria`, branch `gh-pages`):

| Output | Source | Content |
|---|---|---|
| `aladin_adriacenter_<run>.grb` (+ `_latest`) | CHMI ALADIN 2.3 km (open data) | pressure, wind speed/direction, gusts, 2 m temperature on a 0.02° grid |
| `copernicus_adriacenter_<run>.grb` (+ `_latest`) | Copernicus Marine, Mediterranean forecast | surface current, waves on the native 1/24° grid |
| `aladin_wind_<run>.png` (+ `_latest`) | rendered from the wind data | wind map, embedded in the `gh-pages` README only |
| `index.html`, `README.md`, `status.json` | generated | file list, status line, stale-file warning |

The wind GRIB covers one ALADIN run (steps 0-72); the water GRIB has its own reference time (00 UTC of the Copernicus update day, steps 0-96) so it always spans the wind file. Same region, same GRIB1 conventions ([grib-format.md](grib-format.md)).

## Components

| File | Role |
|---|---|
| `.github/workflows/process-grib.yml` | the pipeline: `check`, `wind`, `marine`, `publish` ([publishing.md](publishing.md)) |
| `.github/workflows/tests.yml` | unit tests on every pull request |
| `check_availability.py`, `check_marine.py`, `Dockerfile.checker` | find the newest complete CHMI run; find the newest Copernicus update (Alpine container) |
| `load_and_merge_gribs.py` | wind: download, reproject with CDO, merge, render the wind map |
| `marine_grib.py` | water: Copernicus subset, write GRIB1 with eccodes |
| `grib_validate.py` | structural validation of both GRIBs |
| `build_site.py` | assemble the published site, status and warnings |
| `region.py` | the single definition of the box, grids and forecast length |
| `Dockerfile` | the one image used by `wind` and `marine` (and by the local/Fly.io container) |
| `server.py`, `start.sh`, `process.cron`, `docker-compose.yml`, `fly.toml`, `local_update_water.py` | optional self-hosted variant, wind and water ([wind-pipeline.md](wind-pipeline.md)) |
| `adriatic_coastline.json`, `scripts/make_coastline.py` | coastline for the wind map, generated from Natural Earth |
| `scripts/with_secrets.py` | run a command with the local Copernicus credentials |
| `tests/` | unit tests ([testing.md](testing.md)) |

## Data flow

```
 CHMI open data --> check ---------------------------+ (wind run, Copernicus update, what is needed)
                                                     v
                     +--> wind   : download, CDO, PNG, validate --> artifact --+
   Copernicus -------+                                                         +--> publish --> gh-pages
                     +--> marine : subset, eccodes, validate -----> artifact --+
```

`wind` and `marine` share only the job that checks for new data, and even there each asset has its own check and marker: wind when CHMI has a new complete run, water when Copernicus has a new update. Neither waits for the other.

## Principles

1. **Independent flows.** `wind` and `marine` have no dependency on each other; one failing never stops the other.
2. **Always a valid file.** `publish` replaces a published file only by a new, validated one; otherwise the previous file stays and the page says so.
3. **Water covers wind.** The water file starts at 00 UTC of the update day and runs 96 h, so it always spans the newest wind file ([marine-pipeline.md](marine-pipeline.md)).
4. **One definition of the region.** `region.py` is the only place that holds the box; grids, sizes, validators, the coastline generator and the region texts derive from it. (The two Copernicus DOIs are written in both `build_site.py` and `marine_grib.py`; a test keeps them equal.)
5. **Validate before publishing.** A new file that fails `grib_validate.py` counts as a failed job.
6. **One image.** Both jobs run the same Docker image; an install problem affects both.
7. **No secret outside the marine job.** Credentials are passed by name into one `docker run`.

## Failure behaviour

| Situation | Wind file | Water file | Page |
|---|---|---|---|
| everything succeeds | new | new | status OK |
| wind job fails | previous | new | wind STALE + warning; runs differ |
| marine job fails (credentials, outage, Copernicus change) | new | previous | water STALE + warning |
| both fail, or the image build fails | previous | previous | both STALE |
| a new file fails validation | as a failed job | | |
| `gh-pages` cannot be read | `publish` fails | `publish` fails | nothing deployed, markers not saved, retried at the next run |
| `check` finds no complete run, or fails | unchanged | unchanged | unchanged (nothing is shown) |
| the same failure again at the next run | unchanged | unchanged | not redeployed |
| nothing published before, and the job fails | missing | missing | "not available" warning |

A failed file is retried at the next scheduled run (every 15 minutes in the workflow; GitHub skips many slots, so "next run" can still be an hour away) and a static page cannot show that nothing ran ([operations.md](operations.md)).
