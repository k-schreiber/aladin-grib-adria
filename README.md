# aladin-grib-adria

Automated downloader, cutter, reprojection, and merger of CHMI Aladin 2.3km GRIB files for the central Adriatic.

## Deploy on Fly.io

```bash
fly launch --name aladin-grib-adria --no-deploy
fly volumes create data --size 5 --region fra
docker build -t aladin-grib-adria .
fly deploy --image aladin-grib-adria --app aladin-grib-adria
```

Then access:
https://aladin-grib-adria.fly.dev/aladin_adriacenter_latest.grb2
