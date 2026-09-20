#!/usr/bin/env python3
"""Self-contained dual-purpose (investor + grant) slide deck for Boat Dock Network.
Inline SVG charts + embedded map (data URI). No CDN, no web fonts. Vertical
scroll-snap slides with keyboard/click nav. Reads the verified model + sim data.

Usage: python3 make_deck.py <out_html>
"""
import base64, csv, json, os, sys
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIN = os.path.join(REPO, "data", "financial")
S = json.load(open(os.path.join(FIN, "model_summary.json")))
Y = S["years"]; yl = [f"Y{y}" for y in Y]
def arr(d): return [d[str(y)] if str(y) in d else d[y] for y in Y]
rev, opex, ebit = arr(S["revenue"]), arr(S["opex"]), arr(S["ebitda"])
capex, cfc = arr(S["capex"]), arr(S["cf_cum"])
infra, conn = [], []
for r in csv.reader(open(os.path.join(FIN, "capex_detail.csv"))):
    if r[0] == "network_infrastructure": infra = [int(x) for x in r[1:6]]
    if r[0] == "subscriber_connections": conn = [int(x) for x in r[1:6]]
sim = list(csv.DictReader(open(os.path.join(FIN, "tokenomics_sim.csv"))))
def simat(m): return next(r for r in sim if int(r["month"]) == m)
wake_yr = [int(simat(y*12)["total_units"]) for y in Y]
mapb64 = base64.b64encode(open(os.path.join(os.path.dirname(__file__), "map.png"), "rb").read()).decode()

# ---- SVG chart helpers (viewBox 100x54) ----
W,H,PL,PR,PT,PB = 100,54,12,3,5,8
def Xl(i,n): return PL+(W-PL-PR)*(i/(n-1 if n>1 else 1))
def Xb(i,n): return PL+(W-PL-PR)*(i+0.5)/n
def syf(v,lo,hi): return (H-PB)-(H-PB-PT)*(v-lo)/(hi-lo if hi!=lo else 1)
def gridlines(lo,hi,fmt):
    o=[]
    for t in range(5):
        v=lo+(hi-lo)*t/4; yy=syf(v,lo,hi)
        o.append(f'<line x1="{PL}" y1="{yy:.2f}" x2="{W-PR}" y2="{yy:.2f}" class="g"/>')
        o.append(f'<text x="{PL-1.2}" y="{yy+1:.1f}" class="yt">{fmt(v)}</text>')
    return "".join(o)
def xlab(labs):
    n=len(labs); return "".join(f'<text x="{Xb(i,n):.2f}" y="{H-1.5}" class="xt">{labs[i]}</text>' for i in range(n))
def svg(inner): return f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" role="img">{inner}</svg>'

# cash-flow J-curve
lo=min(cfc)*1.1; hi=max(max(cfc)*1.5,300); n=len(cfc); z=syf(0,lo,hi)
pts=" ".join(f"{Xl(i,n):.2f},{syf(v,lo,hi):.2f}" for i,v in enumerate(cfc))
chart_cash=svg(gridlines(lo,hi,lambda v:f"${v/1000:.1f}M")
  +f'<line x1="{PL}" y1="{z:.2f}" x2="{W-PR}" y2="{z:.2f}" class="zero"/>'
  +f'<polygon points="{PL},{z:.2f} {pts} {Xl(n-1,n):.2f},{z:.2f}" fill="var(--s1)" fill-opacity="0.14"/>'
  +f'<polyline points="{pts}" fill="none" stroke="var(--s1)" stroke-width="0.8"/>'
  +"".join(f'<circle cx="{Xl(i,n):.2f}" cy="{syf(v,lo,hi):.2f}" r="0.9" fill="var(--s1)"><title>{yl[i]}: ${v:,}k</title></circle>' for i,v in enumerate(cfc))
  +"".join(f'<text x="{Xl(i,n):.2f}" y="{syf(v,lo,hi)+(-2 if v>=0 else 3):.1f}" class="dl">${v/1000:.1f}M</text>' for i,v in enumerate(cfc))
  +xlab(yl))
