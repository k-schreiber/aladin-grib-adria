# aladin-grib-adria

Automated downloader, cutter, reprojection, and merger of CHMI Aladin 2.3km GRIB files for the central Adriatic.

## Deploy on Fly.io
Create GHCR_USERNAME and GHCR_TOKEN secrets in fly.io to authenticate for pulling NOAA docker images
GHCR_USERNAME: github username
GHCR_TOKEN: github PAT

```bash
fly launch --name aladin-grib-adria --no-deploy
fly volumes create data --size 5 --region fra
docker build -t aladin-grib-adria .
fly deploy --image aladin-grib-adria --app aladin-grib-adria
```

Then access:
https://aladin-grib-adria.fly.dev/aladin_adriacenter_latest.grb2
