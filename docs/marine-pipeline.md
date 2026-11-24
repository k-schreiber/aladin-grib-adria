# Water pipeline (Copernicus Marine)

Status: ground truth. Verified by running `marine_grib.py` against the live service locally (Python 3.10) and on GitHub's runners, and by the unit tests.

## Source

Product `MEDSEA_ANALYSISFORECAST_PHY_006_013` (physics) and `MEDSEA_ANALYSISFORECAST_WAV_006_017` (waves); a coupled NEMO + WaveWatch-III model that includes tides, 1/24° (about 4 km), run by CMCC.

| Use | Dataset id | Variables | DOI |
|---|---|---|---|
| currents | `cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m` | `uo`, `vo` (hourly mean, surface) | 10.48670/mds-00359 |
| waves | `cmems_mod_med_wav_anfc_4.2km_PT1H-i` | `VHM0 VMDR VTPK VHM0_WW VMDR_WW VTM01_WW VHM0_SW1 VMDR_SW1 VTM01_SW1` (hourly, instantaneous) | 10.48670/mds-00373 |

- Both reach about nine days into the future and hold the past, so the 72 h window of any recent ALADIN run is always covered.
- There is **no merged "total current" dataset** in this product (the Global product has one). Currents are ocean plus tide; the wave model's Stokes drift (`VSDX/VSDY`) is **not** added.
- Access needs a free Copernicus Marine account. The toolbox reads `COPERNICUSMARINE_SERVICE_USERNAME` / `COPERNICUSMARINE_SERVICE_PASSWORD` from the environment.
- Attribution is required and appears on both pages: "Generated using E.U. Copernicus Marine Service Information" with both DOIs.

## Flow: `marine_grib.py --timestamp <run> [--outdir DIR]`

Exit 0 only if a validated file was written. Credential values are never printed.

1. **Parse** the run (`YYYYMMDDHH`, invalid input exits 1) and require both credential variables.
2. **Fetch** each dataset with `copernicusmarine.subset` (server-side subset, NetCDF): window `[run, run + 72 h]`, box padded by 0.01° on every side (`PAD`; see the wave-grid note in [grib-format.md](grib-format.md)). Up to 3 attempts, 30 s apart; errors that retrying cannot fix (credentials, unknown variable, bad coordinates or date) fail immediately (`is_permanent`). No dataset version is requested, so the toolbox uses the newest released one (below). Typical download: 20-80 s in total (the toolbox reports far larger "transfer sizes" because it reads whole chunks).
3. **Open** both files with xarray's `h5netcdf` engine (`netCDF4` is never imported), **crop** each to the exact box (tolerance 1e-3°), and **check** (`check_axes`): identical longitude and latitude axes (within 1e-4°), identical time axes of exactly 73 hourly steps from the run to run + 72 h (compared to the second, so a half-hour offset is caught), and a grid of exactly `region.MARINE_NX x MARINE_NY` (109 x 70).
4. **Write** the GRIB (`write_grib`): one eccodes message per field and step from the `regular_ll_sfc_grib1` sample, header as in [grib-format.md](grib-format.md); NaN (land) becomes missing through the bitmap. The grid is the currents' coordinates. Written to a temporary name and renamed.
5. **Validate** (`grib_validate.validate_marine`) against the grid derived from `region.py` (not from the downloaded data). On failure the file is deleted and the job exits 1.
6. **Record** `marine_meta.json` next to the file: dataset ids and DOIs, `data_updated_utc`, the model system that produced each file (`model_systems`: the NetCDF `source` attribute, e.g. `MedFS EAS10`), `versions_in_use`, retirement dates of those versions (`retires_utc`), grid and message count. `marine_meta.json` stays in the CI artifact (1 day) and the job summary; `publish` copies `data_updated_utc` and `model_systems` into the published `status.json` and the status line. Only `model_systems` comes from the data; `versions_in_use` and the retirement dates are inferred from the catalogue (newest version already released) after the download. Catalogue lookups are informational; a failure there never fails the run.

CDO is deliberately not used for this file: its NetCDF-to-GRIB1 default (centre 0, parameters numbered 1..n, per-message analysis times in minutes) is unusable and differs between CDO versions (the container has 2.0.4).

## Dataset versions: follow the newest

The toolbox picks the newest dataset version whose release time has passed. The owner decided to trust Copernicus and follow it automatically. Consequences:

- A new **model release changes the values on an unchanged grid**. Measured: currents `202511` (`MedFS EAS10`) versus `202611` (`MedFS EAS11`, NEMO 5.0.1, new vertical mixing, 57 instead of 39 rivers, per the Copernicus roadmap page) differ by 0.07 m/s per component on average (0.11 m/s as a vector) on the same 72 h window (same grid and land mask), correlation about 0.5; the new version has stronger currents (rms of u 0.099 against 0.082 m/s, of v 0.105 against 0.085).
- `202511` is retired on **2027-01-12** (both versions are served in parallel until then). It is unknown whether a retired version stays downloadable *(not verified)*.
- Safety net: structure, grid, mask, time axis and value ranges are validated on every run; a version that changes any of them makes the job fail and the previous file stays published. A change in the *values* alone is not detected; each run logs which model system and versions it used.
- Each run prints `Copernicus model systems used: ... dataset versions in use: ...` and warns only if a version in use has a retirement date.

## Known limits

- Coast and channels: 4 km cells do not resolve the channels between the Croatian islands; about 51 % of the box is land and missing.
- Currents are hourly **means** labelled with the centre of the hour; waves are instantaneous ([grib-format.md](grib-format.md) section 1).
- The data vintage depends on when the job runs: the 00 UTC ALADIN run is processed before Copernicus' daily update, so its first hours come from the previous day's forecast cycle.
- The download volume reported by the toolbox for the waves (about 1.8 GB) is read in about 30-90 s; on a slow runner this could approach the 15-minute job timeout *(not seen)*.