# CapEx stacked
tot=[infra[i]+conn[i] for i in range(len(infra))]; hi2=max(tot)*1.12; n=len(tot); bw=(W-PL-PR)/n*0.5
def stack(i):
    x=Xb(i,n)-bw/2; y0=H-PB; segs=[]
    for v,c,nm in [(infra[i],"var(--s1)","Infrastructure"),(conn[i],"var(--s3)","Connections")]:
        h=(H-PB-PT)*v/hi2; y=y0-h
        segs.append(f'<rect x="{x:.2f}" y="{y+0.2:.2f}" width="{bw:.2f}" height="{max(h-0.4,0):.2f}" rx="0.5" fill="{c}"><title>{nm} {yl[i]}: ${v:,}k</title></rect>'); y0=y
    segs.append(f'<text x="{Xb(i,n):.2f}" y="{y0-1:.1f}" class="dl">${tot[i]/1000:.1f}M</text>')
    return "".join(segs)
chart_capex=svg(gridlines(0,hi2,lambda v:f"${v/1000:.1f}M")+"".join(stack(i) for i in range(n))+xlab(yl))
# WAKE supply
hi3=max(wake_yr)*1.08; n=len(wake_yr)
wpts=" ".join(f"{Xl(i,n):.2f},{syf(v,0,hi3):.2f}" for i,v in enumerate(wake_yr))
chart_wake=svg(gridlines(0,hi3,lambda v:f"{v/1000:.0f}k")
  +f'<polygon points="{PL},{syf(0,0,hi3):.2f} {wpts} {Xl(n-1,n):.2f},{syf(0,0,hi3):.2f}" fill="var(--s2)" fill-opacity="0.16"/>'
  +f'<polyline points="{wpts}" fill="none" stroke="var(--s2)" stroke-width="0.8"/>'
  +"".join(f'<circle cx="{Xl(i,n):.2f}" cy="{syf(v,0,hi3):.2f}" r="0.9" fill="var(--s2)"><title>{yl[i]}: {v:,} WAKE</title></circle>' for i,v in enumerate(wake_yr))
  +xlab(yl))

def tiles(items): return '<div class="tiles">'+"".join(f'<div class="tile"><b>{v}</b><span>{k}</span></div>' for v,k in items)+'</div>'

