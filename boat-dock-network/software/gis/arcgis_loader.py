#!/usr/bin/env python3
"""
arcgis_loader.py — pull features from an ArcGIS REST FeatureServer/MapServer layer
that intersect a spatial filter polygon, and write them to a GeoJSON file.

Reproducible data ingestion for Boat Dock Network premises-passed analysis.
No third-party deps (urllib only). Uses the OID-batch method so it works even on
servers with small maxRecordCount and no offset pagination.

Usage:
  python3 arcgis_loader.py \
      --url "https://.../MapServer/0" \
      --out benton_addresses.geojson \
      --fields "FULL_ADDR,CLASSIFICA,POINT_TYPE,PARCELID_1,CITY,ZIP_CODE" \
      --filter-geojson buffer_1mi.geojson \
      [--where "1=1"] [--batch 200]

--filter-geojson is a GeoJSON geometry (Polygon/MultiPolygon) in EPSG:4326 used as an
esriGeometryPolygon intersects filter. Precise clipping is done later in PostGIS.
"""
import argparse, json, sys, time, urllib.parse, urllib.request

def http_post(url, params, timeout=90, retries=4):
    data = urllib.parse.urlencode(params).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"POST failed after {retries} tries: {url}: {last}")

def geojson_to_esri_rings(geom):
    """Convert a GeoJSON Polygon/MultiPolygon to esri polygon 'rings'."""
    t = geom["type"]
    rings = []
    if t == "Polygon":
        rings = geom["coordinates"]
    elif t == "MultiPolygon":
        for poly in geom["coordinates"]:
            rings.extend(poly)
    else:
        raise ValueError(f"filter geometry must be Polygon/MultiPolygon, got {t}")
    return {"rings": rings, "spatialReference": {"wkid": 4326}}

def load_filter_geometry(path):
    d = json.load(open(path))
    if d.get("type") == "FeatureCollection":
        geom = d["features"][0]["geometry"]
    elif d.get("type") == "Feature":
        geom = d["geometry"]
    else:
        geom = d
    return json.dumps(geojson_to_esri_rings(geom))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="layer URL (…/FeatureServer/N or …/MapServer/N)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fields", required=True)
    ap.add_argument("--filter-geojson", required=True)
    ap.add_argument("--where", default="1=1")
    ap.add_argument("--batch", type=int, default=200)
    args = ap.parse_args()

    esri_geom = load_filter_geometry(args.filter_geojson)
    q = args.url.rstrip("/") + "/query"
    common = {
        "where": args.where,
        "geometry": esri_geom,
        "geometryType": "esriGeometryPolygon",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "f": "json",
    }

    # 1) get matching OIDs
    idres = http_post(q, {**common, "returnIdsOnly": "true"})
    oid_field = idres.get("objectIdFieldName", "OBJECTID")
    oids = idres.get("objectIds") or []
    print(f"[{args.url}] matching features: {len(oids)} (oid field: {oid_field})", file=sys.stderr)
    if not oids:
        json.dump({"type": "FeatureCollection", "features": []}, open(args.out, "w"))
        return

    # 2) fetch in OID batches as geojson
    feats = []
    for i in range(0, len(oids), args.batch):
        chunk = oids[i:i + args.batch]
        params = {
            "where": f"{oid_field} IN ({','.join(map(str, chunk))})",
            "outFields": args.fields,
            "outSR": "4326",
            "returnGeometry": "true",
            "f": "geojson",
        }
        res = http_post(q, params)
        got = res.get("features", [])
        feats.extend(got)
        print(f"  {min(i+args.batch,len(oids))}/{len(oids)}  (+{len(got)})", file=sys.stderr)
        time.sleep(0.2)

    fc = {"type": "FeatureCollection", "features": feats}
    json.dump(fc, open(args.out, "w"))
    print(f"wrote {len(feats)} features -> {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
