-- candidates_pool.sql — near-shore parcels (<=0.5mi), any improvement status
-- (vacant land is a valid host-node/tower site), tagged to nearest zone, with UTM xy.
DROP TABLE IF EXISTS cand_pool;
CREATE TABLE cand_pool AS
SELECT p.ogc_fid AS fid, p.parcelid, p.ownername, p.impvalue, p.dist_band,
       (SELECT zf.zone_id FROM zones_final zf ORDER BY zf.centroid <-> p.geom LIMIT 1) AS zone_id,
       ST_X(ST_Transform(p.geom,26915)) AS x, ST_Y(ST_Transform(p.geom,26915)) AS y, p.geom
FROM stg_parcel_centroid p
WHERE p.dist_band IN ('0-0.25mi','0.25-0.5mi');