cap5=S['capex_5y_000']/1000; peak=S['peak_funding_need_000']/1000
SL = []
# 1 title
SL.append(f"""<section class="slide title"><div>
  <div class="kicker">Community-owned gigabit for Beaver Lake, Arkansas</div>
  <h1>Boat Dock Network</h1>
  <p class="lede">A member cooperative delivering fiber-and-wireless gigabit to every home,
  business, and marina on the lake — built, served, and repaired by boat.</p>
  <div class="pill-row"><span class="pill">{S['premises_total']:,} premises in reach</span>
   <span class="pill">~${cap5:.1f}M to build the whole lake</span>
   <span class="pill">EBITDA-positive Year {S['ebitda_positive_year']}</span></div>
  <div class="foot-note">Verified from public GIS · planning-grade financials · seeking blended grant + debt + member capital</div>
</div></section>""")
# 2 problem
SL.append(f"""<section class="slide"><div>
  <div class="kicker">The problem</div>
  <h2>The shoreline is the gap incumbents skip</h2>
  <p class="lede">Cable and telco built for towns, not for 445 miles of coves and fingers.
  Lakeshore homes and marinas are stuck with slow DSL, spotty cellular, or costly satellite —
  even as remote work and vacation rentals boom in Northwest Arkansas.</p>
  {tiles([("445 mi","shoreline underserved"),("3","counties on the lake"),("Weak","incumbent options on the water"),("Rising","demand: remote work + STRs")])}
</div></section>""")
# 3 market
SL.append(f"""<section class="slide"><div>
  <div class="kicker">The market — verified, not estimated</div>
  <h2>9,571 premises within a mile of the water</h2>
  {tiles([(f"{S['premises_total']:,}","premises ≤1 mi"),("6,144","≤¼ mi shoreline"),("$410k","median home value"),("522","homes over $1M"),("~162","marinas/resorts/biz"),("5,943","vacant lots (growth)")])}
  <p class="src">Source: USGS NHD shoreline + Arkansas GIS / Benton County parcels (improved parcels = premises).
  County split: Benton 7,190 · Washington 1,318 · Carroll 1,044 · Madison 19.</p>
</div></section>""")
# 4 solution
SL.append(f"""<section class="slide"><div>
  <div class="kicker">The solution</div>
  <h2>Hybrid network, lake as the highway</h2>
  <div class="two">
    <ul class="ticks"><li><b>Fiber</b> where density pays; <b>non-line-of-sight wireless</b> (Tarana) that punches through Ozark tree cover everywhere else.</li>
      <li>A redundant <b>microwave spine crosses the lake</b> — no need to trench around every cove.</li>
      <li><b>Boat-native operations:</b> nodes on docks and shoreline high points, installs and repairs by water.</li>
      <li><b>Host-node program:</b> members who host a node extend coverage and earn rewards.</li></ul>
    <div class="stat-callout"><b>75%</b><span>of premises reachable by wireless line-of-sight through foliage; the rest by fiber/relay</span></div>
  </div>
</div></section>""")
# 5 network + map
SL.append(f"""<section class="slide"><div>
  <div class="kicker">The engineered network</div>
  <h2>Already designed to the parcel</h2>
  <div class="two">
    <img class="map" alt="Beaver Lake network map" src="data:image/png;base64,{mapb64}"/>
    <div>{tiles([("18","service zones"),("30","nodes (viewshed-ranked)"),("41","spine hops / 140 km"),("75%","wireless LOS (foliage)")])}
    <p class="src">Zones, nodes, backbone spine, and per-premises serviceability computed in PostGIS from
    LiDAR/3DEP + canopy modeling. Build order is demand- and cost-ranked.</p></div>
  </div>
</div></section>""")
# 6 moat
SL.append(f"""<section class="slide"><div>
  <div class="kicker">Why us — the moat</div>
  <h2>Advantages an overbuilder can't copy</h2>
  {tiles([("Lake ROW","boat build + service = lower cost/faster"),("nLOS + fiber","reaches premises others skip"),("Host-node","flywheel: coverage + loyalty"),("Co-op trust","the lake owns its network"),("Software-run","low OpEx per subscriber"),("First mover","one engineered system for the whole lake")])}
</div></section>""")
# 7 co-op / WAKE
SL.append(f"""<section class="slide"><div>
  <div class="kicker">Ownership — a member cooperative</div>
  <h2>The community owns it, and governs it</h2>
  <div class="two">
    <ul class="ticks"><li><b>WAKE governance units:</b> earn 1 per month of membership (1.5× for host-nodes), <b>non-transferable</b> — voice, not a tradable security.</li>
      <li><b>Patronage dividends</b> share surplus the classic co-op way — kept separate from WAKE so the token stays clear of securities law.</li>
      <li>Leavers' units recycle to a Commons Pool and redistribute — power <b>decentralizes over time</b> (founding share 100%→11% by Y8).</li></ul>
    <div>{chart_wake}<div class="cap">Total WAKE in circulation grows as the co-op matures</div></div>
  </div>
  <p class="src">Governance-only design; securities + cooperative counsel review required before launch.</p>
</div></section>""")
# 8 model
SL.append(f"""<section class="slide"><div>
  <div class="kicker">Business model</div>
  <h2>Simple, symmetric, premium-friendly</h2>
  <div class="price-row">
    <div class="price"><b>Cove</b><span>300 Mbps</span><em>$69/mo</em></div>
    <div class="price hi"><b>Shoreline</b><span>1 Gbps</span><em>$89/mo</em></div>
    <div class="price"><b>Deep Water</b><span>2–5 Gbps</span><em>$129–199</em></div>
    <div class="price"><b>Business / Marina</b><span>1 Gbps – multi-gig</span><em>$199–1,200</em></div>
  </div>
  {tiles([("$105","blended ARPU / mo"),("44%","ultimate take rate"),("~$1,769","all-in cost / subscriber"),("~2.0 yr","payback per subscriber")])}
</div></section>""")
# 9 financials
SL.append(f"""<section class="slide"><div>
  <div class="kicker">Financials — verified pro forma (foliage base case)</div>
  <h2>${cap5:.1f}M builds the whole lake; EBITDA-positive Year {S['ebitda_positive_year']}</h2>
  <div class="two">
    <div>{chart_cash}<div class="cap">Cumulative cash (pre-financing): peak need ${peak:.1f}M, then climbs</div></div>
    <div>{chart_capex}<div class="cap">CapEx: infrastructure (incl. $1.37M spine) + subscriber connections</div></div>
  </div>
  {tiles([(f"${cap5:.1f}M","5-yr CapEx"),(f"${peak:.1f}M","peak funding need"),(f"${S['cost_per_passing']}","cost / passing"),("$5.4M","Year-5 revenue")])}
</div></section>""")
# 10 ask
SL.append(f"""<section class="slide"><div>
  <div class="kicker">The ask — blended capital</div>
  <h2>~$3.5M to build and reach cash-flow positive</h2>
  <div class="two">
    <ul class="ticks"><li><b>Grants (BEAD / USDA / AR state):</b> target the high-cost RF-shadow &amp; long-tail zones — non-dilutive.</li>
      <li><b>Low-interest telecom debt (RUS / CoBank / RTFC):</b> the bulk of infrastructure CapEx.</li>
      <li><b>Member + owner capital:</b> first-in risk capital and grant match.</li></ul>
    <div class="stat-callout"><b>${peak:.1f}M</b><span>peak funding need (pre-grants); ~40% grant coverage cuts equity/debt to ~$1.5–2M</span></div>
  </div>
</div></section>""")
# 11 grant fit
SL.append(f"""<section class="slide"><div>
  <div class="kicker">For grant reviewers</div>
  <h2>Built for BEAD / USDA / state scoring</h2>
  {tiles([("Unserved","mapped, parcel-level evidence"),("Symmetric gig","exceeds program thresholds"),("Co-op","local, community-owned"),("Match ready","blended stack + owner capital"),("Whole-lake","coherent, phased buildout"),("Compliance","BABA + segregated accounting planned")])}
  <p class="src">GIS coverage maps, per-zone cost-per-passing, and community-benefit narrative are already produced (docs 05, 13).</p>
</div></section>""")
# 12 roadmap
SL.append(f"""<section class="slide"><div>
  <div class="kicker">Roadmap</div>
  <h2>Phased by demand and cost</h2>
  <div class="road">
    <div class="ph"><b>Phase 1 · Y1</b><span>Prairie Creek, Beaver Shores, Monte Ne — pilot + first lake crossing (3,341 premises)</span></div>
    <div class="ph"><b>Phase 2 · Y2</b><span>Central Benton corridor (2,957) — close grants + debt</span></div>
    <div class="ph"><b>Phase 3 · Y3</b><span>Ring closure + Carroll/Washington zones (1,933)</span></div>
    <div class="ph"><b>Phase 4 · Y4–5</b><span>Long-tail coves, demand-gated (1,340); fiber overbuild of densest zones</span></div>
  </div>
</div></section>""")
# 13 close
SL.append(f"""<section class="slide title"><div>
  <div class="kicker">The opportunity</div>
  <h1>The lake's own internet</h1>
  <p class="lede">A verified {S['premises_total']:,}-premises market, an engineered network, a
  fundable ~${cap5:.1f}M plan, and a cooperative that makes every member an owner.</p>
  <div class="pill-row"><span class="pill">Let's build it together</span></div>
  <div class="foot-note">Boat Dock Network · Beaver Lake, Arkansas · planning-grade; figures to be firmed with quotes, counsel &amp; pilot actuals</div>
</div></section>""")

