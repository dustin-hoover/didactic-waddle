#!/usr/bin/env python3
"""Assemble a self-contained interactive Leaflet map (no external tiles — the lake
polygon is the basemap, so it works inside the Artifact CSP). Embeds the GIS outputs
inline. Reproducible: reads data/gis/outputs/*.geojson + a vendored leaflet.min.css.

Usage: python3 make_map_html.py <outputs_dir> <leaflet_css_path> <out_html>
"""
import json, sys

outdir, css_path, out_html = sys.argv[1], sys.argv[2], sys.argv[3]
def rd(p): return open(f"{outdir}/{p}").read()
lake = rd("lake.geojson"); zones = rd("zones.geojson")
premises = rd("premises.geojson"); nodes = rd("proposed_nodes.geojson")
leaflet_css = open(css_path).read()

# headline stats (kept in sync with the analysis)
STATS = dict(premises=9571, shore=6144, zones=18, nodes=30, cov_pct=84,
             los=8279, median=410288, over1m=522)

HTML = f"""<title>Beaver Lake Network Map</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
{leaflet_css}
:root{{
  --bg:#e9eef0; --panel:#ffffffdd; --panel-solid:#ffffff; --ink:#122029; --muted:#5a6b75;
  --line:#c9d6db; --water:#bfe0e6; --water-edge:#4f9aa6;
  --cov:#0e7c8b; --shadow:#e07a34; --node:#12222c; --node-ring:#f2b705;
  --p1:#c94b4b; --p2:#e08a3c; --p3:#3f8fa6; --p4:#8797a0; --accent:#0e7c8b;
}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --bg:#0c151b; --panel:#11202ad9; --panel-solid:#11202a; --ink:#e6eef2; --muted:#8fa3ad;
  --line:#25363f; --water:#123038; --water-edge:#3d7f8c;
  --cov:#2bb3c4; --shadow:#f0904a; --node:#0a1319; --node-ring:#f2b705;
}}}}
:root[data-theme="dark"]{{
  --bg:#0c151b; --panel:#11202ad9; --panel-solid:#11202a; --ink:#e6eef2; --muted:#8fa3ad;
  --line:#25363f; --water:#123038; --water-edge:#3d7f8c;
  --cov:#2bb3c4; --shadow:#f0904a; --node:#0a1319; --node-ring:#f2b705;
}}
*{{box-sizing:border-box}}
html,body{{height:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;}}
#map{{position:absolute;inset:0;background:var(--bg)}}
.leaflet-container{{background:var(--bg);font-family:inherit}}
.mono{{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}}
.bar{{position:absolute;z-index:1000;top:env(safe-area-inset-top,0px);left:0;right:0;
  display:flex;gap:14px;align-items:center;flex-wrap:wrap;
  padding:10px 16px;background:var(--panel);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line)}}
.bar h1{{font-size:15px;font-weight:700;margin:0;letter-spacing:.02em;white-space:nowrap}}
.bar .sub{{font-size:11px;color:var(--muted);margin-top:1px}}
.chips{{display:flex;gap:8px;flex-wrap:wrap;margin-left:auto}}
.chip{{background:var(--panel-solid);border:1px solid var(--line);border-radius:8px;
  padding:4px 9px;line-height:1.15;min-width:64px}}
.chip b{{display:block;font-size:14px}}.chip span{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
.panel{{position:absolute;z-index:1000;left:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px));
  width:230px;max-width:calc(100vw - 32px);background:var(--panel);backdrop-filter:blur(8px);
  border:1px solid var(--line);border-radius:12px;padding:12px 13px;font-size:12px}}
.panel h2{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 8px}}
.row{{display:flex;align-items:center;gap:8px;padding:3px 0;cursor:pointer;user-select:none}}
.row input{{accent-color:var(--accent)}}
.sw{{width:12px;height:12px;border-radius:3px;flex:0 0 auto;border:1px solid #0003}}
.dot{{width:10px;height:10px;border-radius:50%;flex:0 0 auto}}
.leaflet-popup-content{{font-size:12px;margin:10px 12px;line-height:1.45}}
.leaflet-popup-content h3{{margin:0 0 4px;font-size:13px}}
.leaflet-popup-content .mono{{color:var(--muted)}}
.nodeMk{{background:var(--node);color:#fff;border:2px solid var(--node-ring);border-radius:50%;
  width:22px;height:22px;display:flex;align-items:center;justify-content:center;
  font-size:11px;font-weight:600;font-family:"IBM Plex Mono",monospace;box-shadow:0 1px 4px #0006}}
.foot{{margin-top:9px;padding-top:8px;border-top:1px solid var(--line);color:var(--muted);font-size:10px}}
@media (max-width:560px){{.panel{{width:calc(100vw - 32px)}} .bar h1{{font-size:14px}}}}
</style>

<div id="map"></div>
<div class="bar">
  <div>
    <h1>Beaver Lake Network</h1>
    <div class="sub mono">premises-passed &amp; node siting · NHD + AR GIS + 3DEP viewshed</div>
  </div>
  <div class="chips mono">
    <div class="chip"><b>{STATS['premises']:,}</b><span>premises ≤1mi</span></div>
    <div class="chip"><b>{STATS['shore']:,}</b><span>≤¼mi shore</span></div>
    <div class="chip"><b>{STATS['zones']}</b><span>zones</span></div>
    <div class="chip"><b>{STATS['nodes']}→{STATS['cov_pct']}%</b><span>nodes cover</span></div>
    <div class="chip"><b>${STATS['median']//1000}k</b><span>median home</span></div>
  </div>
</div>

<div class="panel">
  <h2>Layers</h2>
  <label class="row"><input type="checkbox" id="t-zones" checked><span class="sw" style="background:#3f8fa6aa"></span>Service zones (18)</label>
  <label class="row"><input type="checkbox" id="t-cov" checked><span class="dot" style="background:var(--cov)"></span>Premises — LOS covered</label>
  <label class="row"><input type="checkbox" id="t-shadow" checked><span class="dot" style="background:var(--shadow)"></span>Premises — RF shadow</label>
  <label class="row"><input type="checkbox" id="t-nodes" checked><span class="dot" style="background:var(--node-ring)"></span>Proposed nodes (30)</label>
  <div class="foot">Zone fill = build phase (1 darkest → 4). Click any feature for detail.
  Shadow premises (~13%) need relays or fiber.</div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const LAKE={lake};
const ZONES={zones};
const PREM={premises};
const NODES={nodes};
const cssv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const phaseColor=p=>({{1:cssv('--p1'),2:cssv('--p2'),3:cssv('--p3'),4:cssv('--p4')}}[p]||cssv('--p4'));
const map=L.map('map',{{preferCanvas:true,zoomControl:true,attributionControl:false}});
const canvas=L.canvas({{padding:0.5}});

const lakeLayer=L.geoJSON(LAKE,{{style:{{color:cssv('--water-edge'),weight:1,fillColor:cssv('--water'),fillOpacity:1}}}}).addTo(map);

const zoneLayer=L.geoJSON(ZONES,{{style:f=>({{color:phaseColor(f.properties.phase||4),weight:1.3,
  fillColor:phaseColor(f.properties.phase||4),fillOpacity:.14}}),
  onEachFeature:(f,l)=>{{const p=f.properties;l.bindPopup(
    `<h3>${{p.name}} <span class="mono">${{p.zone_id}}</span></h3>
     <div class="mono">${{p.county}} County · phase ${{p.phase||'—'}}</div>
     <div><b>${{(p.premises||0).toLocaleString()}}</b> premises · ${{p.commercial||0}} commercial</div>
     <div class="mono">median $${{(p.median_value||0).toLocaleString()}} · ${{p.over_1m||0}} homes &gt;$1M</div>`);}}}}).addTo(map);

function premLayer(covered){{
  return L.geoJSON(PREM,{{filter:f=>!!f.properties.los===covered,
    pointToLayer:(f,ll)=>L.circleMarker(ll,{{renderer:canvas,radius:1.7,
      color:covered?cssv('--cov'):cssv('--shadow'),weight:0,
      fillColor:covered?cssv('--cov'):cssv('--shadow'),fillOpacity:.8}})}});
}}
const covLayer=premLayer(true).addTo(map);
const shadowLayer=premLayer(false).addTo(map);

const nodeLayer=L.geoJSON(NODES,{{pointToLayer:(f,ll)=>L.marker(ll,{{icon:L.divIcon({{
    className:'',html:`<div class="nodeMk">${{f.properties.priority}}</div>`,
    iconSize:[22,22],iconAnchor:[11,11]}})}}),
  onEachFeature:(f,l)=>{{const p=f.properties;l.bindPopup(
    `<h3>Node #${{p.priority}} <span class="mono">${{p.zone}}</span></h3>
     <div class="mono">${{p.elev_ft}} ft · ${{p.primary?'zone anchor':'fill site'}}</div>
     <div>sees <b>${{(p.vis8km||0).toLocaleString()}}</b> premises ≤8km · <b>+${{p.new}}</b> new</div>
     <div class="mono">${{p.site}}</div>
     <div class="mono">owner: ${{(p.owner||'—')}}</div>`);}}}}).addTo(map);

map.fitBounds(lakeLayer.getBounds(),{{padding:[24,24]}});
const bind=(id,layer)=>document.getElementById(id).addEventListener('change',e=>{{
  e.target.checked?map.addLayer(layer):map.removeLayer(layer);}});
bind('t-zones',zoneLayer);bind('t-cov',covLayer);bind('t-shadow',shadowLayer);bind('t-nodes',nodeLayer);
</script>
"""
open(out_html,"w").write(HTML)
print(f"wrote {out_html} ({len(HTML)//1024} KB)")
