#!/usr/bin/env python3
"""Build a canopy-aware DSM: DSM = bare-earth DEM + canopy height model (CHM),
where CHM is derived from NLCD 2021 land cover classes. Foliage-aware LOS input.

Usage: python3 build_dsm.py <dem.tif> <landcover.tif> <out_dsm.tif>
Grids must align (same size/extent/CRS).
"""
import sys
import numpy as np
import rasterio

dem_p, lc_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]

# NLCD class -> canopy height (m). Ozark hardwood/pine canopy ~20-22 m.
CHM = {11:0, 12:0, 21:1, 22:2, 23:2, 24:2, 31:0,
       41:22, 42:20, 43:21, 51:2, 52:2,
       71:0.5, 72:0.5, 73:0.5, 74:0.5, 81:0.5, 82:0.5,
       90:14, 95:0}

with rasterio.open(dem_p) as d:
    dem = d.read(1).astype("float32"); prof = d.profile
with rasterio.open(lc_p) as l:
    lc = l.read(1)
assert dem.shape == lc.shape, f"grid mismatch {dem.shape} vs {lc.shape}"

chm = np.zeros_like(dem, dtype="float32")
for cls, h in CHM.items():
    chm[lc == cls] = h
dsm = dem + chm

prof.update(dtype="float32", count=1, compress="deflate")
with rasterio.open(out_p, "w", **prof) as o:
    o.write(dsm, 1)

forest = np.isin(lc, [41, 42, 43, 90])
print(f"forest/woody cells: {forest.mean()*100:.1f}% of tile")
print(f"CHM max {chm.max():.0f} m, mean(forest) {chm[forest].mean():.1f} m")
print(f"wrote {out_p}")
