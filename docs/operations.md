# Operations

Status: ground truth, except the notes marked *(not verified)* and the self-hosted variant (reconstructed).

## Credentials

- GitHub repository secrets `COPERNICUSMARINE_SERVICE_USERNAME` and `COPERNICUSMARINE_SERVICE_PASSWORD` (free Copernicus Marine account). Only the `marine` job uses them; they are forwarded into `docker run` by name.
- Local: `secrets.yaml` in the repository root with the same two keys (git-ignored, also excluded from Docker builds by `.dockerignore`). `scripts/with_secrets.py -- <command>` loads them into the command's environment without printing them.

## Everyday commands

```bash
# unit tests (stdlib; optional libs enable more tests)
python3 -m unittest discover -s tests -t .

# build the water file locally (Python 3.10-3.13; the toolbox does not install on very new Pythons)
python3 scripts/with_secrets.py -- uv run --python 3.12 --with copernicusmarine==2.5.1 --with eccodes==2.50.1 \
  python marine_grib.py --timestamp 2026112318 --outdir out

# validate a file
python3 grib_validate.py wind   data/aladin_adriacenter_2026112318.grb   2026112318   # needs eccodes
python3 grib_validate.py marine out/copernicus_adriacenter_2026112318.grb 2026112318

# lint the workflows
uv tool run --from actionlint-py actionlint .github/workflows/*.yml
```

## Run the pipeline by hand

| Goal | Command |
|---|---|
| process the latest run again (e.g. after changing the box) | `gh workflow run process-grib.yml -f force=true` |
| test a branch without publishing | `gh workflow run process-grib.yml --ref <branch> -f dry_run=true -f force=true`, then `gh run watch <id>` and `gh run download <id> -n site` |
| see the previous-file and warning behaviour | add `-f simulate=wind` or `-f simulate=marine` to a dry run |
| forget that a run was processed | `gh cache delete processed-<run>` (wind) or `processed-marine-<run>` |
| inspect what is published | `gh api repos/k-schreiber/aladin-grib-adria/git/trees/gh-pages`, or open `status.json` on the Pages site |

After a dry run, download the `site` artifact and run `grib_validate.py` on both files: that is the independent check of what the container produced. Dry runs from branches never deploy and never save markers (`DEPLOY`, see [publishing.md](publishing.md)).

## Troubleshooting

| Symptom | Likely cause | Look at |
|---|---|---|
| nothing updates for hours | GitHub fires the hourly schedule only 2-5 times a day, or CHMI has no complete run yet | `gh run list --workflow=process-grib.yml` |
| wind STALE | wind job failed: CHMI upload incomplete (3 attempts), CDO error, or validation (message count, grid, time) | `wind` job log, step "Process GRIB files" / "Validate the wind GRIB" |
| water STALE | credentials missing or rejected, Copernicus outage, a new dataset version changed structure (grid, variables, time axis), timeout | `marine` job log; the error line starts with `Error: marine GRIB failed:` |
| `No such file or directory: 'bzip2'` (or another tool) | apt layer is installed without recommends and the tool is not listed | `Dockerfile`; `tests/test_region.py` should have caught it |
| `ModuleNotFoundError` for a project module in the container | file missing from the `COPY` line | `Dockerfile`; same test |
| numpy / matplotlib import error | the pip pins clash again (copernicusmarine needs numpy 2, so matplotlib must be 3.10) | the build-time import check in the `Dockerfile` should fail the build first |
| published wind and water runs differ | one job failed earlier and was not yet retried | status block on the page |

## Routine maintenance

- **Copernicus model releases.** The water file follows the newest released dataset version automatically. Read the "model systems used / versions in use" line in the `marine` job log (and the retirement warning) now and then; after a release compare a few fields with the previous version if the data look different. Copernicus' roadmap page lists transitions.
- **Dependency pins** (`Dockerfile`): `copernicusmarine`, `eccodes`, `eccodeslib`, `eckitlib` are pinned together; bump them together and let the build-time import check and a dry run confirm. matplotlib must stay below 3.11 while the image uses Python 3.10.
- **GitHub Actions versions** are pinned by major version in the workflows; watch for Node runtime deprecation warnings in run logs.
- **CHMI layout.** Directory names, file names and the variable list are hard-coded in `check_availability.py` and `load_and_merge_gribs.py`.

## Checklists

**Change the region** (`region.py`): keep the box a whole number of 0.02° steps (the module raises otherwise); run `python3 scripts/make_coastline.py`; check that ALADIN covers the box (remap onto the grid, count missing points) and that the Copernicus lattice has points in it; update sizes in [grib-format.md](grib-format.md) if you publish them; run the tests; after merging run once with `force`. The coastline, grid, validators, README text and pages all follow `region.py`.

**Add a water field:** add it to `marine_grib.FIELDS` (variable, GRIB1 parameter, level type, source) and `grib_validate.MARINE_RANGES`, update the parameter table in [grib-format.md](grib-format.md), update message counts in the tests (803 = 11 x 73), and check the parameter in the viewers.

**Add a wind variable:** add it to `VARS` in `load_and_merge_gribs.py` and `REQUIRED_VARS` in `check_availability.py`, its parameter to `grib_validate.WIND_RANGES`, and update the tests (438 = 6 x 73).

## Known limitations and inconsistencies

- **Schedule.** Few runs per day; a static page cannot show that nothing ran (a data-age display was considered and declined).
- GRIB1 cannot store the 1/24° increment; the water file omits it ([grib-format.md](grib-format.md)).
- The README names the local container `aladin-grib`, `docker-compose.yml` names it `aladin-grib-processor`.
- `fly.toml` has no `[mounts]` section although the README creates a volume *(not verified at runtime)*.
- The self-hosted variant builds neither the water file nor serves the wind map.
- Gust parameters 130/131 are mapped to the CHMI gust variables by inference *(not verified)*.
