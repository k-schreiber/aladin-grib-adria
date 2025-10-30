# aladin-grib-adria

Automated downloader, cutter, reprojection, and merger of CHMI Aladin 2.3km GRIB files for the central Adriatic.


## Run locally

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Enter container shell
docker-compose exec aladin /bin/bash

# Stop
docker-compose down

# Rebuild after changes
docker-compose up -d --build
```

Access Once running:

Web interface: http://localhost:8080

Latest file: http://localhost:8080/aladin_adriacenter_latest.grb

Shell access:
```bash
docker exec -it aladin-grib /bin/bash (or docker-compose exec aladin /bin/bash)
```

## Deploy on Fly.io

```bash
fly launch --name aladin-grib-adria --no-deploy
fly volumes create data --size 5 --region fra
docker build -t aladin-grib-adria .
fly deploy --image aladin-grib-adria --app aladin-grib-adria
```
Then access:
https://aladin-grib-adria.fly.dev/aladin_adriacenter_latest.grb

## Run Via GitHub Actions

A workflow is set up to run every hour to download, process, and publish the latest data
to the `gh-pages` branch of this repository.

This requires no server setup and makes sure to process new published weather data
from CHMI automatically within one hour.

## About This Data
          
- **Source**: Czech Hydrometeorological Institute (CHMI) - ALADIN model
- **Model**: ALADIN Lambert 2.3km grid
- **Region**: Central Adriatic Sea (13.0-17.5°E, 42.5-44.5°N)
- **Resolution**: 0.02° (~2.2 km) regular lat-lon grid
- **Update frequency**: Roughly every 6 hours by CHMI, processed here within 1 hour
- **Variables included**:
  - Mean Sea Level Pressure (MSLP)
  - Wind Speed and Direction at 10m
  - Wind Gusts (u/v components)
  - Temperature at 2m

## How It Works

1. **Download** the latest ALADIN model data from CHMI every hour
2. **Process** the GRIB files using CDO:
   - Reproject from Lambert to regular lat-lon grid
   - Subset to Adriatic region bounding box
   - Merge multiple variables into single file
3. **Publish** to this `gh-pages` branch for public access
          

## Full Weather Parameter Descriptions
Project is based on CHMI weather data. Original data, parameter list and descriptions can be found at:
https://opendata.chmi.cz/meteorology/weather/nwp_aladin/

Parameters in **bold** are included in the merged output file.

| Parameter Name | Description | Units |
|----------------|-------------|-------|
| SURFGEOPOTENTIEL | Geopotential of model surface (orographic height) | [m^2/s^2] |
| SURFIND_TERREMER | Land-sea mask (land=1, sea=0) | [fraction] |
| **MSLPRESSURE** | Mean sea level pressure | [Pa] |
| SURFTEMPERATURE | Surface temperature | [K] |
| **CLSTEMPERATURE** | Temperature at 2m | [K] |
| CLSMAXI_TEMPERAT | Maximum temperature at 2m (in 6h at 18 UTC) | [K] |
| CLSMINI_TEMPERAT | Minimum temperature at 2m (in 6h at 18 UTC) | [K] |
| CLSDEW_P_TEMPER | Dew point temperature at 2m | [K] |
| CLSTPRIM_M | Wet bulb temperature at 2m | [K] |
| CLSUMI_RELATIVE | Relative humidity at 2m | [0-1] |
| **CLSWIND_SPEED** | Wind speed at 10m | [m/s] |
| **CLSWIND_DIREC** | Wind direction at 10m | [deg] |
| **CLSU_RAF_MOD_XFU** | Maximum wind gust in next 1h, u-component | [m/s] |
| **CLSV_RAF_MOD_XFU** | Maximum wind gust in next 1h, v-component | [m/s] |
| SURFNEBUL_BASSE | Low cloudiness | [fraction] |
| SURFNEBUL_MOYENN | Medium cloudiness | [fraction] |
| SURFNEBUL_HAUTE | High cloudiness | [fraction] |
| SURFNEBUL_TOTALE | Total cloudiness | [fraction] |
| CLS_VISICLD | Minimum horizontal visibility in clouds (ml/hy) | [m] |
| CLS_VISIERE | Minimum horizontal visibility in 1h, all weather | [m] |
| CLPVEIND_MOD_XFU | Ventilation index | [m^2/s] |
| SURFRF_SHORT_DO | Global solar radiation from ground (accumulated from start) | [J/m^2] |
| SURFRF_LONG_DO | Thermal radiation from ground (accumulated from start) | [J/m^2] |
| SURF_RAYT_DIR | Direct solar radiation to ground (accumulated from start) | [J/m^2] |
| SUNSHINE_DUR | Duration of sunshine (accumulated from start) | [s] |
| SURFRESERV_NEIGE | Water content of snow reservoir | [kg/m^2] |
| SURFRAINFALL | Stratiform rain (accumulated from start) | [kg/m^2] |
| SURFSNOWFALL | Stratiform snow (accumulated from start) | [kg/m^2] |
| SURFPREC_TOTAL | Total stratiform + convective precipitation (accumulated) | [kg/m^2] |
| PRECIP_TYPE | Most probable precipitation type in next 1h | [category index] |
| PRECIP_TYPEPRV | Most likely convective precipitation type in next 1h | [category index] |
| SURFCAPE_POS_F00 | CAPE energy diagnostically determined from current state | [J/kg] |
| SURFCIEN_POS_F00 | Convective inhibition energy (CIN) | [J/kg] |
| SURFOHTAG_FLASH | Thickness of hail layer (accumulated from start) | [m^2] |
| MAXSIM_REFLECTI | Maximum reflectivity in vertical column | [converted to mm/h] |