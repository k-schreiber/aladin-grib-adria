#!/usr/bin/env bash
set -euxo pipefail

echo "[$(date)] Starting GRIB processing..."

BASE_URL="https://opendata.chmi.cz/meteorology/weather/nwp_aladin/Lambert_2.3km"
WORKDIR="/tmp/aladin"
OUTDIR="${OUTDIR:-/data}"
mkdir -p "$WORKDIR" "$OUTDIR"
cd "$WORKDIR"

LON_MIN=13.0
LON_MAX=17.5
LAT_MIN=42.5
LAT_MAX=44.5
DX=0.02
DY=0.02

VAR_PATTERNS=("CLSWIND_SPEED" "CLSWIND_DIREC" "CLSTPRIM_W" "CLSTEMPERATURE")

latest_ts=0
latest_run_folder=""
for run in 00 06 12 18; do
  url="$BASE_URL/$run/"
  listing=$(curl -sSf "$url" || true)
  while read -r ts; do
    if [[ -n "$ts" && "$ts" -gt "$latest_ts" ]]; then
      latest_ts="$ts"
      latest_run_folder="$run"
    fi
  done < <(echo "$listing" | grep -oP 'ALADLAMB4opendata_\K[0-9]{10}' || true)
done

if [[ -z "$latest_run_folder" ]]; then
  echo "No run folders found; exiting" >&2
  exit 1
fi

RUN_URL="$BASE_URL/$latest_run_folder"
RUN_DIR="$WORKDIR/run_$latest_ts"
rm -rf "$RUN_DIR"; mkdir -p "$RUN_DIR"; cd "$RUN_DIR"

for p in "${VAR_PATTERNS[@]}"; do
  fname=$(curl -sSf "$RUN_URL/" | grep -oP "ALADLAMB4opendata_${latest_ts}_${p}[^\"\s]*" | head -n1 || true)
  if [[ -n "$fname" ]]; then
    curl -sSf -O "$RUN_URL/$fname"
  fi
done

for f in *.bz2 2>/dev/null; do [ -f "$f" ] && bzip2 -dk "$f"; done

GRIB_FILES=( $(ls ALADLAMB4opendata_${latest_ts}_* 2>/dev/null || true) )
[[ ${#GRIB_FILES[@]} -eq 0 ]] && exit 2

TMP_SUBDIR="$RUN_DIR/subset"
TMP_REPROJ="$RUN_DIR/reproj"
mkdir -p "$TMP_SUBDIR" "$TMP_REPROJ"

nx=$(awk -v a=$LON_MIN -v b=$LON_MAX -v d=$DX 'BEGIN{print int((b-a)/d)+1}')
ny=$(awk -v a=$LAT_MIN -v b=$LAT_MAX -v d=$DY 'BEGIN{print int((b-a)/d)+1}')

reproj_files=()
for gf in "${GRIB_FILES[@]}"; do
  base=$(basename "$gf")
  sub="$TMP_SUBDIR/${base}.subset.grb2"
  wgrib2 "$gf" -small_grib "${LON_MIN}:${LON_MAX}" "${LAT_MIN}:${LAT_MAX}" "$sub"
  out="$TMP_REPROJ/${base}.latlon.grb2"
  wgrib2 "$sub" -new_grid latlon "${LON_MIN}:${DX}:${nx}" "${LAT_MIN}:${DY}:${ny}" -grib "$out"
  reproj_files+=("$out")
done

OUTFILE="$OUTDIR/aladin_adriacenter_${latest_ts}.grb2"
rm -f "$OUTFILE"
for f in "${reproj_files[@]}"; do cat "$f" >> "$OUTFILE"; done
ln -sf "$(basename "$OUTFILE")" "$OUTDIR/aladin_adriacenter_latest.grb2"

cd "$WORKDIR"; ls -1dt run_* | tail -n +4 | xargs -r rm -rf || true

echo "Wrote $OUTFILE"
echo "[$(date)] GRIB processing completed successfully"

