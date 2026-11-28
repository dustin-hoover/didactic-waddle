#!/usr/bin/env python3
"""Self-contained interactive map — NO external resources (no CDN, no web fonts, no
tiles). Everything (lake, zones, premises, nodes) is drawn on an inline <canvas> with
custom pan/zoom/click. Works in any browser and inside the strictest artifact sandbox,
online or offline.

Usage: python3 make_map_canvas_html.py <outputs_dir> <out_html>
"""
import json, sys
outdir, out_html = sys.argv[1], sys.argv[2]
def rd(p): return open(f"{outdir}/{p}").read()
lake, zones, premises, nodes = rd("lake.geojson"), rd("zones.geojson"), rd("premises.geojson"), rd("proposed_nodes.geojson")
try: spine = rd("spine.geojson")
except FileNotFoundError: spine = '{"type":"FeatureCollection","features":[]}'
S = dict(premises=9571, shore=6144, zones=18, nodes=30, cov=84, median=410)

HTML = f"""<title>Beaver Lake Network Map</title>
<style>
:root{{
  --bg:#e9eef0; --panel:#ffffffec; --line:#c9d6db; --ink:#122029; --muted:#5a6b75;
  --water:#bfe0e6; --water-edge:#4f9aa6; --cov:#0e7c8b; --shadow:#e07a34;
  --node:#12222c; --node-ring:#f2b705; --p1:#c94b4b; --p2:#e08a3c; --p3:#3f8fa6; --p4:#8797a0;
}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --bg:#0c151b; --panel:#11202aec; --line:#25363f; --ink:#e6eef2; --muted:#8fa3ad;
  --water:#123038; --water-edge:#3d7f8c; --cov:#2bb3c4; --shadow:#f0904a;
  --node:#0a1319; --node-ring:#f2b705; --p1:#d15b5b; --p2:#e8a05a; --p3:#57a3ba; --p4:#6f8088;
}}}}
:root[data-theme="dark"]{{
  --bg:#0c151b; --panel:#11202aec; --line:#25363f; --ink:#e6eef2; --muted:#8fa3ad;
  --water:#123038; --water-edge:#3d7f8c; --cov:#2bb3c4; --shadow:#f0904a;
  --node:#0a1319; --node-ring:#f2b705; --p1:#d15b5b; --p2:#e8a05a; --p3:#57a3ba; --p4:#6f8088;
}}
*{{box-sizing:border-box}} html,body{{height:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  overflow:hidden}}
#wrap{{position:absolute;inset:0}}
canvas{{position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:grab}}
canvas.drag{{cursor:grabbing}}
.mono{{font-family:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}}
.bar{{position:absolute;z-index:5;top:0;left:0;right:0;display:flex;gap:12px;align-items:center;
  flex-wrap:wrap;padding:9px 16px;background:var(--panel);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line)}}
.bar h1{{font-size:15px;font-weight:700;margin:0;letter-spacing:.01em;white-space:nowrap}}
.bar .sub{{font-size:11px;color:var(--muted);margin-top:1px}}
.chips{{display:flex;gap:7px;flex-wrap:wrap;margin-left:auto}}
.chip{{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:4px 9px;line-height:1.15}}
.chip b{{display:block;font-size:14px}} .chip span{{font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
.panel{{position:absolute;z-index:5;left:14px;bottom:14px;width:220px;max-width:calc(100vw - 28px);
  background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--line);border-radius:12px;padding:11px 12px;font-size:12px}}
.panel h2{{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);margin:0 0 7px}}
.row{{display:flex;align-items:center;gap:8px;padding:3px 0;cursor:pointer;user-select:none}}
.sw{{width:11px;height:11px;border-radius:3px;flex:0 0 auto;border:1px solid #0003}}
.dot{{width:9px;height:9px;border-radius:50%;flex:0 0 auto}}
.foot{{margin-top:8px;padding-top:8px;border-top:1px solid var(--line);color:var(--muted);font-size:10px;line-height:1.4}}
.ctrl{{position:absolute;z-index:5;right:14px;top:64px;display:flex;flex-direction:column;gap:6px}}
.ctrl button{{width:34px;height:34px;font-size:18px;border:1px solid var(--line);background:var(--panel);
  color:var(--ink);border-radius:9px;cursor:pointer;line-height:1}}
.ctrl button:active{{transform:translateY(1px)}}
#pop{{position:absolute;z-index:6;max-width:250px;background:var(--panel);backdrop-filter:blur(8px);
  border:1px solid var(--line);border-radius:10px;padding:9px 11px;font-size:12px;line-height:1.45;
  box-shadow:0 6px 20px #0003;pointer-events:none;display:none}}
#pop h3{{margin:0 0 3px;font-size:13px}} #pop .mono{{color:var(--muted)}}
@media (max-width:560px){{.panel{{width:calc(100vw - 28px)}} .chip:nth-child(n+4){{display:none}}}}
</style>
<div id="wrap">
  <canvas id="cv"></canvas>
  <div class="bar">
    <div><h1>Beaver Lake Network</h1>
      <div class="sub mono">premises-passed &amp; node siting · NHD + AR GIS + 3DEP viewshed</div></div>
    <div class="chips mono">
      <div class="chip"><b>{S['premises']:,}</b><span>premises ≤1mi</span></div>
      <div class="chip"><b>{S['shore']:,}</b><span>≤¼mi shore</span></div>
      <div class="chip"><b>{S['zones']}</b><span>zones</span></div>
      <div class="chip"><b>{S['nodes']}→{S['cov']}%</b><span>nodes cover</span></div>
      <div class="chip"><b>${S['median']}k</b><span>median home</span></div>
    </div>
  </div>
  <div class="ctrl">
    <button id="zin" title="Zoom in">+</button>
    <button id="zout" title="Zoom out">−</button>
    <button id="zfit" title="Reset view" style="font-size:12px">fit</button>
  </div>
  <div class="panel">
    <h2>Layers</h2>
    <label class="row"><input type="checkbox" id="L-zones" checked><span class="sw" style="background:#3f8fa688"></span>Service zones (18)</label>
    <label class="row"><input type="checkbox" id="L-cov" checked><span class="dot" style="background:var(--cov)"></span>Premises — LOS covered</label>
    <label class="row"><input type="checkbox" id="L-shadow" checked><span class="dot" style="background:var(--shadow)"></span>Premises — RF shadow</label>
    <label class="row"><input type="checkbox" id="L-spine" checked><span class="sw" style="background:var(--node-ring);border-radius:0"></span>Backbone spine (41 hops)</label>
    <label class="row"><input type="checkbox" id="L-nodes" checked><span class="dot" style="background:var(--node-ring)"></span>Proposed nodes (30)</label>
    <div class="foot">Drag to pan · scroll/buttons to zoom · click a zone or node for detail. Zone shade = build phase (1 darkest→4). Solid spine = over-water licensed microwave; dashed = land. ~13% of premises are in RF shadow.</div>
  </div>
  <div id="pop"></div>
</div>
<script>
const LAKE={lake}, ZONES={zones}, PREM={premises}, NODES={nodes}, SPINE={spine};
const cv=document.getElementById('cv'), ctx=cv.getContext('2d'), pop=document.getElementById('pop');
const cssv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const phaseCol=p=>cssv('--p'+(p||4));
const vis={{zones:true,cov:true,shadow:true,nodes:true,spine:true}};

// ---- geometry helpers ----
function polys(geom){{ // -> array of rings (outer+holes flattened, each ring = [[lon,lat]...])
  if(!geom) return [];
  if(geom.type==='Polygon') return geom.coordinates;
  if(geom.type==='MultiPolygon'){{let r=[];for(const p of geom.coordinates)r.push(...p);return r;}}
  return [];
}}
// bounds from lake
let minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9;
for(const ring of polys(LAKE)) for(const[x,y] of ring){{minx=Math.min(minx,x);maxx=Math.max(maxx,x);miny=Math.min(miny,y);maxy=Math.max(maxy,y);}}
const lat0=(miny+maxy)/2, kx=Math.cos(lat0*Math.PI/180);
const wx=x=>x*kx, wy=y=>-y;                       // world coords
const wminx=wx(minx),wmaxx=wx(maxx),wminy=wy(maxy),wmaxy=wy(miny);
const wcx=(wminx+wmaxx)/2, wcy=(wminy+wmaxy)/2;

let DPR=Math.max(1,window.devicePixelRatio||1), W=0,H=0, base=1, zoom=1, panx=0, pany=0;
function resize(){{
  W=cv.clientWidth; H=cv.clientHeight; cv.width=W*DPR; cv.height=H*DPR;
  base=Math.min(W/(wmaxx-wminx), H/(wmaxy-wminy))*0.92;
  draw();
}}
function fit(){{zoom=1;panx=0;pany=0;draw();}}
const sx=x=>(wx(x)-wcx)*base*zoom + W/2 + panx;
const sy=y=>(wy(y)-wcy)*base*zoom + H/2 + pany;
const invLon=px=>((px - W/2 - panx)/(base*zoom) + wcx)/kx;
const invLat=py=>-(((py - H/2 - pany)/(base*zoom)) + wcy);

function drawPolyGeom(geom){{ for(const ring of polys(geom)){{ ctx.beginPath();
  for(let i=0;i<ring.length;i++){{const X=sx(ring[i][0]),Y=sy(ring[i][1]); i?ctx.lineTo(X,Y):ctx.moveTo(X,Y);}}
  ctx.closePath(); ctx.fill(); ctx.stroke(); }} }}

function draw(){{
  ctx.setTransform(DPR,0,0,DPR,0,0);
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle=cssv('--bg'); ctx.fillRect(0,0,W,H);
  // lake
  ctx.fillStyle=cssv('--water'); ctx.strokeStyle=cssv('--water-edge'); ctx.lineWidth=1;
  drawPolyGeom(LAKE);
  // zones
  if(vis.zones){{ ctx.lineWidth=1.2;
    for(const f of ZONES.features){{const c=phaseCol(f.properties.phase);
      ctx.fillStyle=c+'26'; ctx.strokeStyle=c; drawPolyGeom(f.geometry);}} }}
  // premises (fast fillRect)
  const r=Math.max(1.1, 1.6*Math.min(zoom,2.2));
  for(const f of PREM.features){{const p=f.properties;
    if(p.los && !vis.cov) continue; if(!p.los && !vis.shadow) continue;
    const X=sx(f.geometry.coordinates[0]), Y=sy(f.geometry.coordinates[1]);
    if(X<-5||X>W+5||Y<-5||Y>H+5) continue;
    ctx.fillStyle=p.los?cssv('--cov'):cssv('--shadow');
    ctx.fillRect(X-r/2,Y-r/2,r,r);}}
  // spine
  if(vis.spine){{ ctx.lineWidth=1.4;
    for(const f of SPINE.features){{const c=f.geometry.coordinates, over=(f.properties.class||'').indexOf('water')===0;
      ctx.beginPath(); ctx.moveTo(sx(c[0][0]),sy(c[0][1])); ctx.lineTo(sx(c[1][0]),sy(c[1][1]));
      ctx.strokeStyle=cssv('--node-ring'); ctx.setLineDash(over?[]:[4,3]);
      ctx.globalAlpha=over?0.9:0.65; ctx.stroke();}}
    ctx.setLineDash([]); ctx.globalAlpha=1; }}
  // nodes
  if(vis.nodes){{ ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.font='600 11px ui-monospace,Menlo,monospace';
    for(const f of NODES.features){{const X=sx(f.geometry.coordinates[0]),Y=sy(f.geometry.coordinates[1]);
      ctx.beginPath();ctx.arc(X,Y,11,0,7); ctx.fillStyle=cssv('--node');ctx.fill();
      ctx.lineWidth=2;ctx.strokeStyle=cssv('--node-ring');ctx.stroke();
      ctx.fillStyle='#fff';ctx.fillText(f.properties.priority,X,Y+0.5);}} }}
}}

// ---- interaction ----
let dragging=false,lastx,lasty,moved=0;
cv.addEventListener('pointerdown',e=>{{dragging=true;moved=0;lastx=e.clientX;lasty=e.clientY;cv.classList.add('drag');cv.setPointerCapture(e.pointerId);}});
cv.addEventListener('pointermove',e=>{{if(!dragging)return;const dx=e.clientX-lastx,dy=e.clientY-lasty;
  panx+=dx;pany+=dy;moved+=Math.abs(dx)+Math.abs(dy);lastx=e.clientX;lasty=e.clientY;draw();}});
cv.addEventListener('pointerup',e=>{{dragging=false;cv.classList.remove('drag');if(moved<4)clickAt(e.clientX,e.clientY);}});
cv.addEventListener('wheel',e=>{{e.preventDefault();const f=e.deltaY<0?1.15:1/1.15;
  const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
  panx=mx-(mx-panx)*f; pany=my-(my-pany)*f; zoom*=f; draw();}},{{passive:false}});
document.getElementById('zin').onclick=()=>{{zoom*=1.3;draw();}};
document.getElementById('zout').onclick=()=>{{zoom/=1.3;draw();}};
document.getElementById('zfit').onclick=fit;
for(const k of ['zones','cov','shadow','nodes','spine'])
  document.getElementById('L-'+k).addEventListener('change',e=>{{vis[k]=e.target.checked;draw();}});

function pointInRings(lon,lat,geom){{let inside=false;
  for(const ring of polys(geom)){{for(let i=0,j=ring.length-1;i<ring.length;j=i++){{
    const xi=ring[i][0],yi=ring[i][1],xj=ring[j][0],yj=ring[j][1];
    if(((yi>lat)!=(yj>lat)) && (lon < (xj-xi)*(lat-yi)/(yj-yi)+xi)) inside=!inside;}}}}
  return inside;}}
function clickAt(cxp,cyp){{const r=cv.getBoundingClientRect(),px=cxp-r.left,py=cyp-r.top;
  // nodes first
  if(vis.nodes){{for(const f of NODES.features){{const X=sx(f.geometry.coordinates[0]),Y=sy(f.geometry.coordinates[1]);
    if((px-X)**2+(py-Y)**2<=196){{const p=f.properties;return showPop(cxp,cyp,
      `<h3>Node #${{p.priority}} <span class="mono">${{p.zone}}</span></h3>
       <div class="mono">${{p.elev_ft}} ft · ${{p.primary?'zone anchor':'fill site'}}</div>
       <div>sees <b>${{(p.vis8km||0).toLocaleString()}}</b> premises ≤8km · <b>+${{p.new}}</b> new</div>
       <div class="mono">${{p.site}}</div>`);}}}}}}
  // zones
  if(vis.zones){{const lon=invLon(px),lat=invLat(py);
    for(const f of ZONES.features){{if(pointInRings(lon,lat,f.geometry)){{const p=f.properties;return showPop(cxp,cyp,
      `<h3>${{p.name}} <span class="mono">${{p.zone_id}}</span></h3>
       <div class="mono">${{p.county}} County · phase ${{p.phase||'—'}}</div>
       <div><b>${{(p.premises||0).toLocaleString()}}</b> premises · ${{p.commercial||0}} commercial</div>
       <div class="mono">median $${{(p.median_value||0).toLocaleString()}} · ${{p.over_1m||0}} homes &gt;$1M</div>`);}}}}}}
  pop.style.display='none';}}
function showPop(cx,cy,html){{const r=cv.getBoundingClientRect();pop.innerHTML=html;pop.style.display='block';
  let x=cx-r.left+12,y=cy-r.top+12; if(x+250>W)x=W-256; if(y+120>H)y=H-124;
  pop.style.left=x+'px';pop.style.top=y+'px';}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')pop.style.display='none';}});

window.addEventListener('resize',()=>{{DPR=Math.max(1,window.devicePixelRatio||1);resize();}});
const mq=window.matchMedia('(prefers-color-scheme:dark)'); mq.addEventListener&&mq.addEventListener('change',draw);
resize();
</script>
"""
open(out_html,"w").write(HTML)
print(f"wrote {out_html} ({len(HTML)//1024} KB)")
