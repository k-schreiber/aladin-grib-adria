# Testing

Status: ground truth.

## Running

```bash
python3 -m unittest discover -s tests -t .
```

Standard-library `unittest`, no network, Docker or CDO. Tests that need `numpy`, `eccodes`, `requests` or `matplotlib` skip themselves when those are missing, so a bare Python is green; `.github/workflows/tests.yml` installs them (`pip install numpy matplotlib requests beautifulsoup4 eccodes xarray h5netcdf h5py pyyaml`), so CI runs everything on every pull request (about 100 tests).

## What each file guards

| File | Guards |
|---|---|
| `tests/test_region.py` | grid size (226 x 146), box edges, 45°22' reached, a box that is not a whole number of steps is rejected, the `int()` row-loss case; coastline structure, containment in the clip box and **coverage past the region on all sides**; the Dockerfile copies the five files the code needs (`load_and_merge_gribs.py`, `region.py`, `adriatic_coastline.json`, `marine_grib.py`, `grib_validate.py`; not `server.py`, `start.sh` or `process.cron`), lists every external tool the wind script runs and sets `PYTHONUNBUFFERED`; `secrets.yaml` is in `.gitignore` and `.dockerignore` |
| `tests/test_marine_grib.py` | timestamp parsing; request box and the wave grid's edge column; field table complete and consistent with the validator; native grid counts (109 x 70) and 73-step window; axis and time checks; retry classification; no `dataset_version` requested; catalogue lookup before and after a release; DOIs in the attribution equal the datasets'; half-hour time offsets rejected; **`load_data` on synthetic NetCDF files** (edge points cropped, values on the right cells, model system returned, shifted time axis and wrong dimension order rejected); the **GRIB header contract** read back with eccodes; a full-size write + validate round trip |
| `tests/test_grib_validate.py` | validator accepts/rejects: complete file, missing step or parameter, wrong reference time, field without values, out-of-range value, wrong grid, GRIB2, mask change, no land; accepts direction 360.04, both CDO time encodings, and MSLP far above the 9999 marker |
| `tests/test_build_site.py` | the publish state machine: bootstrap, failed wind, failed marine, both failed, nothing published, recovery, older run, repeated failure not changing the site, same size but different content, README embeds only the timestamped PNG, no image on the website, attribution, `status.json`, the model system on the pages, a repeated failure with nothing published changing nothing, `latest` files are copies, a missing `--prev` directory is an error, command-line outputs |
| `tests/test_workflow.py` | structure of `process-grib.yml`: no `needs` between `wind` and `marine`, `!cancelled()` in `publish`, string comparisons, timeouts, secrets only in `marine`, deploy and markers gated on `DEPLOY`, per-branch concurrency, marker keys, timestamp pinned for the wind job, simulate only in dry runs, artifact contents, **the published site must be readable** (no `continue-on-error` in `publish`; only "no such branch" skips the checkout) |
| `tests/test_wind_timestamp.py` | `find_latest_run()` with and without `ALADIN_RUN_TIMESTAMP` (a newer partial upload does not win; an unknown run is an error) |
| `tests/helpers.py` | `write_grib1()`: small synthetic GRIB1 files for validator tests |

## Are the tests meaningful?

Each important guard was checked by breaking the code and watching a test fail (restore afterwards):

| Break | Caught by |
|---|---|
| remove the older-run guard in `build_site.decide` | `test_an_older_run_never_replaces_a_newer_one` |
| remove `!cancelled()` from `publish` | `test_publish_runs_even_when_wind_or_marine_failed` |
| treat values >= 9998 as missing without a bitmap | the three wind-validator tests with pressure data |
| put a Copernicus secret into another job | `test_the_copernicus_secrets_are_only_used_by_the_marine_job` |
| old coastline (ends at 45.0°N) | `test_reaches_past_the_region_on_every_side` |
| box that is not a whole number of steps | import of `region` fails |
| remove `bzip2` or `region.py` from the Dockerfile | the Dockerfile tests |
| let the `gh-pages` checkout in `publish` fail silently again | `test_the_published_site_is_required_unless_the_branch_does_not_exist_yet` |
| forget the `missing` state between runs | `test_a_repeated_failure_with_nothing_ever_published_does_not_change_the_site` |
| truncate the Copernicus time axis to hours | `test_a_time_axis_shifted_by_half_an_hour_is_rejected` |
| accept a `--prev` directory that does not exist | `test_a_prev_directory_that_is_missing_is_an_error_not_an_empty_site` |

## What the unit tests cannot cover

CDO runs, the Docker build (and the `COPY`/`ENV` lines only as text), GitHub Actions semantics, and the live Copernicus service. These are covered by:

- `actionlint` on the workflows (it understands expression syntax and contexts);
- the **dry run** on GitHub's runners ([operations.md](operations.md)), followed by downloading the `site` artifact and running `grib_validate.py` on it; this found the missing `bzip2` and confirmed the numpy/matplotlib resolution;
- real-data checks done once and repeatable: the validator accepts the real published wind file; `marine_grib.py` against the live service reproduces the qtVlm-tested file byte for byte; the size formulas ([grib-format.md](grib-format.md)) match the CI-built files exactly.

## Writing tests

- Put them in `tests/`, import project modules by name (the repository root is on the path), keep them network-free.
- Guard optional libraries with `unittest.skipUnless(...)` using `tests.helpers.HAVE_ECCODES` / `HAVE_NUMPY`; import the library inside `setUpClass`.
- Use `tests.helpers.write_grib1` for synthetic GRIB files and `tempfile.TemporaryDirectory` for output.
- When fixing a bug, add the test that would have caught it and break the code once to confirm it fails.