slides = "\n".join(SL); nslides = len(SL)
HTML=f"""<title>Boat Dock Network Deck</title>
<style>
:root{{--bg:#eef1f2;--surface:#fff;--ink:#0b0b0b;--muted:#52514e;--line:#dfe4e6;--g:#e7e7e2;--zero:#9aa3a7;
 --s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--accent:#0e7c8b;}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0c0f10;--surface:#14181a;--ink:#f3f5f5;--muted:#c3c2b7;--line:#242a2b;--g:#242a2b;--zero:#5b6466;--s1:#3987e5;--s2:#d95926;--s3:#199e70;}}}}
:root[data-theme="dark"]{{--bg:#0c0f10;--surface:#14181a;--ink:#f3f5f5;--muted:#c3c2b7;--line:#242a2b;--g:#242a2b;--zero:#5b6466;--s1:#3987e5;--s2:#d95926;--s3:#199e70;}}
*{{box-sizing:border-box}} html,body{{height:100%;margin:0}}
body{{background:var(--bg);color:var(--ink);font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
.deck{{height:100%;overflow-y:scroll;scroll-snap-type:y mandatory;scroll-behavior:smooth}}
.slide{{min-height:100%;scroll-snap-align:start;display:flex;align-items:center;justify-content:center;
 padding:calc(40px + env(safe-area-inset-top)) 24px 56px;border-bottom:1px solid var(--line)}}
.slide>div{{width:100%;max-width:940px}}
.kicker{{font-family:ui-monospace,Menlo,monospace;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin-bottom:10px}}
h1{{font-size:clamp(32px,6vw,60px);line-height:1.02;margin:0 0 14px;letter-spacing:-.02em;text-wrap:balance}}
h2{{font-size:clamp(24px,4vw,38px);line-height:1.08;margin:0 0 18px;letter-spacing:-.01em;text-wrap:balance}}
.lede{{font-size:clamp(15px,2vw,19px);line-height:1.5;color:var(--muted);max-width:60ch;margin:0 0 18px}}
.title .lede{{color:var(--ink);opacity:.85}}
.pill-row{{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}}
.pill{{background:var(--surface);border:1px solid var(--line);border-radius:22px;padding:8px 15px;font-weight:600;font-size:14px}}
.foot-note{{margin-top:22px;color:var(--muted);font-size:12px}}
.tiles{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:6px 0}}
.tile{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px}}
.tile b{{display:block;font-size:clamp(18px,2.4vw,24px);font-variant-numeric:tabular-nums;letter-spacing:-.01em}}
.tile span{{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:center}}
.ticks{{margin:0;padding:0;list-style:none}} .ticks li{{position:relative;padding-left:22px;margin:10px 0;font-size:15px;line-height:1.45}}
.ticks li::before{{content:"";position:absolute;left:2px;top:7px;width:9px;height:9px;border-radius:50%;background:var(--s1)}}
.stat-callout{{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:22px;text-align:center}}
.stat-callout b{{display:block;font-size:44px;color:var(--s1);letter-spacing:-.02em}} .stat-callout span{{color:var(--muted);font-size:13px}}
.map{{width:100%;border-radius:12px;border:1px solid var(--line)}}
.src{{color:var(--muted);font-size:11.5px;margin-top:12px;line-height:1.5}}
.cap{{color:var(--muted);font-size:11.5px;margin-top:4px;text-align:center}}
svg{{width:100%;height:auto;display:block;overflow:visible}} .g{{stroke:var(--g);stroke-width:.2}} .zero{{stroke:var(--zero);stroke-width:.35;stroke-dasharray:1 1}}
.yt{{font-size:2.4px;fill:var(--muted);text-anchor:end}} .xt{{font-size:2.7px;fill:var(--muted);text-anchor:middle}} .dl{{font-size:2.6px;fill:var(--ink);text-anchor:middle;font-variant-numeric:tabular-nums}}
.price-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:6px 0 14px}}
.price{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px}}
.price.hi{{border-color:var(--s1);box-shadow:0 0 0 1px var(--s1)}}
.price b{{font-size:16px}} .price span{{display:block;color:var(--muted);font-size:12px;margin:2px 0 6px}} .price em{{font-style:normal;font-weight:700;font-size:18px}}
.road{{display:grid;gap:10px}} .ph{{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--s1);border-radius:10px;padding:12px 14px}}
.ph b{{font-size:14px}} .ph span{{display:block;color:var(--muted);font-size:13px;margin-top:2px}}
.nav{{position:fixed;right:16px;bottom:calc(16px + env(safe-area-inset-bottom));display:flex;gap:8px;align-items:center;z-index:10}}
.nav button{{width:38px;height:38px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:10px;font-size:17px;cursor:pointer}}
.count{{font-family:ui-monospace,monospace;font-size:12px;color:var(--muted);background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:0 10px;height:38px;display:flex;align-items:center}}
@media (max-width:760px){{.tiles{{grid-template-columns:repeat(3,1fr)}} .two,.price-row{{grid-template-columns:1fr}}}}
</style>
<div class="deck" id="deck">
{slides}
</div>
<div class="nav"><span class="count" id="count">1 / {nslides}</span>
 <button id="prev" aria-label="Previous">&#8593;</button><button id="next" aria-label="Next">&#8595;</button></div>
<script>
const deck=document.getElementById('deck'), slides=[...deck.querySelectorAll('.slide')], count=document.getElementById('count');
let idx=0;
const go=i=>{{idx=Math.max(0,Math.min(slides.length-1,i));slides[idx].scrollIntoView({{behavior:'smooth'}});}};
document.getElementById('next').onclick=()=>go(idx+1);
document.getElementById('prev').onclick=()=>go(idx-1);
addEventListener('keydown',e=>{{if(['ArrowDown','PageDown',' '].includes(e.key)){{e.preventDefault();go(idx+1);}}
 else if(['ArrowUp','PageUp'].includes(e.key)){{e.preventDefault();go(idx-1);}}}});
const io=new IntersectionObserver(es=>{{es.forEach(en=>{{if(en.isIntersecting){{idx=slides.indexOf(en.target);count.textContent=(idx+1)+' / '+slides.length;}}}});}},{{root:deck,threshold:0.6}});
slides.forEach(s=>io.observe(s));
</script>
"""
open(sys.argv[1],"w").write(HTML)
print(f"wrote {sys.argv[1]} ({len(HTML)//1024} KB, {nslides} slides)")
