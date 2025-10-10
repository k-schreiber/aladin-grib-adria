#!/usr/bin/env python3
import pygrib
import requests
import os
from bs4 import BeautifulSoup
import numpy as np
from eccodes import codes_grib_new_from_samples, codes_set_values, codes_write

# ---------------- CONFIG ----------------
BASE_URL = "https://opendata.chmi.cz/meteorology/weather/nwp_aladin/Lambert_2.3km/"
RUN_DIRS = ["00", "06", "12", "18"]
WORKDIR = "./Lambert_2.3km"
os.makedirs(WORKDIR, exist_ok=True)

LAT_MIN, LAT_MAX = 42.0, 44.467
LON_MIN, LON_MAX = 14.0, 18.0

VARS = {
    "MSLPRESSURE": "MSLP",
    "CLSWIND_DIREC": "WDIR10",
    "CLSWIND_SPEED": "WSPD10",
    "CLSTEMPERATURE": "T2m"
}

OUTPUT_GRIB = "Sailing_Adriatic_Lambert.grb"
# ----------------------------------------

def find_latest_run():
    latest_ts = ""
    latest_dir = ""
    latest_links = []

    for run in RUN_DIRS:
        url = f"{BASE_URL}{run}/"
        resp = requests.get(url)
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        links = [a.get("href") for a in soup.find_all("a") if a.get("href")]
        for l in links:
            if l.startswith("ALADLAMB4opendata_"):
                ts = l.split("_")[1]
                if ts > latest_ts:
                    latest_ts = ts
                    latest_dir = run
                    latest_links = links
    if not latest_ts:
        raise Exception("No Lambert 2.3km files found in any run directory")
    return latest_dir, latest_ts, latest_links

def download_file_with_progress(url, local_path):
    r = requests.get(url, stream=True)
    if r.status_code != 200:
        print(f"Failed to download {url}")
        return False
    total_size = int(r.headers.get('content-length', 0))
    total_mb = total_size / 1024 / 1024
    downloaded = 0
    print(f"Downloading {os.path.basename(local_path)} ({total_mb:.2f} MB)...")
    with open(local_path, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                percent = downloaded / total_size * 100 if total_size else 0
                print(f"\r{percent:.1f}% ({downloaded/1024/1024:.2f}/{total_mb:.2f} MB)", end="")
    print("\nDownload complete.")
    return True

def download_latest_files(latest_dir, timestamp, links):
    files_to_download = []
    for l in links:
        if timestamp in l:
            for var_code in VARS.keys():
                if var_code in l:
                    local_path = os.path.join(WORKDIR, l)
                    if not os.path.exists(local_path):
                        url = f"{BASE_URL}{latest_dir}/{l}"
                        download_file_with_progress(url, local_path)
                    # decompress if needed
                    if local_path.endswith(".bz2"):
                        os.system(f"bunzip2 -f {local_path}")
                        local_path = local_path[:-4]
                    files_to_download.append(local_path)
    return files_to_download

def verbose_grib_info(grib_file):
    grbs = pygrib.open(grib_file)
    print(f"\n--- GRIB File: {grib_file} ---")
    print(f"Number of messages: {grbs.messages}")
    names_seen = set()
    for grb in grbs:
        if grb.name not in names_seen:
            print(f"  Name: {grb.name}, ShortName: {grb.shortName}, Units: {grb.units}, LevelType: {grb.levelType}")
            names_seen.add(grb.name)
    grbs.close()

def crop_grb_to_box(grb):
    """Return a tuple of (subset_data, lats, lons) for the bounding box"""
    data, lats, lons = grb.data(lat1=LAT_MIN, lat2=LAT_MAX,
                                lon1=LON_MIN, lon2=LON_MAX)
    return data, lats, lons, grb

def merge_gribs(grib_files):
    """Merge GRIB messages into one file"""
    all_msgs = []

    for grib_file in grib_files:
        verbose_grib_info(grib_file)
        grbs = pygrib.open(grib_file)
        for grb in grbs:
            if grb.name in VARS.values():
                # Crop in memory
                data, lats, lons, grb_orig = crop_grb_to_box(grb)
                # Store original grb; pygrib preserves metadata
                all_msgs.append(grb_orig)
        grbs.close()

    # Write merged GRIB
    with open(OUTPUT_GRIB, "wb") as f:
        for grb in all_msgs:
            f.write(grb.tostring())
    print(f"\nDone. Merged GRIB saved as {OUTPUT_GRIB}")
    verbose_grib_info(OUTPUT_GRIB)

# ---------------- MAIN ----------------
if __name__ == "__main__":
    latest_dir, latest_ts, links = find_latest_run()
    print(f"Latest Lambert 2.3km run: {latest_ts} in directory {latest_dir}")
    # grib_files = download_latest_files(latest_dir, latest_ts, links)
    grib_files = [os.path.join(WORKDIR, f) for f in os.listdir(WORKDIR)
                  if any(var in f for var in VARS.keys()) and (f.endswith(".grb") or f.endswith(".grb.bz2"))]
    merge_gribs(grib_files)
