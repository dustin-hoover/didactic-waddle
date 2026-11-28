#!/usr/bin/env bash
# setup_and_run.sh — reproducible pipeline for the Boat Dock Network
# premises-passed analysis. Stands up PostGIS, loads the DockOS schema, pulls the
# Beaver Lake shoreline (USGS NHD) and NW Arkansas parcels (AR GIS Office statewide
# CAMA centroids, covering Benton/Washington/Carroll/Madison), and computes premises
# passed within shoreline buffers.
#
# Tested on Ubuntu 24.04 with PostgreSQL 16. Run from repo root:
#   bash boat-dock-network/software/gis/setup_and_run.sh
#
# Idempotent-ish: safe to re-run; it overwrites staging tables.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
SCHEMA="$REPO/boat-dock-network/software/db/schema.sql"
OUT="$REPO/boat-dock-network/data/gis/outputs"
WORK="${WORK:-/tmp/bdn-gis}"; mkdir -p "$WORK" "$OUT"

PGDB=${PGDB:-dockos}; PGUSER=${PGUSER:-dockos}; PGPW=${PGPW:-dockos}
export PGPASSWORD="$PGPW"
CONN="postgresql://$PGUSER:$PGPW@localhost:5432/$PGDB"
OGRCONN="PG:host=localhost user=$PGUSER dbname=$PGDB password=$PGPW"

echo "== 1. Dependencies (PostGIS + GDAL) =="
if ! psql --version >/dev/null 2>&1; then sudo apt-get update -qq && sudo apt-get install -y -qq postgresql-16; fi
sudo apt-get install -y -qq postgresql-16-postgis-3 gdal-bin >/dev/null 2>&1 || true
sudo pg_ctlcluster 16 main start 2>/dev/null || true; sleep 2

echo "== 2. Database + PostGIS + schema =="
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$PGUSER'" | grep -q 1 || \
  sudo -u postgres psql -q -c "CREATE ROLE $PGUSER LOGIN PASSWORD '$PGPW' SUPERUSER;"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$PGDB'" | grep -q 1 || \
  sudo -u postgres psql -q -c "CREATE DATABASE $PGDB OWNER $PGUSER;"
psql "$CONN" -q -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql "$CONN" -q -f "$SCHEMA"

echo "== 3. Beaver Lake shoreline (USGS NHD large-scale waterbody) =="
BBOX="-94.15,35.95,-93.55,36.65"
curl -s --max-time 90 -G \
  "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/12/query" \
  --data-urlencode "where=GNIS_NAME='Beaver Lake'" \
  --data-urlencode "geometry=$BBOX" --data-urlencode "geometryType=esriGeometryEnvelope" \
  --data-urlencode "inSR=4326" --data-urlencode "outSR=4326" \
  --data-urlencode "spatialRel=esriSpatialRelIntersects" \
  --data-urlencode "outFields=GNIS_NAME,AREASQKM,FTYPE" \
  --data-urlencode "returnGeometry=true" --data-urlencode "f=geojson" \
  -o "$WORK/beaver_lake.geojson"
ogr2ogr -f PostgreSQL "$OGRCONN" "$WORK/beaver_lake.geojson" \
  -nln beaver_lake -nlt MULTIPOLYGON -lco GEOMETRY_NAME=geom -t_srs EPSG:4326 -overwrite

echo "== 4. Shoreline buffers (0.25 / 0.5 / 1 mi) =="
psql "$CONN" -q <<'SQL'
DROP TABLE IF EXISTS lake_buffers;
CREATE TABLE lake_buffers (buffer_m int PRIMARY KEY, label text, geom geometry(MultiPolygon,4326));
INSERT INTO lake_buffers
SELECT b.m,b.lbl, ST_Multi(ST_Transform(ST_Buffer(ST_Transform(ST_Union(l.geom),26915),b.m),4326))
FROM beaver_lake l,(VALUES (402,'0.25mi'),(805,'0.5mi'),(1609,'1mi')) b(m,lbl) GROUP BY b.m,b.lbl;
CREATE INDEX ON lake_buffers USING gist(geom);
DROP TABLE IF EXISTS query_envelope;
CREATE TABLE query_envelope AS SELECT ST_SimplifyPreserveTopology(geom,0.0008) geom FROM lake_buffers WHERE buffer_m=1609;
SQL
psql "$CONN" -tAc "SELECT ST_AsGeoJSON(geom) FROM query_envelope;" > "$WORK/buffer_1mi.geojson"

echo "== 5. Pull parcels within 1 mi (AR GIS Office statewide CAMA centroids) =="
python3 "$HERE/arcgis_loader.py" \
  --url "https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/FeatureServer/0" \
  --out "$WORK/ar_parcel_centroids.geojson" \
  --fields "parcelid,ownername,county,countyfips,parceltype,impvalue,landvalue,totalvalue,adrcity,adrzip5" \
  --filter-geojson "$WORK/buffer_1mi.geojson" --batch 150
ogr2ogr -f PostgreSQL "$OGRCONN" "$WORK/ar_parcel_centroids.geojson" \
  -nln stg_parcel_centroid -nlt POINT -lco GEOMETRY_NAME=geom -t_srs EPSG:4326 -overwrite

echo "== 6. Classify + compute premises passed =="
psql "$CONN" -q <<'SQL'
ALTER TABLE stg_parcel_centroid ADD COLUMN IF NOT EXISTS dist_band text;
UPDATE stg_parcel_centroid p SET dist_band =
  CASE WHEN ST_Intersects(p.geom,(SELECT geom FROM lake_buffers WHERE buffer_m=402)) THEN '0-0.25mi'
       WHEN ST_Intersects(p.geom,(SELECT geom FROM lake_buffers WHERE buffer_m=805)) THEN '0.25-0.5mi'
       WHEN ST_Intersects(p.geom,(SELECT geom FROM lake_buffers WHERE buffer_m=1609)) THEN '0.5-1mi'
       ELSE 'outside' END;
SQL

echo "== 7. Export outputs =="
psql "$CONN" --csv -c "SELECT county,
  count(*) FILTER (WHERE impvalue>0 AND dist_band='0-0.25mi') prem_0_025mi,
  count(*) FILTER (WHERE impvalue>0 AND dist_band='0.25-0.5mi') prem_025_05mi,
  count(*) FILTER (WHERE impvalue>0 AND dist_band='0.5-1mi') prem_05_1mi,
  count(*) FILTER (WHERE impvalue>0 AND dist_band<>'outside') premises_1mi_total,
  count(*) FILTER (WHERE (impvalue=0 OR impvalue IS NULL) AND dist_band<>'outside') vacant_parcels_1mi
  FROM stg_parcel_centroid WHERE dist_band<>'outside' GROUP BY county ORDER BY premises_1mi_total DESC;" \
  > "$OUT/premises_passed_by_county.csv"
psql "$CONN" --csv -c "SELECT parcelid,ownername,county,parceltype,impvalue,totalvalue,dist_band,
  round(ST_Y(geom)::numeric,6) lat, round(ST_X(geom)::numeric,6) lon
  FROM stg_parcel_centroid WHERE dist_band<>'outside' AND impvalue>0 ORDER BY county,totalvalue DESC;" \
  > "$OUT/premises_points.csv"
python3 "$HERE/make_map_svg.py" "$WORK/beaver_lake.geojson" "$OUT/premises_points.csv" "$OUT/beaver_lake_premises_map.svg"
echo "== DONE. See $OUT =="
