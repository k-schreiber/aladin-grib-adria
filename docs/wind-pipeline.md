# Wind pipeline (CHMI ALADIN)

Status: **reconstructed** from `check_availability.py`, `load_and_merge_gribs.py`, the deployment files, the git history and one decoded published file. Behaviour that was only read in the code, not run, is marked *(not verified)*.

## Source data

CHMI publishes ALADIN 2.3 km (Lambert conformal, 1053 x 837 points at 2.325 km) at
`https://opendata.chmi.cz/meteorology/weather/nwp_aladin/Lambert_2.3km/<00|06|12|18>/`.
Per run and variable one file: `ALADLAMB4opendata_<YYYYMMDDHH>_<VARIABLE>.grb.bz2` (about 30-80 MB; 92 MB unpacked for wind speed), holding **73 hourly steps** (0-72 h) of one variable. `<YYYYMMDDHH>` is the run (model start) time; it was checked that it equals the GRIB reference time. The domain extends far beyond the Adriatic (checked: remapping onto the full box gives no missing points).

Required variables (`check_availability.REQUIRED_VARS`, `load_and_merge_gribs.VARS`):

| CHMI variable | Content (see [grib-format.md](grib-format.md) for the output parameter) |
|---|---|
| `MSLPRESSURE` | mean sea level pressure, Pa |
| `CLSWIND_SPEED` / `CLSWIND_DIREC` | 10 m wind speed (m/s) / direction (degrees, from) |
| `CLSU_RAF_MOD_XFU` / `CLSV_RAF_MOD_XFU` | maximum gust in the next hour, u / v (m/s) |
| `CLSTEMPERATURE` | 2 m temperature, K |

## 1. Finding a run: `check_availability.py`

Runs in the Alpine image (`Dockerfile.checker`; `requests`, `beautifulsoup4`). For each of the four run directories it lists the HTML index and collects `{timestamp: set(variables)}` from links starting with `ALADLAMB4opendata_` (name split on the first two underscores, so `CLSU_RAF_MOD_XFU` stays intact; the suffix `.grb` / `.grb.bz2` is stripped). It prints the **newest timestamp whose variable set contains all six** and exits 0; otherwise it prints a message to stderr and exits 1 (the workflow reads an empty timestamp as "nothing new").

Limits: it checks that files are *listed*, not that they are fully uploaded; a directory that fails (HTTP error or exception) is silently treated as empty, so the result can then be an **older** run (guarded in [publishing.md](publishing.md)). It runs at module level, not as functions.

## 2. Processing: `load_and_merge_gribs.py`

Constants: `WORKDIR=/tmp/aladin`, `OUTDIR` (env, default `/data`), box and grid from `region.py`. `main()` runs the steps below and exits 1 on any exception.

1. **`find_latest_run()`**: the newest timestamp that has *any* file in any run directory, or the run in `ALADIN_RUN_TIMESTAMP` when set (the workflow passes the run `check` found, because the newest listed run can be a partial upload; an unknown run raises).
2. **`download_latest_files(dir, ts)`**: up to 3 attempts, 180 s apart; **the retry only covers an incomplete listing** (see known behaviours). Each attempt re-lists the directory, downloads the six `.bz2` files that are present (HTTP timeout 60 s, 1 MB chunks, files already on disk are reused), and unpacks them with `bzip2 -df`. It returns when all six exist; after the third attempt it raises "Incomplete ... CHMI upload appears stuck".
3. **`merge_gribs(files, ts)`**:
   - `create_target_grid()` writes `WORKDIR/adriatic_grid.txt` (`gridtype = lonlat`, `xsize/ysize = NX/NY`, `xfirst/yfirst = 13.0/42.5`, `xinc/yinc = 0.02`).
   - For every file: `cdo -s sellonlatbox,13.0,17.5,42.5,45.4 -<remap>,<grid> in out` where `<remap>` is **`remapnn` for `CLSWIND_DIREC` and `remapbil` for all others**. CDO applies the inner operator first, so the file is remapped onto the target grid, then cut to the box (a no-op, since the grid already is the box). All 73 steps are processed. If this fails, a two-step fallback (remap, then cut) is tried; a file that still fails is skipped with a log line. Output: `WORKDIR/run_<ts>/processed/<name>.processed.grb`.
   - `cdo -s merge <processed files> OUTDIR/aladin_adriacenter_<ts>.grb`; failure raises. The merge interleaves the variables, so the file is ordered step by step ([grib-format.md](grib-format.md)). **If some variables failed to process, the merge still runs with the rest**: the incomplete file is caught later by `grib_validate.py` (438 messages), not here.
   - `OUTDIR/aladin_adriacenter_latest.grb` is updated through a temporary symlink and rename (atomic). The publish step later turns it into a real copy.
   - `render_wind_map()` (below), wrapped so a rendering error is only logged.
   - `cleanup_old_runs()` keeps the three newest `run_*` directories (by modification time) in `WORKDIR`.
4. Output parameters, header and sizes: [grib-format.md](grib-format.md).

