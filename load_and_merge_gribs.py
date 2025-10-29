#!/usr/bin/env python3
import os
import subprocess
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ---------------- CONFIG ----------------
BASE_URL = "https://opendata.chmi.cz/meteorology/weather/nwp_aladin/Lambert_2.3km/"
RUN_DIRS = ["00", "06", "12", "18"]
WORKDIR = "/tmp/aladin"
OUTDIR = os.getenv("OUTDIR", "/data")

# Bounding box for Adria region
LON_MIN = 13.0
LON_MAX = 17.5
LAT_MIN = 42.5
LAT_MAX = 44.5
DX = 0.02
DY = 0.02

# Variables to download
VARS = {
    "MSLPRESSURE": "MSLP",
    "CLSWIND_DIREC": "WDIR10",
    "CLSWIND_SPEED": "WSPD10",
    "CLSU_RAF_MOD_XFU": "URAF",
    "CLSV_RAF_MOD_XFU": "VRAF",
    "CLSTEMPERATURE": "T2m"
}


# ----------------------------------------

def create_target_grid():
    """Create CDO grid definition file"""
    grid_file = os.path.join(WORKDIR, "adriatic_grid.txt")
    nx = int((LON_MAX - LON_MIN) / DX) + 1
    ny = int((LAT_MAX - LAT_MIN) / DY) + 1

    with open(grid_file, "w") as f:
        f.write(f"gridtype = lonlat\n")
        f.write(f"xsize = {nx}\n")
        f.write(f"ysize = {ny}\n")
        f.write(f"xfirst = {LON_MIN}\n")
        f.write(f"xinc = {DX}\n")
        f.write(f"yfirst = {LAT_MIN}\n")
        f.write(f"yinc = {DY}\n")

    return grid_file


