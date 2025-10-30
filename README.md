# ALADIN Adria GRIB Files

This branch (`gh-pages`) is automatically generated and contains processed GRIB files from the ALADIN weather model.

## About This Data

- **Source**: Czech Hydrometeorological Institute (CHMI) - ALADIN model
- **Model**: ALADIN Lambert 2.3km grid
- **Region**: Adriatic Sea (13.0-17.5°E, 42.5-44.5°N)
- **Resolution**: 0.02° (~2.2 km) regular lat-lon grid
- **Update frequency**: Roughly every 6 hours by CHMI, processed here within 1 hour
- **Variables included**:
  - Mean Sea Level Pressure (MSLP)
  - Wind Speed and Direction at 10m
  - Wind Gusts (u/v components)
  - Temperature at 2m

## Latest Update

**Last processed**: 2025-10-30 08:45:04 UTC


## How This Works

This repository uses GitHub Actions to:

1. **Download** the latest ALADIN model data from CHMI every hour
2. **Process** the GRIB files using CDO (Climate Data Operators):
   - Reproject from Lambert conformal to regular lat-lon grid
   - Subset to Adriatic region bounding box
   - Merge multiple variables into single file
3. **Publish** to this `gh-pages` branch for public access

### Data Source

Original data: [CHMI Open Data Portal](https://opendata.chmi.cz/meteorology/weather/nwp_aladin/Lambert_2.3km/)

## Usage

Download files directly:
```bash
# Latest file
wget https://k-schreiber.github.io/aladin-grib-adria/aladin_adriacenter_latest.grb2
```
