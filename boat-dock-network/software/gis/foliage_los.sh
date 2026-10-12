#!/usr/bin/env bash
# foliage_los.sh — canopy-aware line-of-sight refinement.
# Builds a DSM (bare-earth DEM + NLCD-canopy height), re-runs the candidate viewsheds
# through foliage, and marks premises.los_dsm. Run AFTER setup_and_run.sh +
# node_siting_and_map.sh (needs dockos DB + dem.tif in $WORK).
# Requires: gdal-bin, python3 + rasterio (pip install rasterio).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PGDB=${PGDB:-dockos}; PGUSER=${PGUSER:-dockos}; PGPW=${PGPW:-dockos}
export PGPASSWORD="$PGPW"; CONN="postgresql://$PGUSER:$PGPW@localhost:5432/$PGDB"
WORK="${WORK:-/tmp/bdn-gis}"; cd "$WORK"; mkdir -p vs

echo "== 1. NLCD 2021 land cover, aligned to dem.tif =="
read XMIN YMIN XMAX YMAX < <(gdalinfo -json dem.tif | python3 -c "import json,sys;d=json.load(sys.stdin);c=d['cornerCoordinates'];print(c['lowerLeft'][0],c['lowerLeft'][1],c['upperRight'][0],c['upperRight'][1])")
read W H < <(gdalinfo -json dem.tif | python3 -c "import json,sys;d=json.load(sys.stdin);print(*d['size'])")
curl -s --max-time 120 -G "https://www.mrlc.gov/geoserver/mrlc_display/wcs" \
  --data-urlencode service=WCS --data-urlencode version=1.0.0 --data-urlencode request=GetCoverage \
  --data-urlencode "coverage=mrlc_display:NLCD_2021_Land_Cover_L48" --data-urlencode crs=EPSG:4326 \
  --data-urlencode "bbox=$XMIN,$YMIN,$XMAX,$YMAX" --data-urlencode "width=$W" --data-urlencode "height=$H" \
  --data-urlencode format=GeoTIFF -o lc.tif

echo "== 2. Build DSM (DEM + canopy height) and warp to UTM =="
python3 "$HERE/build_dsm.py" dem.tif lc.tif dsm.tif
gdalwarp -q -overwrite -t_srs EPSG:26915 -tr 30 30 -r bilinear dsm.tif dsm_utm.tif

echo "== 3. Foliage viewsheds (mast 15 m clears canopy; target 2 m above canopy) =="
psql "$CONN" --csv -t -c "SELECT parcelid, ST_X(ST_Transform(geom,26915)), ST_Y(ST_Transform(geom,26915)) FROM premises" > prem_utm.csv
awk -F, '{print $2, $3}' prem_utm.csv > prem_xy.txt; awk -F, '{print $1}' prem_utm.csv > prem_ids.txt
psql "$CONN" --csv -t -c "SELECT zone_id,parcelid,round(elev::numeric,0),x,y FROM candidates ORDER BY zone_id,elev DESC" > cand_list.csv
: > edges_dsm.csv
while IFS=, read ZONE PID ELEV X Y; do
  gdal_viewshed -q -md 8000 -oz 15 -tz 2 -ox "$X" -oy "$Y" dsm_utm.tif vs/d.tif 2>/dev/null
  gdallocationinfo -valonly -geoloc vs/d.tif < prem_xy.txt 2>/dev/null | paste -d, prem_ids.txt - \
    | awk -F, -v c="$PID" '$2==255{print c","$1}' >> edges_dsm.csv
done < cand_list.csv

echo "== 4. Mark premises.los_dsm =="
psql "$CONN" -q -c "DROP TABLE IF EXISTS vis_edges_dsm; CREATE TABLE vis_edges_dsm(cand text, prem text);"
psql "$CONN" -q -c "\copy vis_edges_dsm FROM 'edges_dsm.csv' WITH (FORMAT csv)"
psql "$CONN" -q -c "CREATE INDEX ON vis_edges_dsm(prem);"
psql "$CONN" -q -c "ALTER TABLE premises ADD COLUMN IF NOT EXISTS los_dsm boolean;
  UPDATE premises SET los_dsm=(parcelid IN (SELECT DISTINCT prem FROM vis_edges_dsm));"
psql "$CONN" -c "SELECT round(100.0*count(*) FILTER (WHERE los_dsm)/count(*)) foliage_los_pct,
  count(*) FILTER (WHERE NOT los_dsm) shadow FROM premises;"
echo "== DONE. Re-export premises.geojson (los=los_dsm) + regenerate map =="
