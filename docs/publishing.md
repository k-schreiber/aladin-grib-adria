# Publishing: workflow, publish step, status

Status: ground truth. Verified by tests, `actionlint`, and dry runs on GitHub's runners (run 45304003456 and later).

## Workflow `.github/workflows/process-grib.yml`

Triggers: `schedule` (`5 * * * *`) and `workflow_dispatch` with inputs `dry_run`, `force`, `simulate` (`none|wind|marine`; effective only with `dry_run`). One concurrency group per branch (`aladin-pipeline-<branch>`, no cancellation): a long run delays the next instead of racing it, and a test run can never cancel a production run. `DEPLOY` (workflow `env`) is true only on `refs/heads/main` and not in a dry run; it gates the deploy and the marker steps.

| Job | needs | `if` | Timeout | Does |
|---|---|---|---|---|
| `check` | - | - | 10 min | builds the checker image, runs `check_availability.py`, looks up the two markers, decides `need_wind` / `need_marine` (both true with `force`) |
| `wind` | `check` | `need_wind == 'true'` | 45 | builds the image, runs the wind processor with `ALADIN_RUN_TIMESTAMP`, validates, uploads artifact `wind` |
| `marine` | `check` | `need_marine == 'true'` | 20 | builds the image, runs `marine_grib.py` (the only step with secrets), uploads artifact `marine` |
| `publish` | `check, wind, marine` | `!cancelled() && check succeeded && (need_wind or need_marine)` | 15 | reads the published site, assembles the new one, deploys, saves markers |

Rules that keep the flows independent (each pinned by `tests/test_workflow.py`): `wind` and `marine` depend only on `check`; `publish` uses `!cancelled()` instead of the default success condition; job outputs are compared as strings (`== 'true'`; the string `'false'` is truthy); conditions are written as `${{ ... }}`; only the `marine` job references the secrets. The image builds (processor and checker) use `docker/build-push-action` with the `gha` cache (the earlier raw `docker buildx build` never imported or exported it); only `wind` writes the processor cache.

**Artifacts** contain only the timestamped GRIB and PNG (wind) or GRIB and `marine_meta.json` (marine), never `*_latest*`; `overwrite: true`, 1 day retention.

## Markers (idempotency)

GitHub Actions cache entries with no real content (`.processed-marker`): wind `processed-<run>` (unchanged from before the water file existed), water `processed-marine-<run>`. `check` looks them up (`lookup-only`); `publish` saves one for an asset whose outcome is `new` (after a successful deploy) or `guarded` (rejected as older than the published run; deployed or unchanged). A `new` asset always changes `published_utc`, so it always deploys. A failed or kept asset gets no marker and is retried at the next scheduled run, while the other is not re-run. Markers are only saved on `main` outside dry runs. Bootstrap: when the wind marker for the current run already exists, only the water file is built and the wind file is taken from `gh-pages`.

## The publish step: `build_site.py`

Standard library only, runs on the runner. Inputs: this run's result per job, the artifacts, and a checkout of the current `gh-pages` branch (`prev`).

State per asset (`decide()` is a pure function):

| Job result | New file usable? | Run vs published | Outcome | State |
|---|---|---|---|---|
| success | yes | newer or equal | `new` | `ok` (this run) |
| success | yes | **older** than published | `guarded` | unchanged (never go back; a failing run directory can make `check` return an older run) |
| success | no (missing, empty, wrong run) | - | `failed` | `stale` / `missing` |
| skipped | - | published exists | `kept` | unchanged |
| skipped | - | nothing published | `failed` | `missing` |
| failure / cancelled | - | published exists | `failed` | `stale`: previous file kept, `failed_for` = this run, `failed_since` kept from an earlier failure |
| failure / cancelled | - | nothing published | `failed` | `missing` |

Published files come from the artifact (`new`) or from `prev` (everything else). `*_latest.*` are **copies** of the newest timestamped file (peaceiris dereferences symlinks anyway). The wind map is published only if its run equals the wind file's run; a new wind file without a PNG gets no image, never an older one. The previous state is read from `prev/status.json`, or, for a `gh-pages` made by the old workflow, from the file names (`aladin_adriacenter_<10 digits>.grb`; `_latest` never matches).

**`status.json`** (schema 1; compared between runs without `updated_utc`, together with the SHA-256 of the data files):

```json
{"schema": 1, "updated_utc": "...",
 "assets": {"wind":   {"state": "ok|stale|missing", "run": "YYYYMMDDHH|null", "published_utc": "...|null",
                       "failed_for": "run|null", "failed_since_utc": "...|null"},
            "marine": {"...same...", "data_updated_utc": "Copernicus dataset update time",
                       "model_systems": {"currents": "MedFS EAS10", "waves": "MEDWAM4"}}}}
```

A repeated failure keeps `failed_since_utc` in every state, `missing` included, so it never changes the site.

**Reading the published site.** `publish` first asks `git ls-remote` whether `gh-pages` exists. Only "no such branch" (the very first deploy) runs without a previous site; any other failure of that check or of the checkout fails the job, and `build_site.py` refuses a `--prev` directory that does not exist. Without this, an unreadable `gh-pages` would make every failed asset "missing" and the deploy would delete its published file.

**Generated pages.** `index.html` (website): warning banners, data status lines, `.grb` list with sizes, attribution; no image. `README.md` (the `gh-pages` branch page): status, warnings, the wind map by its **timestamped** file name (the `latest` copy is never referenced), data description, usage, attribution. Warnings: "The update for ALADIN run X failed for Y. Showing data for run Z (stale since T)."; "... is not available ..." for `missing`; "Wind and water files belong to different ALADIN runs" when the runs differ.

**Change detection.** `changed` is true if the SHA-256 of any published data file differs from `prev`, or `status.json` differs ignoring `updated_utc`. If false there is no deploy (a persistent failure does not rewrite 50 MB every run). Because a new asset always changes `published_utc`, `force` or an evicted marker always redeploys the roughly 54 MB. Deploy: `peaceiris/actions-gh-pages` with `force_orphan: true`, a single-commit branch (history would otherwise grow; it once reached 2,711 commits and 7.3 GB).

**Outputs for the workflow:** `changed`, `save_wind_marker`, `save_marine_marker` (true for `new` and `guarded`). The job summary lists each asset's result, the model systems used and any retirement warning.

## Dry run, force, simulate

- `dry_run`: everything runs, nothing is deployed or remembered; the assembled site is uploaded as artifact `site`.
- `force`: process both assets even if their markers exist (replaces deleting cache entries by hand).
- `simulate` (with `dry_run`): fail the `wind` or `marine` job on purpose to see the previous-file and warning behaviour.
- Recipe and checks: [operations.md](operations.md).