def find_latest_run():
    """Find the latest run across all run directories"""
    latest_ts = ""
    latest_dir = ""

    for run in RUN_DIRS:
        url = f"{BASE_URL}{run}/"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                continue
        except requests.RequestException as e:
            print(f"Failed to fetch {url}: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        links = [a.get("href") for a in soup.find_all("a") if a.get("href")]

        for link in links:
            if link.startswith("ALADLAMB4opendata_"):
                parts = link.split("_")
                if len(parts) >= 2:
                    ts = parts[1]
                    if ts > latest_ts:
                        latest_ts = ts
                        latest_dir = run

    if not latest_ts:
        raise Exception("No Lambert 2.3km files found in any run directory")

    return latest_dir, latest_ts


def download_file_with_progress(url, local_path):
    """Download a file with progress indication"""
    try:
        r = requests.get(url, stream=True, timeout=60)
        if r.status_code != 200:
            print(f"Failed to download {url} (status {r.status_code})")
            return False
    except requests.RequestException as e:
        print(f"Error downloading {url}: {e}")
        return False

    total_size = int(r.headers.get('content-length', 0))
    total_mb = total_size / 1024 / 1024
    downloaded = 0
    print(f"Downloading {os.path.basename(local_path)} ({total_mb:.2f} MB)...")

    with open(local_path, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                percent = downloaded / total_size * 100 if total_size else 0
                print(f"\r{percent:.1f}% ({downloaded / 1024 / 1024:.2f}/{total_mb:.2f} MB)", end="", flush=True)
    print("\nDownload complete.")
    return True


def download_latest_files(latest_dir, timestamp):
    """Download files for the latest timestamp"""
    run_url = f"{BASE_URL}{latest_dir}/"

    try:
        resp = requests.get(run_url, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"Failed to list files from {run_url}")
    except requests.RequestException as e:
        raise Exception(f"Error accessing {run_url}: {e}")

    soup = BeautifulSoup(resp.text, "html.parser")
    links = [a.get("href") for a in soup.find_all("a") if a.get("href")]

    downloaded_files = []

    for var_code in VARS.keys():
        # Find the first matching file for this variable
        matching_file = None
        for link in links:
            if f"ALADLAMB4opendata_{timestamp}_{var_code}" in link:
                matching_file = link
                break

        if matching_file:
            local_path = os.path.join(WORKDIR, matching_file)
            decompressed_path = local_path[:-4] if local_path.endswith(".bz2") else local_path

            # Check if decompressed file already exists
            if os.path.exists(decompressed_path):
                print(f"File already exists: {os.path.basename(decompressed_path)}")
                downloaded_files.append(decompressed_path)
                continue

            # Download if not exists
            if not os.path.exists(local_path):
                url = f"{run_url}{matching_file}"
                if not download_file_with_progress(url, local_path):
                    continue

            # Decompress if .bz2
            if local_path.endswith(".bz2"):
                if os.path.exists(local_path):
                    print(f"Decompressing {os.path.basename(local_path)}...")
                    subprocess.run(["bzip2", "-df", local_path], check=True)
                    local_path = decompressed_path

            if os.path.exists(local_path):
                downloaded_files.append(local_path)

    return downloaded_files


def merge_gribs(grib_files, timestamp):
    """
    Merge GRIB files: subset to bounding box, reproject to lat/lon grid, and merge using CDO.
    """
    if not grib_files:
        raise Exception("No GRIB files to process")

    # Create target grid
    grid_file = create_target_grid()

    # Create temporary directory for processed files
    tmp_processed = os.path.join(WORKDIR, f"run_{timestamp}", "processed")
    os.makedirs(tmp_processed, exist_ok=True)

    processed_files = []

    for grib_file in grib_files:
        base = os.path.basename(grib_file)
        processed_file = os.path.join(tmp_processed, f"{base}.processed.grb")

        print(f"Processing {base}...")

        # CDO: Remap to target grid and cut to bounding box in one command
        # Using -s flag to suppress CDO output for cleaner logs
        cmd = [
            "cdo", "-s",
            "sellonlatbox,{},{},{},{}".format(LON_MIN, LON_MAX, LAT_MIN, LAT_MAX),
            "-remapbil,{}".format(grid_file),
            grib_file,
            processed_file
        ]

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(processed_file) and os.path.getsize(processed_file) > 0:
                processed_files.append(processed_file)
                print(f"✓ Processed successfully")
            else:
                print(f"✗ Processing failed or resulted in empty file")
        except subprocess.CalledProcessError as e:
            print(f"✗ CDO error: {e.stderr}")
            # Try alternative method if first one fails
            print("  Trying alternative method (two-step process)...")
            try:
                temp_file = processed_file + ".temp"
                # Step 1: Remap
                subprocess.run(["cdo", "-s", "remapbil,{}".format(grid_file), grib_file, temp_file],
                               check=True, capture_output=True)
                # Step 2: Cut
                subprocess.run(["cdo", "-s", "sellonlatbox,{},{},{},{}".format(LON_MIN, LON_MAX, LAT_MIN, LAT_MAX),
                                temp_file, processed_file], check=True, capture_output=True)
                os.remove(temp_file)
                if os.path.exists(processed_file) and os.path.getsize(processed_file) > 0:
                    processed_files.append(processed_file)
                    print(f"✓ Processed successfully (alternative method)")
            except subprocess.CalledProcessError as e2:
                print(f"✗ Alternative method also failed: {e2.stderr}")
                continue

    if not processed_files:
        raise Exception("No files were successfully processed")

    # Merge all processed files using CDO
    outfile = os.path.join(OUTDIR, f"aladin_adriacenter_{timestamp}.grb")
    print(f"Merging {len(processed_files)} files into {outfile}...")

    # CDO merge command
    cmd_merge = ["cdo", "-s", "merge"] + processed_files + [outfile]

    try:
        subprocess.run(cmd_merge, check=True, capture_output=True)
        print(f"✓ Merged successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Merge failed: {e.stderr}")
        raise

    # Create symlink to latest
    latest_link = os.path.join(OUTDIR, "aladin_adriacenter_latest.grb")
    if os.path.exists(latest_link) or os.path.islink(latest_link):
        os.remove(latest_link)
    os.symlink(os.path.basename(outfile), latest_link)

    # Cleanup old run directories (keep last 3)
    cleanup_old_runs()

    return outfile


def cleanup_old_runs():
    """Remove old run directories, keeping only the 3 most recent"""
    run_dirs = []
    for item in os.listdir(WORKDIR):
        path = os.path.join(WORKDIR, item)
        if os.path.isdir(path) and item.startswith("run_"):
            run_dirs.append(path)

    run_dirs.sort(key=os.path.getmtime, reverse=True)

    for old_dir in run_dirs[3:]:
        print(f"Removing old run directory: {old_dir}")
        subprocess.run(["rm", "-rf", old_dir], check=True)


# ---------------- MAIN ----------------
if __name__ == "__main__":
    print(f"[{datetime.now()}] Starting GRIB processing with CDO...")

    # Create directories
    os.makedirs(WORKDIR, exist_ok=True)
    os.makedirs(OUTDIR, exist_ok=True)

    try:
        # Find latest run
        latest_dir, latest_ts = find_latest_run()
        print(f"Latest Lambert 2.3km run: {latest_ts} in directory {latest_dir}")

        # Download files
        grib_files = download_latest_files(latest_dir, latest_ts)
        print(f"Downloaded {len(grib_files)} GRIB files")

        # Process and merge
        outfile = merge_gribs(grib_files, latest_ts)
        print(f"Wrote {outfile}")
        print(f"[{datetime.now()}] GRIB processing completed successfully")

    except Exception as e:
        print(f"Error: {e}")
        exit(1)
