#!/usr/bin/env python3
import os
import subprocess
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ---------------- CONFIG ----------------
BASE_URL = "https://opendata.chmi.cz/meteorology/weather/nwp_aladin/Lambert_2.3km/"
RUN_DIRS = ["00", "06", "12", "18"]
WORKDIR = "./tmp/aladin"
OUTDIR = os.getenv("OUTDIR", "./data")

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
        for chunk in r.iter_content(1024*1024):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                percent = downloaded / total_size * 100 if total_size else 0
                print(f"\r{percent:.1f}% ({downloaded/1024/1024:.2f}/{total_mb:.2f} MB)", end="", flush=True)
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
            
            # Download if not exists
            if not os.path.exists(local_path) and not os.path.exists(local_path[:-4]):
                url = f"{run_url}{matching_file}"
                if not download_file_with_progress(url, local_path):
                    continue
            
            # Decompress if .bz2
            if local_path.endswith(".bz2"):
                if os.path.exists(local_path):
                    print(f"Decompressing {os.path.basename(local_path)}...")
                    subprocess.run(["bzip2", "-df", local_path], check=True)
                    local_path = local_path[:-4]
            
            if os.path.exists(local_path):
                downloaded_files.append(local_path)
    
    return downloaded_files

def merge_gribs(grib_files, timestamp):
    """
    Merge GRIB files: subset to bounding box, reproject to lat/lon grid, and merge.
    """
    if not grib_files:
        raise Exception("No GRIB files to process")
    
    # Create temporary directories
    tmp_subdir = os.path.join(WORKDIR, f"run_{timestamp}", "subset")
    tmp_reproj = os.path.join(WORKDIR, f"run_{timestamp}", "reproj")
    os.makedirs(tmp_subdir, exist_ok=True)
    os.makedirs(tmp_reproj, exist_ok=True)
    
    # Calculate grid dimensions
    nx = int((LON_MAX - LON_MIN) / DX) + 1
    ny = int((LAT_MAX - LAT_MIN) / DY) + 1
    
    reproj_files = []
    
    for grib_file in grib_files:
        base = os.path.basename(grib_file)
        subset_file = os.path.join(tmp_subdir, f"{base}.subset.grb2")
        reproj_file = os.path.join(tmp_reproj, f"{base}.latlon.grb2")
        
        print(f"Processing {base}...")
        
        # Step 1: Subset to bounding box
        cmd_subset = [
            "wgrib2", grib_file,
            "-small_grib", f"{LON_MIN}:{LON_MAX}", f"{LAT_MIN}:{LAT_MAX}",
            subset_file
        ]
        subprocess.run(cmd_subset, check=True, capture_output=True)
        
        # Step 2: Reproject to lat/lon grid
        cmd_reproj = [
            "wgrib2", subset_file,
            "-new_grid", "latlon",
            f"{LON_MIN}:{DX}:{nx}",
            f"{LAT_MIN}:{DY}:{ny}",
            "-grib", reproj_file
        ]
        subprocess.run(cmd_reproj, check=True, capture_output=True)
        
        reproj_files.append(reproj_file)
    
    # Merge all reprojected files
    outfile = os.path.join(OUTDIR, f"aladin_adriacenter_{timestamp}.grb2")
    print(f"Merging {len(reproj_files)} files into {outfile}...")
    
    with open(outfile, "wb") as out:
        for f in reproj_files:
            with open(f, "rb") as inp:
                out.write(inp.read())
    
    # Create symlink to latest
    latest_link = os.path.join(OUTDIR, "aladin_adriacenter_latest.grb2")
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
    print(f"[{datetime.now()}] Starting GRIB processing...")
    
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