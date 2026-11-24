# Further data sources (survey)

Status: **survey, nothing implemented.** Dataset ids, variables, grids and time axes were read with `copernicusmarine describe` (metadata only, no login, no download) on 2026-11-24. Latencies, CAMS and other non-marine details come from web search. Anything not checked is marked *(not verified)*. Re-check ids before implementing: Copernicus renames and versions datasets.

The question was: which Copernicus products beyond the eleven fields of the water file ([grib-format.md](grib-format.md) section 4) would help sailing navigation in the region box? A product only fits the pipeline if it is a gridded forecast that covers the box and the water file's 108 h. Observations are past-only and usually gappy, so they suit validation better than a GRIB layer.

## Recommendation

1. **Add sea level `zos` and sea surface temperature to the water file.** Both come from the Med physics product on the same 1/24° grid and are hourly, with about 8.5 days of forecast. Both are one more `subset` call each, with no regridding. Their GRIB1 codes are likely NCEP table 2 code 82 (deviation of sea level from mean) and code 80 (water temperature) *(not verified)*. Check how qtVlm displays them before deciding (see section 8 of [grib-format.md](grib-format.md)).
2. **Max wave height VCMX, wave peak direction VPED and the second swell (SW2)** are in the wave dataset that is already downloaded, so they would cost no extra request. VCMX and SW2 height have no GRIB1 code (decision 14 in [decisions.md](decisions.md)), so they need GRIB2 or a non-standard code first. VPED could use code 107 only by replacing VMDR, so it is not worth adding on its own.
3. **Validation, not publication:** the observed wind L4 product and the in-situ buoys and tide gauges could be compared against ALADIN and the water file in a log or job summary.
4. **Everything else:** skip it (tables below).

## Copernicus Marine forecasts

| Dataset | Variables | Grid / step | Forecast | Use for sailing |
|---|---|---|---|---|
| `cmems_mod_med_phy-ssh_anfc_4.2km-2D_PT1H-m` | `zos`, sea surface height above geoid, includes tide and surge (m) | 1/24° / 1 h | about 8.5 d | **High:** depth in harbours and shallows, sirocco setup, seiches |
| `cmems_mod_med_phy-ssh_anfc_4.2km_PT15M-i` | `zos` | 1/24° / 15 min | about 3.5 d | Low: too short for 108 h; 1 h is enough |
| `cmems_mod_med_phy-tem_anfc_4.2km-2D_PT1H-m` | `thetao`, near-surface temperature (°C) | 1/24° / 1 h | about 8.5 d | **High:** fog and thermal-breeze hints, cold-water safety |
| `cmems_mod_med_wav_anfc_4.2km_PT1H-i` (already used) | unused fields: `VCMX` max wave height, `VMXL` max crest height, `VHM0_SW2 VMDR_SW2 VTM01_SW2` second swell, `VPED` peak direction, `VSDX VSDY` Stokes drift, `VTM02 VTM10` | 1/24° / 1 h | about 9 d | VCMX **high** (safety margin in steep seas); SW2 and VPED medium (crossing seas); the rest low |
| `cmems_mod_glo_phy_anfc_merged-sl_PT1H-i` | `ocean_tide`, `total_sea_level`, `invert_barometer` and related fields | 1/12° / 1 h | about 9 d | Medium: separates tide from surge, which the Med `zos` does not; Adriatic quality at 9 km *(not verified)* |
| `cmems_mod_glo_phy_anfc_merged-uv_PT1H-i` | `utotal vtotal` (ocean + tide + Stokes) | 1/12° / 1 h | about 9 d | Low: already rejected for resolution (decision 13) |
| Med physics `mld`, `sal`, 3D and daily datasets; Med BGC; Global physics and waves | mixed-layer depth, salinity, 3D fields, biogeochemistry; coarser copies of the Med fields | | | Low: not navigation fields or a duplicate |

The Med wave model has no wind variable. There is no Adriatic-specific regional product: BLKSEA, IBI, BALTIC, ARCTIC and NWSHELF do not cover the Adriatic, and the "ADRIA" hits are indicators and ocean colour. Wave steepness is not provided; it would have to be derived from `VHM0` and a period.

## Copernicus Marine observations

| Product | Measures | Grid / step | Use for sailing |
|---|---|---|---|
| `WIND_GLO_PHY_L4_NRT_012_004` | gridded wind u/v from scatterometer blended with a model | 0.125° / 1 h | Medium: an "observed wind" check of ALADIN; partly a model, coarse and poor at the coast |
| `WIND_GLO_PHY_L3_NRT_012_002`, `WIND_MED_PHY_HR_L3_NRT_012_104` (Sentinel-1 SAR) | wind along satellite swaths | 0.125-0.25° or about 1 km, a few passes a day | Low as a layer (gappy), useful for one-off checks such as bora and island lee |
| `SST_MED_SST_L4_NRT_OBSERVATIONS_010_004` | gap-free analysed SST | 1/16° / daily | Medium: a check of the forecast SST |
| `SST_MED_PHY_SUBSKIN_L4_NRT_010_036` | hourly subskin SST | 1/16° / 1 h | Low: the daily product is enough |
| `INSITU_MED_PHYBGCWAV_DISCRETE_MYNRT_013_035` | buoys, tide gauges, other platforms | points, irregular; 24-48 h delay on average | Medium for validation only; the list of platforms in the box needs a login *(not verified)* |
| `WAVE_GLO_PHY_SWH_L3_NRT_014_001`, `..._L4_NRT_014_003` | altimeter wave height along tracks; merged at 0.5° and 2° | | Low: thin tracks, mostly near land; L4 is too coarse |
| `MULTIOBS_GLO_PHY_MYNRT_015_003`, `SEALEVEL_EUR_PHY_L4_NRT_008_060` | combined and geostrophic surface currents | 0.25° and 1/16°, hourly or daily | Low: they do not resolve the Adriatic; no tide |
| `OCEANCOLOUR_MED_BGC_L3_NRT_009_141` | chlorophyll, water clarity | 300 m-1 km / daily | Low: not navigation |

## Other Copernicus services

| Service / product | Offers | Use for sailing |
|---|---|---|
| CAMS European air quality forecasts (Atmosphere Data Store) | dust and particulates at about 0.1°, 0-96 h | Medium: Saharan dust and haze. Needs a free account and the licence accepted once. The rest is air quality |
| CAMS global composition forecasts | dust aerosol optical depth, UV index, at 0.4°, 5 d | Medium: haze and sun-exposure overlay; only about 11 x 8 cells in the box |
| C3S Climate Data Store: ERA5, ERA5 waves | hourly reanalysis since 1940 at 0.25° (waves about 0.5°) | Medium for **season and passage planning only** (wind roses, gale frequency); not a forecast |
| CEMS: EFFIS fire danger, EFAS / GloFAS floods, rapid mapping | fire weather index, river discharge, disaster maps | Low |
| CLMS (land), Sentinel-3 via the Copernicus Data Space | land cover and coastline; SST and altimetry | Low: nothing beyond the Marine products |

**Copernicus offers no fog, visibility, thunderstorm or lightning forecast.** CAMS has only dust and aerosol proxies. Those fields would have to come from ALADIN or national services.
