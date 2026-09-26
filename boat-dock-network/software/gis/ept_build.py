#!/usr/bin/env python3
"""Build a true LiDAR canopy DSM (max-Z per cell) from a USGS 3DEP EPT, using only the
root hierarchy page (positive-count nodes over the bbox — no octree crawl). Output
GeoTIFF in EPSG:26915 at the given cell size. See ept_dsm.py for the general crawler.

Usage: python3 ept_build.py <ept_base> <minlon> <minlat> <maxlon> <maxlat> <cell_m> <out.tif>
"""
import io, json, sys, urllib.request, time
import numpy as np, laspy, rasterio
from rasterio.transform import from_origin
from pyproj import Transformer

base=sys.argv[1].rstrip('/'); minlon,minlat,maxlon,maxlat=map(float,sys.argv[2:6])
cell=float(sys.argv[6]); outp=sys.argv[7]
def http(u,t=120,n=4):
    for a in range(n):
        try:
            with urllib.request.urlopen(u,timeout=t) as r: return r.read()
        except Exception as e:
            last=e; time.sleep(1.5*(a+1))
    raise RuntimeError(f"GET {u}: {last}")

ept=json.loads(http(base+"/ept.json")); b=ept["bounds"]; cx0,cy0=b[0],b[1]; edge=b[3]-b[0]
h=json.loads(http(base+"/ept-hierarchy/0-0-0-0.json"))
t3857=Transformer.from_crs("EPSG:4326","EPSG:3857",always_xy=True)
(x0,y0)=t3857.transform(minlon,minlat); (x1,y1)=t3857.transform(maxlon,maxlat)
x0,x1=sorted([x0,x1]); y0,y1=sorted([y0,y1])
def ov(d,x,y):
    s=edge/2**d; nx0=cx0+x*s; ny0=cy0+y*s
    return nx0+s>x0 and nx0<x1 and ny0+s>y0 and ny0<y1
nodes=[k for k,v in h.items() if v>0 and ov(*map(int,k.split('-')[:3]))]
print(f"fetching {len(nodes)} LAZ nodes…",file=sys.stderr)

t26=Transformer.from_crs("EPSG:3857","EPSG:26915",always_xy=True)
(ux0,uy0)=t26.transform(x0,y0); (ux1,uy1)=t26.transform(x1,y1)
ux0,ux1=sorted([ux0,ux1]); uy0,uy1=sorted([uy0,uy1])
ncol=int((ux1-ux0)/cell)+1; nrow=int((uy1-uy0)/cell)+1
grid=np.full((nrow,ncol),-9999.0,dtype="float32"); npts=0
for i,k in enumerate(nodes):
    try: raw=http(f"{base}/ept-data/{k}.laz")
    except Exception: continue
    las=laspy.read(io.BytesIO(raw))
    cls=np.asarray(las.classification); keep=~np.isin(cls,[7,18])
    X=np.asarray(las.x)[keep]; Y=np.asarray(las.y)[keep]; Z=np.asarray(las.z)[keep].astype("float32")
    if len(X)==0: continue
    ux,uy=t26.transform(X,Y)
    col=((np.asarray(ux)-ux0)/cell).astype(int); row=((uy1-np.asarray(uy))/cell).astype(int)
    m=(col>=0)&(col<ncol)&(row>=0)&(row<nrow); col,row,zz=col[m],row[m],Z[m]
    flat=row*ncol+col; order=np.argsort(flat); flat=flat[order]; zz=zz[order]
    uniq,idx=np.unique(flat,return_index=True); cmax=np.maximum.reduceat(zz,idx)
    r=uniq//ncol; c=uniq%ncol; cur=grid[r,c]; better=cmax>cur
    grid[r[better],c[better]]=cmax[better]; npts+=len(X)
    if i%20==0: print(f"  {i+1}/{len(nodes)}  {npts:,} pts",file=sys.stderr)
prof=dict(driver="GTiff",height=nrow,width=ncol,count=1,dtype="float32",crs="EPSG:26915",
          transform=from_origin(ux0,uy1,cell,cell),nodata=-9999.0,compress="deflate")
with rasterio.open(outp,"w",**prof) as o: o.write(grid,1)
v=grid!=-9999.0
print(f"wrote {outp}: {ncol}x{nrow}@{cell}m  {npts:,} pts  {v.mean()*100:.0f}% filled  z {grid[v].min():.0f}..{grid[v].max():.0f}m")
