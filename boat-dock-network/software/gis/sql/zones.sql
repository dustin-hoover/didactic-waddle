-- zones.sql — cluster improved premises into 18 service zones, build hull polygons,
-- name from nearest GNIS place, populate DockOS zones, tag premises with zone_id.
DROP TABLE IF EXISTS premises CASCADE;
CREATE TABLE premises AS
SELECT parcelid, ownername, county, parceltype, impvalue, totalvalue, dist_band, geom,
       ST_ClusterKMeans(ST_Transform(geom,26915), 18) OVER () AS cid
FROM stg_parcel_centroid WHERE impvalue>0 AND dist_band<>'outside';
CREATE INDEX ON premises USING gist(geom);

DROP TABLE IF EXISTS zones_auto CASCADE;
CREATE TABLE zones_auto AS
SELECT cid, count(*) premises, mode() WITHIN GROUP (ORDER BY county) county,
  round(avg(totalvalue) FILTER (WHERE totalvalue>0)) avg_value,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY totalvalue) FILTER (WHERE totalvalue>0)) median_value,
  count(*) FILTER (WHERE totalvalue>=1000000) over_1m,
  count(*) FILTER (WHERE parceltype IN ('CI','CG','CR','CP')) commercial,
  ST_Multi(ST_ConcaveHull(ST_Collect(geom),0.6)) geom, ST_Centroid(ST_Collect(geom)) centroid
FROM premises GROUP BY cid;

ALTER TABLE zones_auto ADD COLUMN IF NOT EXISTS place text;
UPDATE zones_auto z SET place = (
  SELECT g.feature_name FROM stg_gnis g
  WHERE g.feature_class IN ('Park','Populated Place','Locale','Civil','Dam','Bay','Reservoir','Crossing')
  ORDER BY z.centroid <-> g.geom LIMIT 1);

DROP TABLE IF EXISTS zones_final;
CREATE TABLE zones_final AS
SELECT 'Z-'||lpad((row_number() OVER (ORDER BY premises DESC))::text,2,'0') zone_id,
       place, cid, premises, county, median_value, over_1m, commercial, geom, centroid
FROM zones_auto;
WITH d AS (SELECT zone_id, place, count(*) OVER (PARTITION BY place) c,
       row_number() OVER (PARTITION BY place ORDER BY zone_id) rn FROM zones_final)
UPDATE zones_final z SET place = CASE WHEN d.c>1 THEN d.place||' '||d.rn ELSE d.place END
FROM d WHERE z.zone_id=d.zone_id;

DELETE FROM zones;
INSERT INTO zones (zone_id,name,status,geom) SELECT zone_id,place,'planned',geom FROM zones_final;
ALTER TABLE premises ADD COLUMN IF NOT EXISTS zone_id text;
UPDATE premises p SET zone_id = zf.zone_id FROM zones_final zf WHERE p.cid=zf.cid;
