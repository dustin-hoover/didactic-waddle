-- candidates_pick.sql — attach sampled elevations (tmp_elev), pick top-6 highest
-- near-shore parcels per zone as viewshed candidates.
ALTER TABLE cand_pool ADD COLUMN IF NOT EXISTS elev double precision;
UPDATE cand_pool c SET elev = t.elev FROM tmp_elev t WHERE c.fid=t.fid;

DROP TABLE IF EXISTS candidates;
CREATE TABLE candidates AS
SELECT * FROM (
  SELECT zone_id, parcelid, ownername, impvalue, dist_band, elev, x, y, geom,
         row_number() OVER (PARTITION BY zone_id ORDER BY elev DESC) rnk
  FROM cand_pool WHERE elev IS NOT NULL) s
WHERE rnk<=6;
