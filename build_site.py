#!/usr/bin/env python3
"""Assemble the GitHub Pages site from this run's results and the previously published files.

For each asset (wind, marine) the new file is used when its job succeeded; otherwise the previously
published file is kept and the page shows a warning. Also writes status.json, index.html and README.md.

Usage: build_site.py --wind-ts YYYYMMDDHH --marine-ts YYYYMMDD00 --wind-result R --marine-result R --prev DIR --wind DIR --marine DIR --out DIR
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone

import region

ATTRIBUTION = ("Generated using E.U. Copernicus Marine Service Information; "
               "https://doi.org/10.48670/mds-00359 (currents), https://doi.org/10.48670/mds-00373 (waves).")

ASSETS = {
    "wind": {
        "title": "Wind (ALADIN)",
        "label": "ALADIN run",
        "main": "aladin_adriacenter_{run}.grb",
        "latest": "aladin_adriacenter_latest.grb",
        "extra": "aladin_wind_{run}.png",
        "extra_latest": "aladin_wind_latest.png",
        "pattern": re.compile(r"^aladin_adriacenter_(\d{10})\.grb$"),
    },
    "marine": {
        "title": "Water (Copernicus)",
        "label": "reference time",
        "main": "copernicus_adriacenter_{run}.grb",
        "latest": "copernicus_adriacenter_latest.grb",
        "extra": None,
        "extra_latest": None,
        "pattern": re.compile(r"^copernicus_adriacenter_(\d{10})\.grb$"),
    },
}
DERIVED_FILES = {"index.html", "README.md", "status.json", ".nojekyll"}


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fmt_run(run):
    if not run:
        return "an unknown run"
    return f"{run[0:4]}-{run[4:6]}-{run[6:8]} {run[8:10]} UTC"


def fmt_utc(iso):
    return f"{iso[0:10]} {iso[11:16]} UTC" if iso else "unknown time"


def previous_state(prev_dir, name):
    """The published state of one asset in prev_dir, or None when no file of it is published."""
    if not prev_dir or not os.path.isdir(prev_dir):
        return None
    runs = sorted(m.group(1) for f in os.listdir(prev_dir) if (m := ASSETS[name]["pattern"].match(f)))
    status = read_json(os.path.join(prev_dir, "status.json")) or {}
    entry = (status.get("assets") or {}).get(name)
    if entry and entry.get("run") in runs:
        return dict(entry)
    if entry and entry.get("state") == "missing" and not runs:
        return dict(entry)  # keeps failed_since, so a repeated failure does not change the site
    if runs:
        return {"state": "ok", "run": runs[-1], "published_utc": None, "failed_for": None, "failed_since_utc": None}
    return None


def new_asset(spec, artifact_dir, ts):
    """The new files of one asset from its artifact directory, or None when there is no usable file."""
    if not artifact_dir or not os.path.isdir(artifact_dir):
        return None
    main = os.path.join(artifact_dir, spec["main"].format(run=ts))
    if not os.path.isfile(main) or os.path.getsize(main) == 0:
        return None
    new = {"run": ts, "main": main, "extra": None}
    if spec["extra"]:
        extra = os.path.join(artifact_dir, spec["extra"].format(run=ts))
        if os.path.isfile(extra) and os.path.getsize(extra) > 0:
            new["extra"] = extra
    meta = read_json(os.path.join(artifact_dir, "marine_meta.json")) or {}
    new["meta"] = meta
    return new


def decide(result, new, prev, ts, now):
    """The state machine for one asset. Returns (outcome, state) with outcome in
    new / guarded / kept / failed."""
    if result == "success" and new is not None:
        if prev and prev.get("run") and new["run"] < prev["run"]:
            return "guarded", dict(prev)  # never go back to an older ALADIN run
        state = {"state": "ok", "run": new["run"], "published_utc": now, "failed_for": None, "failed_since_utc": None}
        meta = new.get("meta", {})
        if meta.get("data_updated_utc"):
            state["data_updated_utc"] = meta["data_updated_utc"]
        if meta.get("model_systems"):
            state["model_systems"] = meta["model_systems"]
        return "new", state
    if result == "skipped" and prev and prev.get("run"):
        return "kept", dict(prev)
    if prev and prev.get("run"):
        since = prev.get("failed_since_utc") if prev.get("state") == "stale" else None
        state = dict(prev)
        state.update(state="stale", failed_for=ts, failed_since_utc=since or now)
        return "failed", state
    since = prev.get("failed_since_utc") if prev and prev.get("state") == "missing" else None
    return "failed", {"state": "missing", "run": None, "published_utc": None,
                      "failed_for": ts, "failed_since_utc": since or now}


def copy_asset(spec, run, source_dir, out_dir, extra_path=None):
    """Copy the files of one run into the site, plus the *_latest copies. Returns the file names written."""
    written = []
    main = os.path.join(source_dir, spec["main"].format(run=run))
    shutil.copyfile(main, os.path.join(out_dir, spec["main"].format(run=run)))
    shutil.copyfile(main, os.path.join(out_dir, spec["latest"]))
    written += [spec["main"].format(run=run), spec["latest"]]
    if spec["extra"]:
        extra = extra_path or os.path.join(source_dir, spec["extra"].format(run=run))
        if os.path.isfile(extra):
            shutil.copyfile(extra, os.path.join(out_dir, spec["extra"].format(run=run)))
            shutil.copyfile(extra, os.path.join(out_dir, spec["extra_latest"]))
            written += [spec["extra"].format(run=run), spec["extra_latest"]]
    return written


def model_text(entry):
    systems = entry.get("model_systems") or {}
    parts = [f"{systems[k]} ({k})" for k in ("currents", "waves") if systems.get(k)]
    return ", model " + " / ".join(parts) if parts else ""


def status_line(spec, entry, name):
    title = spec["title"]
    if entry["state"] == "missing":
        return f"{title}: not available yet"
    what = f"run {fmt_run(entry['run'])}" if name == "wind" else f"reference time {fmt_run(entry['run'])}"
    if entry["state"] == "stale":
        return f"{title}: {what}, STALE since {fmt_utc(entry['failed_since_utc'])}{model_text(entry)}"
    text = f"{title}: {what}, OK"
    if entry.get("published_utc"):
        text += f", published {fmt_utc(entry['published_utc'])}"
    if name == "marine" and entry.get("data_updated_utc"):
        text += f", Copernicus data updated {fmt_utc(entry['data_updated_utc'])}"
    return text + model_text(entry)


def failed_update(spec, entry):
    """Names what failed. A water update can fail for the reference time that is already shown (a second update
    on the same day), and its checker may have given no time at all, so it is not named by time."""
    if spec["label"] == "ALADIN run" and entry.get("failed_for"):
        return f"The update to ALADIN run {fmt_run(entry['failed_for'])}"
    return "The latest update" if spec["label"] == "ALADIN run" else "The latest Copernicus update"


def warnings(status):
    out = []
    for name, spec in ASSETS.items():
        entry = status["assets"][name]
        if entry["state"] == "stale":
            out.append(f"{failed_update(spec, entry)} failed for {spec['title']}. "
                       f"Showing {spec['label']} {fmt_run(entry['run'])} (stale since {fmt_utc(entry['failed_since_utc'])}).")
        elif entry["state"] == "missing":
            out.append(f"{spec['title']} is not available: {failed_update(spec, entry).lower()} failed and there is no earlier file.")
    wind, marine = status["assets"]["wind"].get("run"), status["assets"]["marine"].get("run")
    if wind and marine and run_end(marine, region.MARINE_HOURS) < run_end(wind, region.FORECAST_HOURS):
        out.append(f"The water file (to {fmt_run(run_end(marine, region.MARINE_HOURS).strftime('%Y%m%d%H'))}) ends "
                   f"before the wind file (to {fmt_run(run_end(wind, region.FORECAST_HOURS).strftime('%Y%m%d%H'))}).")
    return out


def run_end(run, hours):
    return datetime.strptime(run, "%Y%m%d%H") + timedelta(hours=hours)


def human_size(path):
    return f"{os.path.getsize(path) / 1e6:.1f} MB"


def render_index(status, out_dir, files):
    lines = ['<!DOCTYPE html>', '<html lang="en">',
             '<head><meta charset="utf-8"><title>ALADIN GRIB Files</title></head>', '<body>',
             '<h1>ALADIN Adria GRIB Files</h1>']
    for w in warnings(status):
        lines.append('<p style="border:2px solid #b00;background:#fee;padding:0.6em">'
                     f'<strong>Warning:</strong> {html.escape(w)}</p>')
    lines.append('<h2>Data status</h2><ul>')
    for name, spec in ASSETS.items():
        lines.append(f'<li>{html.escape(status_line(spec, status["assets"][name], name))}</li>')
    lines.append('</ul><h2>Files</h2><ul>')
    for f in files:
        if f.endswith(".grb"):
            lines.append(f'<li><a href="{html.escape(f)}">{html.escape(f)}</a> ({human_size(os.path.join(out_dir, f))})</li>')
    lines.append('</ul>')
    lines.append(f'<p>Updated: {html.escape(fmt_utc(status["updated_utc"]))}</p>')
    lines.append(f'<p><small>{html.escape(ATTRIBUTION)}</small></p>')
    lines += ['</body>', '</html>']
    return "\n".join(lines) + "\n"


def render_readme(status, files):
    out = ["# ALADIN Adria GRIB Files", "",
           "This branch (`gh-pages`) is automatically generated and contains processed GRIB files from the "
           "ALADIN weather model (wind, pressure, temperature) and from Copernicus Marine (surface currents, waves).",
           "", "## Data status", ""]
    for name, spec in ASSETS.items():
        out.append(f"- {status_line(spec, status['assets'][name], name)}")
    out.append("")
    for w in warnings(status):
        out += [f"> **Warning:** {w}", ""]
    run = status["assets"]["wind"].get("run")
    png = ASSETS["wind"]["extra"].format(run=run) if run else None
    if png in files:
        out += [f"![Latest ALADIN wind forecast]({png})", ""]
    out += [
        "## About This Data", "",
        "- **Wind source**: Czech Hydrometeorological Institute (CHMI) - ALADIN model, Lambert 2.3km grid",
        "- **Water source**: Copernicus Marine, Mediterranean Sea Physics and Waves Analysis and Forecast, 1/24° grid",
        f"- **Region**: Adriatic Sea ({region.LON_MIN}-{region.LON_MAX}°E, {region.LAT_MIN}-{region.LAT_MAX}°N)",
        f"- **Time frame**: wind: one ALADIN run, hourly steps 0-{region.FORECAST_HOURS}; "
        f"water: from 00 UTC of the day of the latest Copernicus update, hourly steps 0-{region.MARINE_HOURS}, "
        "so it always extends past the wind forecast",
        f"- **Wind resolution**: {region.DX}° (~2.2 km) regular lat-lon grid",
        "- **Water resolution**: native 1/24° (~4 km) points, not regridded",
        "- **Update frequency**: wind every 6 hours (CHMI), water up to three times a day (Copernicus); each file is rebuilt when its data is new",
        "- **Wind file variables**:",
        "  - Mean Sea Level Pressure (MSLP)",
        "  - Wind Speed and Direction at 10m",
        "  - Wind Gusts (u/v components)",
        "  - Temperature at 2m",
        "- **Water file variables**:",
        "  - Surface current (ocean and tide), u/v components",
        "  - Wave height, direction and period",
        "  - Wind-sea and primary swell height, direction and period", "",
        "## Usage", "", "Download files here or get the latest run directly:", "```bash",
        "wget https://k-schreiber.github.io/aladin-grib-adria/aladin_adriacenter_latest.grb",
        "wget https://k-schreiber.github.io/aladin-grib-adria/copernicus_adriacenter_latest.grb",
        "```", "", ATTRIBUTION, ""]
    return "\n".join(out)


def data_hashes(root):
    if not root or not os.path.isdir(root):
        return None
    return {f: sha256(os.path.join(root, f)) for f in sorted(os.listdir(root))
            if f not in DERIVED_FILES and os.path.isfile(os.path.join(root, f))}


def comparable(status):
    return None if status is None else {k: v for k, v in status.items() if k != "updated_utc"}


def build(tss, results, dirs, prev_dir, out_dir, now):
    """Build the site in out_dir. Returns (status, outcomes, changed)."""
    os.makedirs(out_dir, exist_ok=True)
    status = {"schema": 1, "updated_utc": now, "assets": {}}
    outcomes, files = {}, []
    for name, spec in ASSETS.items():
        prev = previous_state(prev_dir, name)
        ts = tss.get(name) or None
        new = new_asset(spec, dirs.get(name), ts) if ts else None
        outcome, state = decide(results[name], new, prev, ts, now)
        outcomes[name], status["assets"][name] = outcome, state
        if outcome == "new":
            files += copy_asset(spec, new["run"], dirs[name], out_dir, new["extra"])
        elif state.get("run"):
            files += copy_asset(spec, state["run"], prev_dir, out_dir)
    with open(os.path.join(out_dir, "status.json"), "w") as f:
        json.dump(status, f, indent=1)
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(render_index(status, out_dir, files))
    with open(os.path.join(out_dir, "README.md"), "w") as f:
        f.write(render_readme(status, files))

    prev_status = read_json(os.path.join(prev_dir, "status.json")) if prev_dir else None
    changed = (data_hashes(prev_dir) != data_hashes(out_dir)) or (comparable(prev_status) != comparable(status))
    return status, outcomes, changed


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wind-ts", default="", help="ALADIN run of this attempt, YYYYMMDDHH (empty: none)")
    p.add_argument("--marine-ts", default="", help="water reference time of this attempt, YYYYMMDDHH (empty: none)")
    for name in ASSETS:
        p.add_argument(f"--{name}-result", required=True, choices=["success", "failure", "skipped", "cancelled"])
        p.add_argument(f"--{name}", dest=f"{name}_dir", default=None)
    p.add_argument("--prev", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--now", default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    args = p.parse_args(argv)
    for opt in (args.wind_ts, args.marine_ts):
        if opt and not re.fullmatch(r"\d{10}", opt):
            p.error("--wind-ts / --marine-ts must be YYYYMMDDHH")
    if args.prev and not os.path.isdir(args.prev):
        # Omit --prev only when nothing is published yet. A missing directory here would turn every
        # failed asset into "missing" and the deploy would remove its published file.
        p.error(f"--prev {args.prev} is not a directory")

    results = {"wind": args.wind_result, "marine": args.marine_result}
    dirs = {"wind": args.wind_dir, "marine": args.marine_dir}
    tss = {"wind": args.wind_ts, "marine": args.marine_ts}
    status, outcomes, changed = build(tss, results, dirs, args.prev, args.out, args.now)

    lines = [f"### Site: wind {fmt_run(args.wind_ts)}, water {fmt_run(args.marine_ts)}", ""]
    for name, spec in ASSETS.items():
        lines.append(f"- {status_line(spec, status['assets'][name], name)} (job: {results[name]}, outcome: {outcomes[name]})")
    for w in warnings(status):
        lines.append(f"- WARNING: {w}")
    meta = read_json(os.path.join(dirs["marine"], "marine_meta.json")) if dirs["marine"] else None
    if meta and meta.get("model_systems"):
        lines.append(f"- Copernicus model systems used: {meta['model_systems']} (dataset versions {meta.get('versions_in_use')})")
    if meta and meta.get("retires_utc"):
        lines.append(f"- WARNING: Copernicus dataset versions scheduled for retirement: {meta['retires_utc']}")
    lines.append(f"- {'content changed: deploy' if changed else 'nothing changed: no deploy'}")
    summary = "\n".join(lines) + "\n"
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")
            for name in ASSETS:
                f.write(f"save_{name}_marker={'true' if outcomes[name] in ('new', 'guarded') else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
