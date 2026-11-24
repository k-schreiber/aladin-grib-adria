#!/usr/bin/env python3
"""Checks whether Copernicus Marine has new data for the water GRIB, without credentials.

Reads the public STAC metadata of the newest released version of both datasets and prints
"<update key YYYYMMDDHHMM> <reference time YYYYMMDD00>" (exit 0), or exits 1 with a message on stderr.
The key is the latest update time of either dataset; the reference time is 00 UTC of that day.
"""
import sys
from datetime import datetime, timezone

import requests

BASE = "https://s3.waw3-1.cloudferro.com/mdl-metadata/metadata"
DATASETS = (
    ("MEDSEA_ANALYSISFORECAST_PHY_006_013", "cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m"),
    ("MEDSEA_ANALYSISFORECAST_WAV_006_017", "cmems_mod_med_wav_anfc_4.2km_PT1H-i"),
)


def parse(stamp):
    return datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def get(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def latest_update(product, dataset_id, now):
    """Update time of the newest dataset version that is already released."""
    links = [l["href"] for l in get(f"{BASE}/{product}/product.stac.json").get("links", [])
             if l.get("rel") in ("child", "item") and l.get("href", "").startswith(dataset_id + "_")]
    best = None
    for href in sorted(links, reverse=True):
        props = get(f"{BASE}/{product}/{href}").get("properties", {})
        released, updated = props.get("admp_released_date"), props.get("admp_updated_data")
        if updated and (not released or parse(released) <= now):
            best = best or parse(updated)  # versions sort newest first
    if best is None:
        raise ValueError(f"no released version of {dataset_id}")
    return best


def newest_update(now=None, fetch=latest_update):
    now = now or datetime.now(timezone.utc)
    updated = max(fetch(product, dataset, now) for product, dataset in DATASETS)
    return updated.strftime("%Y%m%d%H%M"), updated.strftime("%Y%m%d00")


def main():
    try:
        key, ref = newest_update()
    except Exception as e:
        print(f"Could not read the Copernicus metadata: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(key, ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
