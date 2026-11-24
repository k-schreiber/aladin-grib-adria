# Spec: marine GRIB asset (Copernicus Marine) next to the ALADIN wind GRIB

Status: **v1.1**, 2026-11-24. Supersedes v1.0. Changes since v1.0: independent review (every finding below was re-checked against CI logs, PyPI metadata, `gh api` or the sample files before it was accepted), the owner's viewer test and decisions, and the bounding-box work (PR #10).

## 0. Decisions taken

| # | Decision | Source |
|---|---|---|
| D1 | Each of `wind` and `marine` builds the image itself, but with a **working** build cache (`docker/build-push-action`, `type=gha`, cache written by one job only). Build-once-and-pull-from-GHCR stays an upgrade path. | default, not vetoed |
| D2 | Slim the apt layer: drop `ncview`, install with `--no-install-recommends`. Verified by a dry-run build before merge; if a needed runtime library turns out to be missing, revert only that part. | owner |
| D3 | **GRIB1 variant B** (increments flagged "not given"), **all 11 fields**, currents at level type 160, waves at level type 1, centre 89 as in the wind file. | owner (qtVlm test) |
| D4 | Automated tests ship with the code (PR 1 has the region/coastline/Dockerfile pins; PR 2 has the rest). `unittest`, stdlib only, no network/Docker/CDO. | owner |
| D5 | Names `copernicus_adriacenter_<YYYYMMDDHH>.grb` and `copernicus_adriacenter_latest.grb`. | default, not vetoed |
| D6 | Only the **failure warning** plus the status block: no client-side data-age check. | owner |
| R8 | North limit **45.4°N** (45°24'), see section 3. | owner + implementation |

## 1. Goals and constraints

| # | Requirement |
|---|---|
| R1 | A second asset, `copernicus_adriacenter_<YYYYMMDDHH>.grb` (+ `_latest`), with surface currents and waves from Copernicus Marine, on the same Pages site as the ALADIN wind GRIB. |
| R2 | Same time frame as the wind GRIB of the same run: reference time = ALADIN run T0, hourly steps 0..72 (73 steps). |
| R3 | Same GRIB format (GRIB1) and header conventions as the wind file; native Copernicus grid points, no regridding. |
| R4 | Independent computation flows: separate jobs, neither needs the other to succeed. The only coupling is the trigger: marine is assembled when a new ALADIN timestamp is detected; Copernicus updates in between are skipped on purpose. |
| R5 | A valid wind and a valid marine GRIB are always available: a failed run keeps the previous file. The page always shows a brief status and shows a warning when a file is stale. |
| R6 | One Docker image for both jobs; `copernicusmarine` goes straight into the existing wind `Dockerfile`. |
| R7 | Economical compute. |
| R8 | North limit of the box extended beyond 45°22'N for both GRIBs. |
| R9 | Credentials as GitHub secrets (done) and a local git-ignored `secrets.yaml` (used for local testing only). |

Non-goals: 3D currents, Stokes drift (currents are ocean + tide only), a currents/waves PNG, a client-side data-age display (D6), the Flask/Fly.io path (`server.py`, `start.sh`, `process.cron`), historic archives.

## 2. Facts established

Measured or verified on 2026-11-24 (toolbox 2.5.1, real credentials). Spike scripts and samples: `/private/tmp/claude-501/-Users-konrad-Projects-aladin-grib-adria/44dd8be5-2397-4080-9fea-2563b28ab70d/scratchpad/` (`scripts/`, `spike/`); owner's viewer samples: `~/Downloads/marine-grib-samples/`.

**Published wind GRIB** (decoded): GRIB1, WMO table 1, centre 89, subCentre 0, generating process 2, grid definition 255; `stepUnits` 1, `P1` 0..72, `P2` 0, time range indicator 0, reference time = run T0 in every message; 12 bits/value, no bitmap, `resolutionAndComponentFlags` 136, scan mode 64 (south to north). Parameters 2 (level type 102), 31/32 (105, 10 m), 130/131 (105), 11 (105, 2 m). 438 messages = 6 x 73.

**Copernicus datasets** (versions 202511):

| Use | Dataset id | Variables | DOI |
|---|---|---|---|
| Currents | `cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m` | `uo`, `vo` | 10.48670/mds-00359 |
| Waves | `cmems_mod_med_wav_anfc_4.2km_PT1H-i` | `VHM0 VMDR VTPK VHM0_WW VMDR_WW VTM01_WW VHM0_SW1 VMDR_SW1 VTM01_SW1` | 10.48670/mds-00373 |

Both are 1/24° (109 columns over 13.0..17.5°E), hourly on the hour, and reach 9+ days ahead. The model is NEMO + WaveWatch-III, coupled, including tides; `uo`/`vo` already contain the tide. The directions are "from" directions. Server-side subsets for 73 steps: about 20 s / 2.9 MB (currents) and 29 s / 6.5 MB (waves) on the dev machine (the toolbox reports 224 MB and 1.8 GB "transfer size" because it reads whole chunks; CI timing must be measured).

**Grid detail:** the wave grid's last longitude is 17.50000191, 2e-6° above 17.5; a strict box drops that column. Request a box padded by 0.01° and check that both datasets' coordinates agree within 1e-4° (measured 1.9e-6°). About half of the points are land: a static missing mask (per-step missing count constant), so a bitmap is needed.

**Encoding results (spike):** the marine GRIB is written with Python `eccodes` from the sample `regular_ll_sfc_grib1`; its header equals the wind header (centre 89, table 1, process 2, hours, P1 = step, TRI 0, 12 bit). CDO's default NetCDF-to-GRIB1 output is unusable (centre 0 / table 255, parameters 1..n, per-message analysis time in minutes) and CDO differs between the container (2.0.4) and a dev machine (2.6.6); the marine path therefore does not use CDO. Round trip: land mask identical, values equal to packing precision, orientation correct. eccodes names the wave parameters (`swh`, `shww`, `shts`, ...) but not ocean currents (harmless).

**GRIB1 stores grid increments in whole millidegrees**, so 41.667 mdeg becomes 42. Decoded by eccodes on the final 109 x 70 grid: variant A (increments stored) up to about 2.5 km latitude error; **variant B (increments "not given", Di/Dj set to missing): about 0.06 km**; variant C (GRIB2): exact. Viewers: **qtVlm** (owner's main viewer) opens A, B and C, lists all 10 data types (currents under "Mean sea level", waves under "Surface"), 73 dates, centre 89, resolution 0.0417°, identical coverage for A and B. **OpenCPN** (source read): GRIB1 reads only parameters 49/50 and 100..103, so total wave direction/period (107/108) and swell (104..106) are ignored; Di/Dj are recomputed from the corners, so A and B behave the same; its GRIB2 wave mapping uses 10.0.14/10.0.15 rather than 10.0.10/10.0.11. The extra fields are harmless in OpenCPN.

**12-bit packing overshoot:** directions decode up to 360.04 (marine) and 360.002 (published wind). Validators must tolerate 0.5°.

**Dataset versions (found while running the real job):** the currents dataset has two versions: `202511` (retires **2027-01-12**) and `202611` (released 2026-11-24 13:00 UTC). `202611` has the identical grid and land mask but different values on the same window (mean difference 0.07 m/s, correlation about 0.5; a new model release, `MedFS EAS11`). The toolbox silently selects the newest version, so `marine_grib.py` **pins** the versions (currents `202511`, waves `202311`), and each run records `newer_versions` and `retires_utc` in `marine_meta.json` and prints a warning. Moving to `202611` is a decision for the owner and must happen before 2027-01-12.

**Schedule reality:** `5 * * * *` produces only **2-5 scheduled runs per day** (last 12 days); some ALADIN runs are never processed. "Retry" therefore means "next scheduled run".

**gh-pages reality:** `aladin_adriacenter_latest.grb` and `aladin_wind_latest.png` are **full copies** (git mode 100644), not symlinks (peaceiris dereferences them). The Pages site carries each file twice (git stores identical blobs once).

**Image reality:** the Ubuntu 22.04 image gets `python3-numpy 1.21.5`, `python3-matplotlib 3.5.1`, `python3-pandas 1.3.5`, `python3-xarray 0.21.1`, `python3-netcdf4` and `python3-scipy` from apt (pulled in by the apt packages, not by the Dockerfile's pip step: pip logs "Requirement already satisfied: numpy ... /usr/lib/python3/dist-packages (1.21.5)"). `copernicusmarine 2.5.1` requires `numpy>=2.1.0`; Debian's pip puts numpy 2 in `/usr/local`, shadowing the apt copy, and the apt `matplotlib 3.5.1` (built against numpy 1) then fails at import. **A naive install would make the wind job crash at runtime, not at build time.** The existing `type=gha` build cache is inactive (no cache lines in the log, apt layer rebuilt every run); the build takes 3 min 39 s, of which 79 s "exporting layers" and 34 s "importing to docker" cannot be cached away.

**Resolved environment that works on Python 3.10 (clean venv):** `copernicusmarine==2.5.1`, `eccodes==2.50.1` (bundles `eccodeslib==2.48.0.26`; independent of the system `libeccodes-tools`), `xarray==2025.6.1`, `h5netcdf==1.8.3`, `numpy==2.2.6`, `pandas==2.3.3`, `zarr==2.18.3`, `dask`, `pydantic==2.14.4`. NetCDF is opened with xarray's `h5netcdf` engine; the apt `python3-netcdf4` must never be imported. Output is byte-identical on Python 3.10 and 3.12.

## 3. Bounding box (done in PR #10)

`region.py` is the single source of truth:

```python
LON_MIN, LON_MAX = 13.0, 17.5
LAT_MIN, LAT_MAX = 42.5, 45.4      # 45°24'N
DX = DY = 0.02
NX, NY = grid_points(...)          # 226, 146 (round(), and a box that is not a whole number of steps raises)
```

45.4 is the smallest clean value at which both grids reach 45°22': the wind grid ends exactly at 45.40, and the Copernicus 1/24° grid gains its row at 45.396 (the previous row, 45.354, falls short). With 45.4, `int((LAT_MAX - LAT_MIN) / DY)` evaluates to `144.99999999999991`, one row short, hence `round()`.

| | before (44.5°N) | after (45.4°N) |
|---|---|---|
| Wind grid | 226 x 101 | 226 x 146 |
| Wind GRIB (438 msgs) | 15.03 MB | 21.72 MB (49,578 B/msg measured on real data) |
| Marine native grid | 109 x 48 | 109 x 70 (lat 42.5208..45.3958) |
| Marine GRIB (803 msgs) | 4.30 MB | 5.32 MB (51 % land) |
| Files on the Pages site (each twice) | ~39 MB | ~54 MB |

ALADIN covers the new area completely (remap to the 226 x 146 grid: 0 missing values). Also in PR #10: wind-map axes built as `LAT_MIN + DY * arange(ny)` (the old `linspace(LAT_MIN, LAT_MAX, ny)` was only right while the box was a whole number of steps), regenerated coastline (`scripts/make_coastline.py`, previously ended at 45.0°N), region texts, `COPY region.py` in the Dockerfile, tests.

## 4. Architecture

One workflow, `.github/workflows/process-grib.yml`. The processing jobs have no `needs` on each other.

```
 check ---> wind    (CHMI download, CDO, PNG, validate, artifact) ---+
   |                                                                  +--> publish --> gh-pages
   +------> marine  (Copernicus subset, eccodes writer, validate, artifact) -+
```

### 4.1 Triggers and guards

- `schedule: '5 * * * *'` (unchanged), `workflow_dispatch` with inputs:
  - `dry_run` (boolean): run everything, upload the assembled `site/` as an artifact, **never deploy, never save markers**.
  - `force` (boolean): treat both assets as needed even when their markers exist (replaces `gh cache delete`).
  - `simulate` (choice `none`/`wind`/`marine`, effective only with `dry_run`): makes that job fail early, to test that the previous file is kept and the warning appears.
- **Deploy and marker saving require `github.ref == 'refs/heads/main'` and not a dry run.** A dispatch from any other branch can therefore never reach `gh-pages` or poison the markers, whatever `dry_run` says.
- Concurrency: `group: aladin-pipeline-${{ github.ref_name }}`, `cancel-in-progress: false`. A long production run delays the next one instead of racing it; a branch test run cannot cancel or replace a pending production run.
- Job timeouts: `check` 10 min, `wind` 30, `marine` 15, `publish` 15 (a stuck step must not hold the concurrency group for the 6 h default).
- Expression pitfalls to respect when writing the YAML: write every condition as `if: ${{ ... }}` (a bare leading `!` is a YAML tag); compare job outputs with `== 'true'` (the string `'false'` is truthy); `inputs.*` are empty on `schedule` events, so spell out `github.event_name == 'workflow_dispatch' && inputs.force`.

### 4.2 Jobs

| Job | needs | `if` | Does | Output |
|---|---|---|---|---|
| `check` | - | always | Alpine checker image + `check_availability.py` (unchanged), two `lookup-only` cache restores, decide per asset | `timestamp`, `need_wind`, `need_marine` |
| `wind` | `check` | `needs.check.outputs.need_wind == 'true'` | Build image, run the existing processor with `ALADIN_RUN_TIMESTAMP`, validate, upload artifact | `wind-<ts>` |
| `marine` | `check` | `needs.check.outputs.need_marine == 'true'` | Build image, run `marine_grib.py` with the secrets, validate, upload artifact | `marine-<ts>` |
| `publish` | `check`, `wind`, `marine` | `!cancelled() && needs.check.result == 'success' && (need_wind == 'true' \|\| need_marine == 'true')` | Assemble the site (new where valid, else previous from `gh-pages`), status, deploy, markers | `gh-pages` |

`publish` reads `needs.wind.result` / `needs.marine.result` (`success`, `failure`, `skipped`, `cancelled`). A job-level timeout yields `failure`/`cancelled`; both are treated as "no new file". Artifact upload uses `overwrite: true` (re-runs of a run id).

### 4.3 Markers, retry and ordering

- Wind marker: cache key `processed-<ts>` (unchanged, so the existing marker keeps working). Marine marker: `processed-marine-<ts>`. `check` looks both up (`lookup-only`); `force` sets both needs.
- A marker is saved in `publish` for an asset when that asset's state for `<ts>` is final: it was **deployed**, or the publish found it **identical to what is published** (no deploy needed), or it was **rejected by the monotonic guard** (below). A failed asset gets no marker and is retried by the **next scheduled run** (hours, not an hour); the other asset is not re-run. A newer ALADIN timestamp supersedes a failing older one.
- **Monotonic guard:** `check_availability.py` returns `{}` for a run directory on any HTTP error, so a single failing directory can make `check` return an **older** complete timestamp. `build_site.py` never publishes a run older than the one currently published for that asset (the previous `status.json`/filename decides; strings `YYYYMMDDHH` compare correctly). A guarded asset is logged and keeps its previous file and state.
- **Wind timestamp:** `load_and_merge_gribs.find_latest_run()` takes the newest timestamp with *any* file, while `check` picks the newest *complete* one. The wind job passes `ALADIN_RUN_TIMESTAMP=<check ts>`; when set, the script uses that run (searching the run directories for it) instead of its own choice. One small change in the wind script; without it a newer partial upload makes the wind job fail validation against `check`'s timestamp.
- **Bootstrap** (first run after the change): the wind marker for the current timestamp exists, so `need_wind=false`, `need_marine=true`; `publish` takes the wind files from `gh-pages` and adds the new marine file. A previous `gh-pages` without `status.json` is read from the filenames (regex `^(aladin|copernicus)_adriacenter_(\d{10})\.grb$`, which does not match `_latest`).

## 5. Image and build

### 5.1 One image, installed straight into the wind Dockerfile

- apt layer (D2): remove `ncview`; add `--no-install-recommends` to both `apt-get install` lines (hypothesis: the Debian scientific Python stack comes in as Recommends of `nco`/`cdo`; verified by the dry run, not assumed). If the slim build lacks a library CDO or NCO needs at run time, restore recommends (keep `ncview` dropped).
- One `pip3 install` (single resolver pass): `flask requests beautifulsoup4` as today, plus exact pins `copernicusmarine==2.5.1`, `eccodes==2.50.1`, `eccodeslib==2.48.0.26` (and whatever else `eccodeslib` pins via `eckitlib`, taken from a clean resolve), and **`matplotlib>=3.10,<3.11` with `numpy>=2.1`** so pip installs a numpy-2-compatible matplotlib into `/usr/local` instead of leaving Debian's 3.5.1 in place.
- `COPY` the new files: `region.py` (already, PR 1), `marine_grib.py`, `grib_validate.py`, `adriatic_coastline.json`, and the wind script as today.
- **Build-time smoke check** (the last RUN of the dependency layer) so a bad install fails the build, not a run: `python3 -c "import numpy, matplotlib.pyplot, copernicusmarine, eccodes, xarray, h5netcdf; assert numpy.__version__ >= '2.1'; assert eccodes.codes_get_api_version().startswith('2.48'); print('imports OK')"`. This is exactly the import chain `load_and_merge_gribs.py` and `marine_grib.py` use at run time.
- NetCDF is opened with `xarray.open_dataset(..., engine="h5netcdf")`; `netCDF4` is never imported.
- `.dockerignore`: `secrets.yaml`, `.git`, `graft`, `docs`, `tests`, `__pycache__`, so a local `docker build .` cannot send credentials into the build context. (`.gitignore` with `secrets.yaml` is currently only a local untracked file; PR 2 commits it, containing just that entry.)
- Accepted by the owner: a failing install breaks the wind build. The smoke check turns the silent runtime failure described in section 2 into a loud build failure, and the dry run exercises it before merge.

### 5.2 Build strategy (D1)

Replace the raw `docker buildx build` step by `docker/build-push-action@v6` (`load: true`, `cache-from: type=gha,scope=processor`; `cache-to` **only in the `wind` job**, so the two jobs do not write the same scope). The action supplies the cache-service credentials that the raw command lacked. Expected: cache import about 0.5 min instead of rebuilding 300+ packages; the 1.9 min export/load remains until the apt slimming (D2) shrinks the image. With 2-5 runs per day this is a small absolute saving, which is why build-once-and-pull (GHCR) is not worth its moving parts now. The numbers are estimates until measured in the dry run.

## 6. Marine job: `marine_grib.py`

CLI: `python3 /app/marine_grib.py --timestamp <YYYYMMDDHH> [--outdir /data]`. Exit 0 only if a validated file was written. Never prints credential values.

### 6.1 Flow

1. T0 = timestamp (UTC); window T0..T0+`FORECAST_HOURS` (72 h, a constant in `region.py` added by PR 2), 73 hourly steps.
2. Fail fast with a clear message if either credential variable is missing.
3. Subset both datasets (pinned `dataset_version`) with the toolbox API into a temp dir: padded box `LON 12.99..17.51`, `LAT 42.49..LAT_MAX+0.01`, NetCDF. Retry transient errors 3 times with a 30 s pause; bad credentials or unknown datasets fail immediately.
4. Check axes: same longitude/latitude counts and coordinates within 1e-4°; identical time axes, exactly 73 steps of 1 h, first = T0, last = T0+72 h. Crop to the region (`+1e-3` tolerance), use the **currents'** coordinates for the GRIB grid. The expected native counts (109 x 70) are derived from the dataset origin and step (lon0 -17.29167, lat0 30.1875, 1/24°) and `region.py`, and compared with what arrived.
5. Write `copernicus_adriacenter_<ts>.grb` through a temp name and an atomic rename.
6. Self-check with `grib_validate.validate_marine`; on failure delete the file and exit 1.
7. Write `marine_meta.json` (6.5); a failed vintage lookup is non-fatal.

### 6.2 Field mapping (GRIB1, variant B)

| Field | Source | Param | Level type / value |
|---|---|---|---|
| Current u / v | `uo` / `vo` | 49 / 50 | 160 / 0 |
| Wave height | `VHM0` | 100 | 1 / 0 |
| Wave direction (from) | `VMDR` | 107 | 1 / 0 |
| Wave period (peak) | `VTPK` | 108 | 1 / 0 |
| Wind-sea height / direction / period | `VHM0_WW` / `VMDR_WW` / `VTM01_WW` | 102 / 101 / 103 | 1 / 0 |
| Swell height / direction / period | `VHM0_SW1` / `VMDR_SW1` / `VTM01_SW1` | 105 / 104 / 106 | 1 / 0 |

Notes: `VMDR` is the *mean* direction of combined waves and is stored as "primary wave direction" (107); 108 ("primary wave mean period") carries the peak period `VTPK`, as in operational wave GRIBs. The time range indicator stays 0 although the currents are hourly means (same compromise as the wind file). If GRIB2 is ever chosen, remap direction/period to 10.0.14/10.0.15 for OpenCPN after checking the names with eccodes.

### 6.3 Header contract

Identical to the wind file unless noted: centre 89 (kept because the owner's viewer accepted it; the data source is credited in the metadata and README), subCentre 0, table 1, process 2, grid definition 255; `dataDate`/`dataTime` = T0, `stepUnits` 1, `timeRangeIndicator` 0, `P1` = step, `P2` 0; `regular_ll` 109 x 70, first/last point from the currents' coordinates, scan mode 64; **`iDirectionIncrementGiven = jDirectionIncrementGiven = 0` with both increments set to missing**; 12 bits/value; bitmap present, `missingValue` 9999; field-major, step-minor message order. `resolutionAndComponentFlags` is whatever the eccodes sample yields with increments not given (0); this is exactly what the owner tested in qtVlm.

### 6.4 `grib_validate.py`

Module + CLI (`python3 /app/grib_validate.py wind|marine <file> <ts>`), using `eccodes` inside the image. Structural gates; ranges generous so a valid file is never rejected:

- Common: edition 1; every message has reference time T0; per parameter exactly 73 messages with `P1` = 0..72 once each; identical grid in all messages, equal to the expected `Ni/Nj` and corners; no all-missing message; all values finite.
- Missing values are only recognised where a bitmap exists (wind MSLP is about 101,325 Pa, far above the 9999 marker). The step is read with eccodes' `step` key, not `P1` (newer CDO writes the step in two octets); wind accepts time range indicators 0 and 10, marine only 0.
- Wind: 438 messages = parameters {2, 31, 32, 130, 131, 11}; 226 x 146; MSLP 85,000..110,000 Pa, wind speed 0..80 m/s, direction -0.5..360.5, T2m 230..330 K.
- Marine: 803 messages = the 11 mapped parameters; 109 x 70; per field the missing count is identical in all steps and the land share is within 0.25..0.75; |u|,|v| <= 3 m/s, 0 <= Hs <= 15 m, directions -0.5..360.5, periods 0 < T <= 25 s.

### 6.5 `marine_meta.json`

`{"schema":1,"timestamp":"<ts>","datasets":{"currents":{id,doi,version},"waves":{...}},"toolbox":"2.5.1","data_updated_utc":<max arco_updated_date of both or null>,"grid":{"ni":109,"nj":70},"fields":11,"steps":73}` (vintage from `copernicusmarine.describe`).

## 7. Wind job: what changes

Unchanged: `check_availability.py`, `Dockerfile.checker`, the download/CDO/merge/PNG code, the `docker run ... load_and_merge_gribs.py` command, its 30 min timeout.

Changed: (1) `load_and_merge_gribs.py` honours `ALADIN_RUN_TIMESTAMP` (section 4.3); the region import and axis fix are already in PR #10. (2) The steps "Create simple index", "Create README", "Deploy", "Save processed marker", "Cache processed marker" leave the job (they move to `publish`). (3) New last steps: validate `data/aladin_adriacenter_<ts>.grb` inside the container, then `upload-artifact` of the timestamped GRIB and PNG only (no `*_latest.*`; they are re-created by `publish`). The PNG is optional: without it the asset is still valid. (4) The job is renamed `process` -> `wind`.

## 8. Publish job: `build_site.py`

Stdlib-only Python on the runner (no container). Replaces the inline shell for `index.html` and `README.md`.

### 8.1 Asset selection

For `wind` (`aladin_adriacenter_<ts>.grb`, `aladin_wind_<ts>.png`) and `marine` (`copernicus_adriacenter_<ts>.grb`, `marine_meta.json`):

- job `success` and a non-empty artifact -> **new** files, state `ok` (subject to the monotonic guard, 4.3);
- job `skipped` -> previous files and previous state unchanged;
- job `failure`/`cancelled`/no artifact -> previous files, state `stale` (`failed_for = <ts>`, `failed_since` kept if already stale, else now);
- nothing new and nothing previous -> state `missing`.

Previous files come from a checkout of the `gh-pages` branch (`continue-on-error` for the very first deploy). `*_latest.*` are **copies** of the newest timestamped file (not symlinks). The README embeds the wind PNG only if its timestamp equals the published wind run; a new wind file without PNG gets no image (never an older run's image).

### 8.2 `status.json` (schema 1, published)

```json
{"schema": 1, "updated_utc": "2026-11-24T13:41:07Z",
 "assets": {"wind":   {"state": "ok",    "run": "2026112412", "published_utc": "...", "failed_for": null, "failed_since_utc": null},
            "marine": {"state": "stale", "run": "2026112406", "published_utc": "...", "failed_for": "2026112412", "failed_since_utc": "...", "data_updated_utc": "..."}}}
```

Per-attempt timestamps are not published (change detection, 8.4).

### 8.3 Rendered output

- `index.html`: the `.grb` file list with sizes, a status block, and a warning banner when an asset is `stale`/`missing`. No image (decision: wind map stays README-only).
- `README.md` (`gh-pages` branch page): status block and warning, the wind-map image by its **timestamped** filename, "About this data" and "Usage" text (region text generated from `region.py`), the marine variable list, and the attribution: "Generated using E.U. Copernicus Marine Service Information; https://doi.org/10.48670/mds-00359 (currents), https://doi.org/10.48670/mds-00373 (waves)."
- Status example: `Wind (ALADIN): run 2026-11-24 12 UTC, OK, published 2026-11-24 13:41 UTC` / `Water (Copernicus): valid for ALADIN run 2026-11-24 12 UTC, OK, Copernicus data updated 2026-11-24 12:14 UTC`. Warning example: `Warning: the update for ALADIN run 2026-11-24 18 UTC failed for Water (Copernicus). Showing data for run 2026-11-24 12 UTC (stale since 2026-11-24 22:41 UTC).` One extra sentence flags differing runs.
- Limitation (accepted, D6): a static page cannot show that nothing ran; if no workflow run happens at all, the page simply keeps its last content.

### 8.4 Change detection and deploy

`changed=true` iff the set of published files differs **by SHA-256** from `gh-pages`, or `status.json` differs ignoring `updated_utc` (name + size is not enough: a wind GRIB of a given grid has a deterministic size). If false: no deploy (avoids a 50 MB force-push at every failing run), markers still saved per 4.3. Deploy: `peaceiris/actions-gh-pages@v4`, `publish_dir: site`, `force_orphan: true`, only on `main` and not in a dry run; in a dry run `site/` is uploaded as an artifact instead.

## 9. Failure matrix

| Situation | Wind published | Marine published | Page / retry |
|---|---|---|---|
| Both OK | new | new | status OK |
| Wind fails, marine OK | **previous** | new | warning for wind + mismatch note; wind retried at the next scheduled run, marine not re-run |
| Marine fails (credentials, outage), wind OK | new | **previous** | warning for marine; same |
| Both fail, or the image build fails | previous | previous | warning for both (once; later identical failures do not redeploy) |
| Validation of a new file fails | treated like a failed job | | |
| Older run returned by `check` (HTTP error on a run directory) | not replaced by an older run | same | guard logs it |
| No previous file and the job fails | missing | missing | warning |
| `check` fails or CHMI incomplete | unchanged | unchanged | nothing published (as today) |
| Deploy fails | unchanged | unchanged | markers not saved, retried |
| No scheduled run happens | unchanged | unchanged | page cannot show it (D6) |

## 10. Security and credentials

- The secrets reach only the `marine` job's run step as `env:` and are forwarded with `docker run -e NAME` (names only, so values never appear on a command line); GitHub masks them in logs. No `set -x`. The toolbox logs variable names, not values.
- The toolbox gets credentials from the environment only; the container's home is ephemeral, so no credential file survives.
- Artifacts contain only the public output files; the artifact step uses an explicit allowlist of file names, and the dry-run `site/` artifact is built from the same allowlist.
- Branch dispatches by a repo writer can use the secrets (the intended dry-run path); forks cannot (no `pull_request` job uses them).
- Local: `secrets.yaml` (git-ignored, `.dockerignore`d). `scripts/with_secrets.py -- <command>` loads the two keys into the child environment without printing them.

## 11. Testing and rollout

### 11.1 Automated tests (`unittest`, stdlib only; `.github/workflows/tests.yml` runs them on every PR)

- PR 1 (in #10): grid size and edges, 45°22' reached, non-whole-step box rejected, the float case behind `int()`; coastline structure, coverage past the region on every side, containment in the clip box; clip splitting; Dockerfile copies `region.py` and the coastline. Each pin was verified by breaking its invariant.
- PR 2: `marine_grib` (axis/time checks, expected native counts derived from origin/step/region, field mapping completeness, header contract on a small synthetic file read back with eccodes, bitmap round trip); `grib_validate` (accepts a good synthetic file; rejects a missing step, wrong reference time, all-missing field, wrong grid, out-of-range value; accepts directions up to 360.5); `build_site` (table-driven state machine from section 9 incl. bootstrap without `status.json`, `skipped` jobs, monotonic guard, repeated failures not changing the page, new wind without PNG, README embeds the timestamped PNG and never `latest`); the workflow file (parsed with a YAML loader if available in CI, otherwise text assertions): expressions use `== 'true'`, deploy and markers are gated on `main`, timeouts present, secrets only in the marine job.
- Tests that need `numpy`, `eccodes`, `requests` or `matplotlib` skip cleanly when those are not importable (a bare Python runs 86 tests with 37 skipped, all green); `tests.yml` installs them, so CI runs the full set. Mutation checks confirmed that the monotonic guard, the `!cancelled()` condition, the bitmap-only missing-value logic and the secret scoping each have a test that fails when broken.

### 11.2 CI verification (no Docker locally)

Dispatch from the PR 2 branch with `dry_run: true`: image build (slim apt layer, pins, smoke check, cache), marine job end to end with the real secrets, validators, assembled `site/` artifact, then `simulate: wind` and `simulate: marine` (previous file kept, warning shown, other asset new). Record the marine job duration, the real Copernicus download time on a runner and the build time versus today's 3 min 39 s.

### 11.3 PR plan (the owner reviews and merges each)

1. **PR #10 (open):** region/box, axis fix, coastline, Dockerfile `COPY region.py`, tests + `tests.yml`.
2. **PR 2 (stacked on #10, retargeted to `main` after it merges):** Dockerfile (slim, pins, smoke check), `.dockerignore`, `.gitignore`, `marine_grib.py`, `grib_validate.py`, `build_site.py`, `scripts/with_secrets.py`, wind-script timestamp override, workflow restructure, tests, README, this spec.
After PR #10 merges, publish the new wind grid with `gh cache delete processed-<ts>` plus a dispatch (the `force` input arrives with PR 2).

### 11.4 Acceptance criteria

- The marine file passes `validate_marine`; its reference time, step range and unit equal those of the wind file of the same run; it opens in qtVlm (already shown for the spike sample).
- Dry run with `simulate: marine` and `simulate: wind`: the failed asset keeps its previous file in `site/`, the warning appears, the other asset is new.
- A failed run leaves `gh-pages` unchanged apart from status text; a second identical failure does not redeploy.
- The wind GRIB's content for a given run is unchanged by PR 2 (PR #10 changes only the grid).
- No branch other than `main` can deploy or save markers (workflow assertions in the tests).
- The artifacts and `site/` contain only allowlisted file names (no credential files).

## 12. Remaining open items

- Measure in CI: marine job duration, real download time, build time and image size after slimming.
- If the dry-run build shows that `--no-install-recommends` removes something needed, keep recommends and keep `ncview` dropped (section 5.1).
- **Before 2027-01-12:** review and switch the currents pin from `202511` to `202611` (compare the data first; they differ).
- Optional later: GHCR build-once (D1 upgrade), a data-age display (declined for now), an external trigger for more reliable scheduling.
