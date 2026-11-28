#!/usr/bin/env python3
"""Build a TRUE LiDAR first-return DSM from a USGS 3DEP EPT (Entwine) point cloud.

Walks the EPT octree hierarchy for nodes overlapping a bbox, fetches their LAZ,
and grids the MAX Z per cell (canopy top) into a GeoTIFF (EPSG:26915). Cells with
no points are left nodata (fill downstream from a bare-earth DEM if desired).

Usage:
  python3 ept_dsm.py survey  <ept_base_url> <minlon> <minlat> <maxlon> <maxlat> <maxdepth>
  python3 ept_dsm.py build   <ept_base_url> <minlon> <minlat> <maxlon> <maxlat> <maxdepth> <cell_m> <out.tif>
"""
import json, sys, urllib.request, io
import numpy as np
from pyproj import Transformer

def http(url, timeout=90, tries=4):
    last=None
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r: return r.read()
        except Exception as e:
            last=e; import time; time.sleep(1.5*(a+1))
    raise RuntimeError(f"GET failed {url}: {last}")

def main():
    mode=sys.argv[1]; base=sys.argv[2].rstrip('/')
    minlon,minlat,maxlon,maxlat=map(float,sys.argv[3:7]); maxdepth=int(sys.argv[7])
    ept=json.loads(http(base+"/ept.json"))
    bounds=ept["bounds"]; edge=bounds[3]-bounds[0]
    cx0,cy0=bounds[0],bounds[1]
    # bbox in EPT srs (3857)
    to3857=Transformer.from_crs("EPSG:4326","EPSG:3857",always_xy=True)
    (bx0,bx1),(by0,by1)=zip(to3857.transform(minlon,minlat),to3857.transform(maxlon,maxlat))
    bx0,bx1=sorted([bx0,bx1]); by0,by1=sorted([by0,by1])
    def node_xy(d,x,y):
        step=edge/(2**d)
        return cx0+x*step, cx0+(x+1)*step, cy0+y*step, cy0+(y+1)*step
    def overlaps(d,x,y):
        nx0,nx1,ny0,ny1=node_xy(d,x,y)
        return nx1>bx0 and nx0<bx1 and ny1>by0 and ny0<by1
    pages={}
    def page(key):
        if key not in pages:
            try: pages[key]=json.loads(http(f"{base}/ept-hierarchy/{key}.json"))
            except Exception: pages[key]={}
        return pages[key]
    root=page("0-0-0-0")
    known=dict(root)
    def count(k): return known.get(k)
    # BFS collect target nodes (leaf or at maxdepth) overlapping bbox
    from collections import deque
    targets=[]; q=deque([(0,0,0,0)])
    seen=set()
    while q:
        d,x,y,z=q.popleft()
        key=f"{d}-{x}-{y}-{z}"
        if key in seen: continue
        seen.add(key)
        c=count(key)
        if c is None or c==0:
            # maybe in a subpage rooted here
            sp=page(key); known.update(sp); c=known.get(key,0)
            if not c: continue
        if d>=maxdepth:
            targets.append((key,c)); continue
        # ensure children known
        kids=[(d+1,2*x+dx,2*y+dy,2*z+dz) for dx in(0,1) for dy in(0,1) for dz in(0,1)]
        if not any(f"{a}-{b}-{cc}-{e}" in known for (a,b,cc,e) in kids):
            sp=page(key); known.update(sp)
        anykid=False
        for (a,b,cc,e) in kids:
            kk=f"{a}-{b}-{cc}-{e}"
            if known.get(kk):
                if overlaps(a,b,cc): q.append((a,b,cc,e)); anykid=True
            elif overlaps(a,b,cc):
                # try subpage rooted at child
                sp=page(kk)
                if sp: known.update(sp);
                if known.get(kk): q.append((a,b,cc,e)); anykid=True
        if not anykid:
            targets.append((key,c))
    tot=sum(c for _,c in targets)
    if mode=="survey":
        print(f"target nodes: {len(targets)}  points(cumulative-in-nodes): {tot:,}")
        print("depth histogram:", {d:sum(1 for k,_ in targets if int(k.split('-')[0])==d) for d in sorted(set(int(k.split('-')[0]) for k,_ in targets))})
        return
    # build: fetch laz, grid max Z in 26915
    cell=float(sys.argv[8]); outp=sys.argv[9]
    import laspy, rasterio
    from rasterio.transform import from_origin
    t26=Transformer.from_crs("EPSG:3857","EPSG:26915",always_xy=True)
    # output grid from bbox corners in 26915
    (ux0,uy0)=t26.transform(bx0,by0); (ux1,uy1)=t26.transform(bx1,by1)
    ux0,ux1=sorted([ux0,ux1]); uy0,uy1=sorted([uy0,uy1])
    ncol=int((ux1-ux0)/cell)+1; nrow=int((uy1-uy0)/cell)+1
    grid=np.full((nrow,ncol),-9999.0,dtype="float32")
    n=0
    for i,(key,c) in enumerate(targets):
        try: raw=http(f"{base}/ept-data/{key}.laz")
        except Exception: continue
        las=laspy.read(io.BytesIO(raw))
        cls=np.asarray(las.classification)
        keep=~np.isin(cls,[7,18])  # drop noise
        X=np.asarray(las.x)[keep]; Y=np.asarray(las.y)[keep]; Z=np.asarray(las.z)[keep]
        if len(X)==0: continue
        ux,uy=t26.transform(X,Y)
        col=((ux-ux0)/cell).astype(int); row=((uy1-uy0-(uy-uy0))/cell).astype(int)
        m=(col>=0)&(col<ncol)&(row>=0)&(row<nrow)
        col,row,zz=col[m],row[m],Z[m].astype("float32")
        # max-Z per cell
        flat=row*ncol+col
        order=np.argsort(flat); flat=flat[order]; zz=zz[order]
        uniq,idx=np.unique(flat,return_index=True)
        cummax=np.maximum.reduceat(zz,idx)
        r=uniq//ncol; cc=uniq%ncol
        cur=grid[r,cc]; better=cummax>cur;
        grid[r[better],cc[better]]=cummax[better]
        n+=len(X)
        if i%20==0: print(f"  {i+1}/{len(targets)} nodes, {n:,} pts", file=sys.stderr)
    prof=dict(driver="GTiff",height=nrow,width=ncol,count=1,dtype="float32",
              crs="EPSG:26915",transform=from_origin(ux0,uy1,cell,cell),nodata=-9999.0,compress="deflate")
    with rasterio.open(outp,"w",**prof) as o: o.write(grid,1)
    valid=(grid!=-9999.0)
    print(f"wrote {outp}: {ncol}x{nrow} @{cell}m, {n:,} pts, {valid.mean()*100:.0f}% cells filled, "
          f"z {grid[valid].min():.0f}..{grid[valid].max():.0f} m")

if __name__=="__main__": main()
