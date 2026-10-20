#!/usr/bin/env bash
# node_siting_and_map.sh — zones, DEM viewshed node siting, greedy set-cover, outputs,
# and the interactive HTML map. Run AFTER setup_and_run.sh (needs the dockos DB with
# stg_parcel_centroid, beaver_lake, lake_buffers already loaded).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
OUT="$REPO/boat-dock-network/data/gis/outputs"; mkdir -p "$OUT"
WORK="${WORK:-/tmp/bdn-gis}"; mkdir -p "$WORK/vs"
PGDB=${PGDB:-dockos}; PGUSER=${PGUSER:-dockos}; PGPW=${PGPW:-dockos}
export PGPASSWORD="$PGPW"; CONN="postgresql://$PGUSER:$PGPW@localhost:5432/$PGDB"
OGRCONN="PG:host=localhost user=$PGUSER dbname=$PGDB password=$PGPW"
cd "$WORK"

echo "== 1. Cluster premises into 18 zones + hulls + GNIS names =="
python3 "$HERE/arcgis_loader.py" \
  --url "https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Location/FeatureServer/5" \
  --out gnis.geojson --fields "feature_name,feature_class,county_name" \
  --filter-geojson buffer_1mi.geojson --batch 300 || true
ogr2ogr -f PostgreSQL "$OGRCONN" gnis.geojson -nln stg_gnis -nlt PROMOTE_TO_MULTI \
  -lco GEOMETRY_NAME=geom -t_srs EPSG:4326 -overwrite
psql "$CONN" -q -f "$HERE/sql/zones.sql"

echo "== 2. DEM (3DEP ~30m) + warp to UTM =="
read XMIN YMIN XMAX YMAX < <(psql "$CONN" -tAc "SELECT ST_XMin(g),ST_YMin(g),ST_XMax(g),ST_YMax(g) FROM (SELECT ST_Extent(geom) g FROM lake_buffers WHERE buffer_m=1609) s;" | tr '|' ' ')
W=$(python3 -c "print(int(($XMAX-($XMIN))*111320*0.81/30))"); H=$(python3 -c "print(int(($YMAX-($YMIN))*111320/30))")
curl -s --max-time 180 -G "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage" \
  --data-urlencode "bbox=$XMIN,$YMIN,$XMAX,$YMAX" --data-urlencode "bboxSR=4326" --data-urlencode "imageSR=4326" \
  --data-urlencode "size=$W,$H" --data-urlencode "format=tiff" --data-urlencode "pixelType=F32" \
  --data-urlencode "f=image" -o dem.tif
gdalwarp -q -overwrite -t_srs EPSG:26915 -tr 30 30 -r bilinear dem.tif dem_utm.tif

echo "== 3. Candidate high points per zone (elev-sampled near-shore parcels) =="
psql "$CONN" -q -f "$HERE/sql/candidates_pool.sql"
psql "$CONN" --csv -t -c "SELECT fid,x,y FROM cand_pool" > cand_coords.csv
awk -F, '{print $2, $3}' cand_coords.csv | gdallocationinfo -valonly -geoloc dem_utm.tif > cand_elev.csv
paste -d, <(cut -d, -f1 cand_coords.csv) cand_elev.csv > cand_fid_elev.csv
psql "$CONN" -q -c "DROP TABLE IF EXISTS tmp_elev; CREATE TABLE tmp_elev(fid int, elev double precision);"
psql "$CONN" -q -c "\copy tmp_elev FROM 'cand_fid_elev.csv' WITH (FORMAT csv)"
psql "$CONN" -q -f "$HERE/sql/candidates_pick.sql"

echo "== 4. Viewsheds + coverage + visibility edges =="
psql "$CONN" --csv -t -c "SELECT parcelid, ST_X(ST_Transform(geom,26915)), ST_Y(ST_Transform(geom,26915)) FROM premises" > prem_utm.csv
awk -F, '{print $2, $3}' prem_utm.csv > prem_xy.txt; awk -F, '{print $1}' prem_utm.csv > prem_ids.txt
psql "$CONN" --csv -t -c "SELECT zone_id,parcelid,round(elev::numeric,0),x,y FROM candidates ORDER BY zone_id,elev DESC" > cand_list.csv
: > cand_coverage.csv; : > edges.csv
while IFS=, read ZONE PID ELEV X Y; do
  gdal_viewshed -q -md 8000 -oz 10 -tz 4 -ox "$X" -oy "$Y" dem_utm.tif vs/v.tif 2>/dev/null
  gdallocationinfo -valonly -geoloc vs/v.tif < prem_xy.txt 2>/dev/null | paste -d, prem_ids.txt - > vlt.csv
  echo "$ZONE,$PID,$ELEV,$X,$Y,$(awk -F, '$2==255' vlt.csv | wc -l)" >> cand_coverage.csv
  awk -F, -v c="$PID" '$2==255{print c","$1}' vlt.csv >> edges.csv
done < cand_list.csv

