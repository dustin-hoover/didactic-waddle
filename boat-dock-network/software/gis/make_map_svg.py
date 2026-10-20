#!/usr/bin/env python3
"""Render a dependency-free SVG map: Beaver Lake + premises passed.
Inputs: lake GeoJSON polygon, premises_points.csv (lat,lon,dist_band,county).
No numpy/matplotlib — pure stdlib. Equirectangular projection with cos(lat) x-scale.
"""
import csv, json, math, sys

lake_path, pts_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

lake = json.load(open(lake_path))
geom = lake["features"][0]["geometry"] if lake.get("type") == "FeatureCollection" else lake.get("geometry", lake)
polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]

pts = []
with open(pts_path) as f:
    for r in csv.DictReader(f):
        try:
            pts.append((float(r["lon"]), float(r["lat"]), r.get("dist_band",""), r.get("county","")))
        except (ValueError, KeyError):
            pass

# bounds from lake
xs, ys = [], []
for poly in polys:
    for ring in poly:
        for x, y in ring:
            xs.append(x); ys.append(y)
minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
pad = 0.02
minx-=pad; maxx+=pad; miny-=pad; maxy+=pad
lat0 = (miny+maxy)/2
kx = math.cos(math.radians(lat0))
W = 1100
H = int(W * ((maxy-miny)) / ((maxx-minx)*kx))

def px(x, y):
    sx = (x-minx)/(maxx-minx) * W
    sy = H - (y-miny)/(maxy-miny) * H
    return sx, sy

def ring_to_path(ring):
    d = []
    for i,(x,y) in enumerate(ring):
        sx, sy = px(x,y)
        d.append(("M" if i==0 else "L") + f"{sx:.1f},{sy:.1f}")
    return " ".join(d) + " Z"

colors = {"0-0.25mi":"#0b7285", "0.25-0.5mi":"#3ba7bf", "0.5-1mi":"#9bd3dd"}
out = []
out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="system-ui,sans-serif">')
out.append(f'<rect width="{W}" height="{H}" fill="#0f1720"/>')
# lake
lake_d = " ".join(ring_to_path(r) for poly in polys for r in poly)
out.append(f'<path d="{lake_d}" fill="#16323b" stroke="#2b6b7a" stroke-width="1" fill-rule="evenodd"/>')
# premises points
for x,y,band,_ in pts:
    sx, sy = px(x,y)
    c = colors.get(band, "#c0c0c0")
    out.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="1.4" fill="{c}" fill-opacity="0.85"/>')
# legend
lx, ly = 24, H-110
out.append(f'<rect x="{lx-12}" y="{ly-24}" width="270" height="118" fill="#0b1015" fill-opacity="0.8" stroke="#2b6b7a" rx="6"/>')
out.append(f'<text x="{lx}" y="{ly-4}" fill="#e6edf3" font-size="15" font-weight="700">Beaver Lake — premises passed</text>')
labels = [("0–0.25 mi (shoreline)","0-0.25mi"),("0.25–0.5 mi","0.25-0.5mi"),("0.5–1 mi","0.5-1mi")]
for i,(txt,band) in enumerate(labels):
    yy = ly + 18 + i*22
    out.append(f'<circle cx="{lx+6}" cy="{yy-4}" r="5" fill="{colors[band]}"/>')
    out.append(f'<text x="{lx+20}" y="{yy}" fill="#c9d4dd" font-size="13">{txt}</text>')
out.append(f'<text x="{lx}" y="{ly+94}" fill="#8b98a5" font-size="11">{len(pts):,} improved parcels within 1 mi · NHD + AR GIS/Benton Co</text>')
out.append('</svg>')
open(out_path,"w").write("\n".join(out))
print(f"wrote {out_path} ({len(pts)} points, {W}x{H})")
