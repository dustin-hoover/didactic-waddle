-- greedy_and_rank.sql — greedy set-cover node selection, persist proposed_nodes +
-- DockOS nodes, mark shadow premises, build per-zone build-order ranking + phases.
DROP TABLE IF EXISTS covered; CREATE TABLE covered (prem text PRIMARY KEY);
DROP TABLE IF EXISTS chosen; CREATE TABLE chosen (step int, cand text, gain int, cumulative int);
DO $$
DECLARE s int:=0; c text; g int; cum int:=0; tot int;
BEGIN
  SELECT count(DISTINCT prem) INTO tot FROM vis_edges;
  LOOP
    SELECT e.cand, count(*) INTO c, g FROM vis_edges e
    WHERE NOT EXISTS (SELECT 1 FROM covered v WHERE v.prem=e.prem)
    GROUP BY e.cand ORDER BY count(*) DESC LIMIT 1;
    EXIT WHEN g IS NULL OR g=0;
    s:=s+1; cum:=cum+g; INSERT INTO chosen VALUES (s,c,g,cum);
    INSERT INTO covered SELECT DISTINCT prem FROM vis_edges WHERE cand=c
       AND prem NOT IN (SELECT prem FROM covered);
    EXIT WHEN cum >= tot*0.97;
  END LOOP;
END $$;

DROP TABLE IF EXISTS proposed_nodes;
CREATE TABLE proposed_nodes AS
SELECT ch.step priority, cc.zone_id, ch.cand parcelid, cc.elev, ch.gain new_premises,
       ch.cumulative, cc.vis total_visible_8km, cp.ownername, cp.impvalue,
       CASE WHEN cp.impvalue>0 THEN 'improved (existing owner)' ELSE 'vacant (acquire/lease)' END site_type,
       c.geom
FROM chosen ch JOIN cand_cov cc ON cc.parcelid=ch.cand
JOIN candidates c ON c.parcelid=ch.cand JOIN cand_pool cp ON cp.parcelid=ch.cand;
DELETE FROM proposed_nodes a USING proposed_nodes b WHERE a.priority=b.priority AND a.ctid>b.ctid;
ALTER TABLE proposed_nodes ADD COLUMN is_primary boolean;
UPDATE proposed_nodes p SET is_primary=(priority=(SELECT min(priority) FROM proposed_nodes q WHERE q.zone_id=p.zone_id));

ALTER TABLE premises ADD COLUMN IF NOT EXISTS los_covered boolean;
UPDATE premises SET los_covered=(parcelid IN (SELECT DISTINCT prem FROM vis_edges));

DELETE FROM nodes;
INSERT INTO nodes (node_id, zone_id, tier, status, host_property, elevation_ft, geom)
SELECT 'BDN-'||replace(zone_id,'Z-','Z')||'-T2-'||lpad(priority::text,2,'0'),
       zone_id,'T2','candidate',(impvalue>0),round((elev*3.28084)::numeric,0),geom
FROM proposed_nodes;

DROP TABLE IF EXISTS zone_rank;
CREATE TABLE zone_rank AS
WITH z AS (
  SELECT zf.zone_id, zf.place, zf.county, zf.premises, zf.commercial, zf.median_value, zf.over_1m,
    round(100.0*count(*) FILTER (WHERE p.los_covered)/zf.premises,0) pct_los,
    (SELECT count(*) FROM proposed_nodes n WHERE n.zone_id=zf.zone_id) nodes_in_set
  FROM zones_final zf JOIN premises p ON p.zone_id=zf.zone_id
  GROUP BY zf.zone_id, zf.place, zf.county, zf.premises, zf.commercial, zf.median_value, zf.over_1m),
n AS (SELECT *, premises::numeric/(SELECT max(premises) FROM z) s_prem,
    median_value::numeric/(SELECT max(median_value) FROM z) s_val, pct_los::numeric/100 s_los,
    commercial::numeric/GREATEST((SELECT max(commercial) FROM z),1) s_comm FROM z)
SELECT zone_id, place, county, premises, commercial, median_value, over_1m, pct_los, nodes_in_set,
  round((0.40*s_prem+0.20*s_val+0.25*s_los+0.15*s_comm)::numeric,3) build_score
FROM n;
ALTER TABLE zone_rank ADD COLUMN phase int;
WITH r AS (SELECT zone_id, row_number() OVER (ORDER BY build_score DESC) rn FROM zone_rank)
UPDATE zone_rank z SET phase=CASE WHEN r.rn<=3 THEN 1 WHEN r.rn<=8 THEN 2 WHEN r.rn<=13 THEN 3 ELSE 4 END
FROM r WHERE z.zone_id=r.zone_id;
UPDATE zones z SET phase=zr.phase FROM zone_rank zr WHERE z.zone_id=zr.zone_id;