echo "== 5. Greedy set-cover + persist nodes + build order =="
psql "$CONN" -q -c "DROP TABLE IF EXISTS vis_edges; CREATE TABLE vis_edges(cand text, prem text);"
psql "$CONN" -q -c "\copy vis_edges FROM 'edges.csv' WITH (FORMAT csv)"
psql "$CONN" -q -c "CREATE INDEX ON vis_edges(cand); CREATE INDEX ON vis_edges(prem);"
psql "$CONN" -q -c "DROP TABLE IF EXISTS cand_cov; CREATE TABLE cand_cov(zone_id text,parcelid text,elev numeric,x double precision,y double precision,vis int);"
psql "$CONN" -q -c "\copy cand_cov FROM 'cand_coverage.csv' WITH (FORMAT csv)"
psql "$CONN" -q -f "$HERE/sql/greedy_and_rank.sql"

echo "== 6. Export outputs (CSV + GeoJSON) =="
GJ(){ psql "$CONN" -tAc "$1" > "$OUT/$2"; }
psql "$CONN" --csv -c "SELECT zone_id,place zone_name,county,premises,commercial,median_value,over_1m homes_over_1m,round(ST_Y(centroid)::numeric,5) lat,round(ST_X(centroid)::numeric,5) lon FROM zones_final ORDER BY zone_id" > "$OUT/zones_summary.csv"
psql "$CONN" --csv -c "SELECT phase,zone_id,place zone_name,county,premises,commercial,median_value,over_1m,pct_los,nodes_in_set,build_score FROM zone_rank ORDER BY build_score DESC" > "$OUT/zone_build_order.csv"
psql "$CONN" --csv -c "SELECT priority,zone_id,(SELECT place FROM zones_final z WHERE z.zone_id=p.zone_id) zone_name,parcelid,ownername,site_type,round(elev*3.28084) elev_ft,new_premises,cumulative cumulative_covered,total_visible_8km,is_primary,round(ST_Y(geom)::numeric,6) lat,round(ST_X(geom)::numeric,6) lon FROM proposed_nodes p ORDER BY priority" > "$OUT/proposed_nodes.csv"
psql "$CONN" --csv -c "SELECT priority nodes_built,cumulative premises_covered,round(100.0*cumulative/9571,1) pct_all,round(100.0*cumulative/8279,1) pct_los_reachable FROM proposed_nodes ORDER BY priority" > "$OUT/node_coverage_curve.csv"
psql "$CONN" --csv -c "SELECT county,count(*) FILTER (WHERE impvalue>0 AND dist_band='0-0.25mi') prem_0_025mi,count(*) FILTER (WHERE impvalue>0 AND dist_band='0.25-0.5mi') prem_025_05mi,count(*) FILTER (WHERE impvalue>0 AND dist_band='0.5-1mi') prem_05_1mi,count(*) FILTER (WHERE impvalue>0 AND dist_band<>'outside') premises_1mi_total,count(*) FILTER (WHERE (impvalue=0 OR impvalue IS NULL) AND dist_band<>'outside') vacant_parcels_1mi FROM stg_parcel_centroid WHERE dist_band<>'outside' GROUP BY county ORDER BY premises_1mi_total DESC" > "$OUT/premises_passed_by_county.csv"
psql "$CONN" --csv -c "SELECT parcelid,ownername,county,parceltype,impvalue,totalvalue,dist_band,round(ST_Y(geom)::numeric,6) lat,round(ST_X(geom)::numeric,6) lon FROM premises ORDER BY county,totalvalue DESC" > "$OUT/premises_points.csv"
GJ "SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom,0.0003)) FROM beaver_lake" lake.geojson
GJ "SELECT json_build_object('type','FeatureCollection','features',coalesce(json_agg(json_build_object('type','Feature','properties',json_build_object('zone_id',zone_id,'name',place,'county',county,'premises',premises,'median_value',median_value,'over_1m',over_1m,'commercial',commercial,'phase',(SELECT phase FROM zone_rank zr WHERE zr.zone_id=zf.zone_id)),'geometry',ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom,0.0004))::json)),'[]'::json)) FROM zones_final zf" zones.geojson
GJ "SELECT json_build_object('type','FeatureCollection','features',coalesce(json_agg(json_build_object('type','Feature','properties',json_build_object('z',zone_id,'v',totalvalue,'b',dist_band,'los',los_covered),'geometry',ST_AsGeoJSON(geom)::json)),'[]'::json)) FROM premises" premises.geojson
GJ "SELECT json_build_object('type','FeatureCollection','features',coalesce(json_agg(json_build_object('type','Feature','properties',json_build_object('priority',priority,'zone',zone_id,'elev_ft',round(elev*3.28084),'new',new_premises,'cum',cumulative,'vis8km',total_visible_8km,'site',site_type,'owner',ownername,'primary',is_primary),'geometry',ST_AsGeoJSON(geom)::json)),'[]'::json)) FROM proposed_nodes" proposed_nodes.geojson

echo "== 7. Build interactive map (self-contained canvas — no external deps) =="
python3 "$HERE/make_map_canvas_html.py" "$OUT" "$OUT/beaver_lake_network_map.html"
echo "== DONE — see $OUT =="