**Why nearest-neighbour for direction:** direction is circular (0°/360°); bilinear interpolation between 359° and 1° gives 180°. All other values are bilinearly interpolated (so output values are interpolated, not original model values).

**`-s`** silences CDO's warnings, so edge or mask problems are invisible in the logs. `VARS` also holds short names (`MSLP`, `WDIR10`, ...) that nothing uses.

### Known behaviours a developer should expect

- **Raw downloads are never cleaned.** `cleanup_old_runs()` removes only old `run_*` directories; the unpacked CHMI files (about 0.5 GB per run) stay in `WORKDIR`. Harmless in CI (fresh runner), unbounded growth in the self-hosted variant.
- **Only the request is protected, not the transfer.** `download_file_with_progress()` catches errors of the initial request; an error while streaming propagates and the run exits 1 without a retry. The "3 attempts" apply to an incomplete listing, not to a broken download.
- **A truncated `.bz2` is never re-downloaded**: an existing file is reused, `bzip2 -df` then fails. In CI the workspace is fresh, so a retry works; in the self-hosted variant (persistent `/tmp/aladin`) the same run fails every hour until the file is removed.
- **No lock** between the cron job and the run `start.sh` launches in the background; they can overlap.
- **Partial processing:** variables that fail in CDO are skipped and the merge continues (only `grib_validate.py` notices).
- **Raw time encoding:** the CHMI files use time range indicator 1 at step 0 and 10 afterwards; CDO 2.0.4 rewrites all steps as indicator 0 ([grib-format.md](grib-format.md)).

## 3. Wind map: `render_wind_map()`

Renders `aladin_wind_<ts>.png` (+ `aladin_wind_latest.png`) from the processed speed and direction files. Values are read with `cdo -s output -seltimestep,1 <file>`: **only step 0** is drawn, and the 73-step files are why `-seltimestep,1` is needed (without it the value count is 73 times too large and the reshape check fails; this was a real bug, fixed in PR #9). The text values are reshaped to `(NY, NX)` (longitude fastest, south first); CDO's missing-value marker (about 9e33, treated as `|v| > 1e6`) becomes NaN.

Drawing (matplotlib, Agg backend): speed as a `viridis` colour mesh, white arrows from `u = -s sin(d)`, `v = -s cos(d)` on every 7th point, black coastline from `adriatic_coastline.json`, aspect `1/cos(mid-latitude)`, title with the run time, 10x7 in at 130 dpi. Axes are built as `LAT_MIN + DY * arange(NY)` (not `linspace` over the box, which is only right when the box is a whole number of steps).

The coastline file is Natural Earth 10 m (public domain) clipped to the box plus 0.5° by `scripts/make_coastline.py`; regenerate it whenever the box changes (a test enforces coverage). The PNG appears only in the `gh-pages` README, never on the website.

## 4. Image and container

`Dockerfile` (Ubuntu 22.04): apt without recommends `bzip2 cdo libeccodes-tools nco` and `cron python3-pip`; one `pip3 install` pass for `flask requests beautifulsoup4 numpy>=2.1 matplotlib>=3.10,<3.11` plus the Copernicus packages ([marine-pipeline.md](marine-pipeline.md)); a build-time import check; the application files are copied to `/app`. A test requires every external tool the wind script runs to be listed (`bzip2` was once missing after the apt layer was slimmed, which only a CI run caught).

## 5. Self-hosted variant (optional; wind reconstructed, water ground truth)

- `start.sh`: writes the cron environment, starts `cron`, runs both processors once in the background, then `exec python3 server.py`. `process.cron` runs the processor at minute 0 of every hour and, every 15 minutes, `local_update_water.py`: it asks `check_marine.py` for the newest Copernicus update, builds the water file with `marine_grib.py` only when the key differs from `OUTDIR/.water_key`, writes `copernicus_adriacenter_latest.grb` atomically and keeps the four newest files. The credentials come from the container environment (docker-compose passes them through; `start.sh` hands them to cron via a 0600 `cron_env.sh`); without them the water step only logs. There is **no idempotency check**: every hour re-merges the latest run (downloads are reused while `/tmp/aladin` lives).
- `server.py` (Flask, port 8080 or `PORT`): `/` lists `aladin_adriacenter_*.grb` newest first with size and run time; `/aladin_adriacenter_latest.grb` and `/files/<name>` download (only names matching `aladin_adriacenter_*.grb` or `copernicus_adriacenter_*.grb`). It also serves the water files (`copernicus_adriacenter_*.grb`, `copernicus_adriacenter_latest.grb`), not the PNG.
- `docker-compose.yml`: builds the image, port 8080, volume `./data:/data`, `OUTDIR=/data`, restart unless stopped, container name `aladin-grib-processor`.
- `fly.toml` (Fly.io, region `fra`, 1 shared CPU, 1 GB, machines stop when idle and start on request): contains **no `[mounts]` section**, so the volume the README tells you to create is not mounted *(not verified at runtime)*; a stopped machine runs no cron, so the Fly variant only updates while it is awake *(inferred)*. Memory with numpy 2 / matplotlib 3.10 on 1 GB is untested.
