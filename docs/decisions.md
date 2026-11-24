# Decisions

Why things are the way they are, and what was rejected. Entries 1-7 are **reconstructed** from the git history and the code; entries 8-25 were made with the water file and are **ground truth** (dates 2026-11-24 unless stated). "Owner" is the repository owner.

## Reconstructed (earlier history)

1. **Single orphan commit on `gh-pages`** (`force_orphan`, 2026-03-07). `keep_files` accumulated 2,711 deploy commits (7.3 GB; cleaned to 13 MB on 2026-03-09). Consequence that shaped later work: every deploy replaces the whole branch, so anything not in the deployed directory disappears (see 17).
2. **Checker container** (2026-03-07). A tiny Alpine image finds the newest complete CHMI run first, so the large image is only built when there is something to process.
3. **`remapnn` for wind direction** (2026-03-09). Bilinear interpolation of an angle is wrong near 0°/360°. Everything else stays bilinear.
4. **Download retry** (2026-08-28). CHMI's listing is sometimes incomplete for a while: 3 attempts, 180 s apart, then fail.
5. **Wind map in the `gh-pages` README only** (2026-09-26). The owner does not want an image on the website.
6. **First step only for the map** (PR #9). The CHMI files hold 73 steps; `-seltimestep,1` selects the run's step 0 (a missing selection made the first production render fail silently).
7. **Action versions bumped** (PR #8) after GitHub retired the Node 20 runtime for actions.

## The box and the grids

8. **North limit 45.4°N** (requested: at least 45°22'). It is the smallest value that is a whole number of 0.02° steps *and* at which both grids reach 45°22': the wind grid ends exactly there, the Copernicus lattice has a row at 45.3958 (the previous row, 45.3542, falls short). `region.py` is the single source; `round()` replaces `int()` because `(45.4 - 42.5) / 0.02` is 144.99999999999991. Sizes grew from 15.0 to 21.7 MB (wind) and 4.3 to 5.3 MB (water; the new strip is half land).

## The water file

9. **A second asset, same time frame.** Reference time = ALADIN run, steps 0-72, same region, GRIB1 as the wind file. Built whenever a new ALADIN run is found; Copernicus updates between runs are ignored.
10. **Native 1/24° points, no regridding** (owner). Smaller, no false precision, no coast shrinkage from interpolating a masked field. Rejected: the 0.02° wind grid (4.6x more points, interpolated).
11. **GRIB1 with the grid increments "not given"** (variant B). GRIB1 holds increments in whole millidegrees, so 1/24° would be stored wrong (up to about 2.5 km of decoded error); readers derive the spacing from the corners (about 0.06 km). qtVlm opened this and the two alternatives: A (stored, rounded increments; same display, larger error in other readers) and C (GRIB2, exact but not the wind file's format and with different wave codes in OpenCPN). Owner chose B.
12. **Written with eccodes, not CDO.** CDO's default NetCDF-to-GRIB1 header is unusable and differs between versions (container 2.0.4, newer 2.6.6); eccodes gives explicit control and identical output on Python 3.10 and 3.12.
13. **Currents are ocean + tide** (owner); the model includes tides. Not added: Stokes drift (a keel does not feel it; adds a second dataset). The merged "total current" dataset exists only in the Global product (about 9 km), rejected for resolution.
14. **Eleven fields:** currents u/v; wave height, direction, period; wind sea and primary swell height, direction, period (owner). Not included: maximum wave height, crest height, second swell (no GRIB1 codes).
15. **Follow the newest dataset version automatically** (owner, against the author's recommendation to pin and compare first). The toolbox picks the newest released version. Risk accepted: a new model release changes values on an unchanged grid (202511 versus 202611: 0.07 m/s on average, correlation about 0.5) without any code change. Mitigations: structure, grid, mask, time and range validation; each run records the model system and versions used. Rejected: pinning (needs a manual switch before the retirement of 202511 on 2027-01-12).
16. **Header centre 89 (CHMI's), kept for the water file** so viewers treat both files alike; qtVlm accepted it. The source is credited in the READMEs and `marine_meta.json`, not in the GRIB. Time range indicator 0 for the hourly-mean currents is the same compromise as for the wind file's gust maxima.

## The pipeline

17. **Independent `wind` and `marine` jobs and one shared `publish`.** Because each deploy replaces `gh-pages` (1), keeping the previous file of a failed asset requires one final step that builds the site from "new where valid, else previous from `gh-pages`". Rejected: publishing the water file as a release asset (not next to the wind file); a second workflow that re-adds the file after each deploy (gap, race); a guarded step inside the old deploy (kept the old flow tangled).
18. **Per-asset markers.** The wind key stays `processed-<run>` (no migration); the water file adds `processed-marine-<run>`. A failed asset has no marker and is retried; the other is not re-run.
19. **Older-run guard.** `check` can return an older run when a CHMI directory listing fails; `publish` never replaces a run by an older one.
20. **Deploy only when something changed** (SHA-256), only on `main` and outside dry runs (`DEPLOY`); `dry_run`, `force`, `simulate`; one concurrency group per branch; timeouts on every job. A branch can never deploy by accident.
21. **Status block and warning on both pages** when a file is stale; **no data-age display** (owner): GitHub starts the hourly schedule only 2-5 times a day, and a static page cannot show that nothing ran.
22. **The run is passed to the wind job** (`ALADIN_RUN_TIMESTAMP`): the newest *listed* run can be a partial upload, while `check` returns the newest *complete* one.
23. **One image, with `copernicusmarine` installed straight into the wind `Dockerfile`** (owner: simplicity, one build). Required care: the toolbox needs numpy 2, so matplotlib is pinned to 3.10 in the same pip pass (otherwise Debian's matplotlib 3.5 fails at import, a runtime crash of the wind job); a build-time import check; the apt layer without recommends (smaller; `ncview` dropped) with `bzip2` listed explicitly (found missing by the first dry run). The `gha` build cache works now (`docker/build-push-action`); only `wind` writes it. Rejected: building once and pulling from GHCR (small gain at 2-5 runs a day).
24. **Validation is structural and generous** (`grib_validate.py`): a missing-value marker only where a bitmap exists, the step read with eccodes' `step`, directions up to 360.5, wind time range indicator 0 or 10. The aim is that a valid file is never rejected (which would freeze an asset) while a broken one never replaces a good one.
25. **`unittest`, stdlib only, optional libraries skip** so a bare Python is green and CI runs everything; every important guard was verified by breaking the code once ([testing.md](testing.md)).

## Considered and not done

A data-age display on the page (declined, 21); an external trigger for a reliable schedule; Stokes drift (13); GHCR build-once (23); a side-by-side comparison of dataset versions before following them (15).
