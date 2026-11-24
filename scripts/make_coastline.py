#!/usr/bin/env python3
"""Regenerate adriatic_coastline.json: the Natural Earth 10m coastline clipped to the
processing region plus a margin, so the wind map needs no network access at render time.

Usage: python3 scripts/make_coastline.py [--source ne_10m_coastline.geojson]
Without --source the public-domain GeoJSON (about 10 MB) is downloaded.
"""
import argparse
import json
import os
import sys
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from region import LON_MIN, LON_MAX, LAT_MIN, LAT_MAX  # noqa: E402

URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_coastline.geojson"
MARGIN = 0.5  # degrees around the region, so lines reach past every map and grid edge
OUT = os.path.join(ROOT, "adriatic_coastline.json")


def clip(lines, west, east, south, north):
    """Keep the runs of consecutive points inside the box; split a line wherever it leaves it."""
    segments = []
    for coords in lines:
        run = []
        for lon, lat in coords:
            if west <= lon <= east and south <= lat <= north:
                run.append([round(lon, 4), round(lat, 4)])
            else:
                if len(run) >= 2:
                    segments.append(run)
                run = []
        if len(run) >= 2:
            segments.append(run)
    return segments


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="local GeoJSON instead of downloading")
    args = parser.parse_args()

    if args.source:
        with open(args.source) as f:
            data = json.load(f)
    else:
        with urllib.request.urlopen(URL, timeout=120) as resp:
            data = json.load(resp)

    lines = []
    for feature in data["features"]:
        geom = feature["geometry"]
        if geom["type"] == "LineString":
            lines.append(geom["coordinates"])
        elif geom["type"] == "MultiLineString":
            lines.extend(geom["coordinates"])

    box = (LON_MIN - MARGIN, LON_MAX + MARGIN, LAT_MIN - MARGIN, LAT_MAX + MARGIN)
    segments = clip(lines, *box)
    with open(OUT, "w") as f:
        json.dump(segments, f, separators=(",", ":"))
    points = sum(len(s) for s in segments)
    print(f"{len(segments)} segments, {points} points, box lon {box[0]}..{box[1]} lat {box[2]}..{box[3]} -> {OUT}")


if __name__ == "__main__":
    main()
