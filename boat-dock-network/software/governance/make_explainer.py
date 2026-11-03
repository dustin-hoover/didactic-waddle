#!/usr/bin/env python3
"""Self-contained governance explainer (inline SVG, no CDN). Reads tokenomics_sim.csv.
Usage: python3 make_explainer.py <out_html>"""
import csv, os, sys
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sim = list(csv.DictReader(open(os.path.join(REPO, "data", "financial", "tokenomics_sim.csv"))))
def at(m): return next(r for r in sim if int(r["month"]) == m)
yrs = [1,2,3,4,5,6,7,8]; ym = {y: at(y*12) for y in yrs}
out_html = sys.argv[1]

W,H,PL,PR,PT,PB = 100,58,12,3,5,8
def Xb(i,n): return PL+(W-PL-PR)*(i+0.5)/n
def Xl(i,n): return PL+(W-PL-PR)*(i/(n-1 if n>1 else 1))
def syf(v,lo,hi): return (H-PB)-(H-PB-PT)*(v-lo)/(hi-lo if hi!=lo else 1)
def grid(lo,hi,fmt):
    o=[]
    for t in range(5):
        v=lo+(hi-lo)*t/4; yy=syf(v,lo,hi)
        o.append(f'<line x1="{PL}" y1="{yy:.2f}" x2="{W-PR}" y2="{yy:.2f}" class="g"/>')
        o.append(f'<text x="{PL-1.2}" y="{yy+1:.1f}" class="yt">{fmt(v)}</text>')
    return "".join(o)
def xlab(labels):
    n=len(labels); return "".join(f'<text x="{Xb(i,n):.2f}" y="{H-1.5}" class="xt">{labels[i]}</text>' for i in range(n))
def svg(inner): return f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" role="img">{inner}</svg>'

# Chart A: stacked area circulating (active_units) + pool = total, over years
circ=[int(ym[y]["active_units"]) for y in yrs]; pool=[int(ym[y]["pool"]) for y in yrs]
tot=[circ[i]+pool[i] for i in range(len(yrs))]; hiA=max(tot)*1.08; n=len(yrs)
def areaPoly(vals_top, vals_bot, color):
    pts_top=[(Xl(i,n),syf(vals_top[i],0,hiA)) for i in range(n)]
    pts_bot=[(Xl(i,n),syf(vals_bot[i],0,hiA)) for i in range(n)]
    d=" ".join(f"{x:.2f},{y:.2f}" for x,y in pts_top)+" "+" ".join(f"{x:.2f},{y:.2f}" for x,y in reversed(pts_bot))
    return f'<polygon points="{d}" fill="{color}" fill-opacity="0.85"/>'
cum_bot=[0]*n; cum_top=circ[:]
chartA=svg(grid(0,hiA,lambda v:f"{v/1000:.0f}k")
    + areaPoly([circ[i] for i in range(n)],[0]*n,"var(--s1)")
    + areaPoly([circ[i]+pool[i] for i in range(n)],[circ[i] for i in range(n)],"var(--s2)")
    + "".join(f'<circle cx="{Xl(i,n):.2f}" cy="{syf(tot[i],0,hiA):.2f}" r="0.8" fill="var(--ink)"><title>Y{yrs[i]}: {tot[i]:,} total WAKE</title></circle>' for i in range(n))
    + xlab([f"Y{y}" for y in yrs]))

# Chart B: founding-cohort vote share (declining)
fs=[float(ym[y]["founding_share"]) for y in yrs];
chartB=svg(grid(0,100,lambda v:f"{v:.0f}%")
    + '<polyline points="'+" ".join(f"{Xl(i,n):.2f},{syf(fs[i],0,100):.2f}" for i in range(n))+'" fill="none" stroke="var(--s2)" stroke-width="0.8"/>'
    + "".join(f'<circle cx="{Xl(i,n):.2f}" cy="{syf(fs[i],0,100):.2f}" r="0.9" fill="var(--s2)"><title>Y{yrs[i]}: {fs[i]}%</title></circle>' for i in range(n))
    + "".join(f'<text x="{Xl(i,n):.2f}" y="{syf(fs[i],0,100)-2:.1f}" class="dl">{fs[i]:.0f}%</text>' for i in (0,3,7))
    + xlab([f"Y{y}" for y in yrs]))

# Chart C: voting weight curve (bars)
ten=[("1mo",2),("6mo",7),("1yr",13),("2yr",25),("5yr",61),("10yr",121),("15yr",121)]
hiC=130; n2=len(ten); bw=(W-PL-PR)/n2*0.6
chartC=svg(grid(0,hiC,lambda v:f"{v:.0f}")
    + "".join(f'<rect x="{Xb(i,n2)-bw/2:.2f}" y="{syf(v,0,hiC):.2f}" width="{bw:.2f}" height="{(H-PB)-syf(v,0,hiC):.2f}" rx="0.6" fill="var(--s1)"><title>{lab}: {v} votes</title></rect>' for i,(lab,v) in enumerate(ten))
    + "".join(f'<text x="{Xb(i,n2):.2f}" y="{syf(v,0,hiC)-1:.1f}" class="dl">{v}</text>' for i,(lab,v) in enumerate(ten))
    + xlab([t[0] for t in ten]))

def leg(items): return '<div class="lg">'+"".join(f'<span><i style="background:{c}"></i>{t}</span>' for t,c in items)+'</div>'
t8=ym[8]
HTML=f"""<title>WAKE Cooperative Governance</title>
<style>
:root{{--bg:#eef1f2;--surface:#fff;--ink:#0b0b0b;--muted:#52514e;--line:#dfe4e6;--g:#e7e7e2;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0c0f10;--surface:#16191a;--ink:#f3f5f5;--muted:#c3c2b7;--line:#2a2f30;--g:#282d2e;--s1:#3987e5;--s2:#d95926;--s3:#199e70;}}}}
:root[data-theme="dark"]{{--bg:#0c0f10;--surface:#16191a;--ink:#f3f5f5;--muted:#c3c2b7;--line:#2a2f30;--g:#282d2e;--s1:#3987e5;--s2:#d95926;--s3:#199e70;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:max(16px,env(safe-area-inset-top)) 16px 28px}}
.wrap{{max-width:1000px;margin:0 auto}} h1{{margin:0 0 2px;font-size:22px}} .sub{{color:var(--muted);font-size:13px;margin:0 0 14px;font-family:ui-monospace,Menlo,monospace}}
.tiles{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:14px}}
.tile{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 12px}}
.tile b{{display:block;font-size:18px;font-variant-numeric:tabular-nums}} .tile span{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
.rail{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:13px 15px}}
.card h3{{margin:0 0 6px;font-size:14px}} .card p{{margin:4px 0;font-size:12.5px;color:var(--muted);line-height:1.5}}
.badge{{display:inline-block;font-size:10px;padding:2px 7px;border-radius:20px;font-weight:600;margin-bottom:4px}}
.gov{{background:#2a78d622;color:var(--s1)}} .eco{{background:#1baf7a22;color:var(--s3)}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
figure{{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px 14px}}
figcaption{{font-size:13px;font-weight:600}} .cap{{font-size:11px;color:var(--muted);margin-bottom:4px}}
svg{{width:100%;height:auto;display:block;overflow:visible}} .g{{stroke:var(--g);stroke-width:.2}}
.yt{{font-size:2.4px;fill:var(--muted);text-anchor:end}} .xt{{font-size:2.7px;fill:var(--muted);text-anchor:middle}} .dl{{font-size:2.7px;fill:var(--ink);text-anchor:middle;font-variant-numeric:tabular-nums}}
.lg{{display:flex;gap:14px;font-size:12px;color:var(--muted);margin-top:6px}} .lg i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}}
.flow{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px;margin-top:6px}}
.step{{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:6px 9px}} .arw{{color:var(--muted)}}
.note{{color:var(--muted);font-size:11.5px;line-height:1.5;margin-top:14px;border-top:1px solid var(--line);padding-top:10px}}
@media (max-width:780px){{.tiles{{grid-template-columns:repeat(3,1fr)}} .rail,.grid2{{grid-template-columns:1fr}}}}
</style>
<div class="wrap">
<h1>WAKE — Cooperative Governance</h1>
<p class="sub">Boat Dock Network · earn 1 WAKE per month of membership · non-transferable · tenure-weighted voting</p>
<div class="tiles">
  <div class="tile"><b>1 / mo</b><span>WAKE per member</span></div>
  <div class="tile"><b>1.5&times;</b><span>host-node accrual</span></div>
  <div class="tile"><b>120</b><span>vote cap (10 yr)</span></div>
  <div class="tile"><b>50% / yr</b><span>pool redistributed</span></div>
  <div class="tile"><b>100&rarr;11%</b><span>founder vote share Y1&rarr;Y8</span></div>
  <div class="tile"><b>{int(t8['total_units']):,}</b><span>total WAKE by Y8</span></div>
</div>

<div class="rail">
  <div class="card"><span class="badge gov">GOVERNANCE RAIL</span>
    <h3>WAKE units &mdash; voice, not value</h3>
    <p>Earned by loyalty (1/month, 1.5&times; for host-nodes). <b>Non-transferable</b> &mdash;
    can't be bought or sold, has no price. It is your vote weight and a public record of
    tenure. Because it can't be traded and pays no dividend, it isn't a security.</p>
    <div class="flow"><span class="step">Stay a member</span><span class="arw">&rarr;</span>
      <span class="step">+1 WAKE/mo</span><span class="arw">&rarr;</span>
      <span class="step">more voting weight</span></div>
    <div class="flow"><span class="step">Leave</span><span class="arw">&rarr;</span>
      <span class="step">WAKE &rarr; Commons Pool</span><span class="arw">&rarr;</span>
      <span class="step">50%/yr back to active members</span></div>
  </div>
  <div class="card"><span class="badge eco">ECONOMICS RAIL</span>
    <h3>Patronage dividends &mdash; the money part</h3>
    <p>Members share surplus the way electric &amp; telephone co-ops have for a century:
    <b>patronage dividends</b> allocated by how much service you buy, paid as cash or bill
    credit. Kept <b>separate</b> from WAKE on purpose &mdash; that separation is what keeps
    the token clear of securities law while members still share in success.</p>
    <div class="flow"><span class="step">Co-op earns surplus</span><span class="arw">&rarr;</span>
      <span class="step">members vote split</span><span class="arw">&rarr;</span>
      <span class="step">dividend + reinvest</span></div>
  </div>
</div>

<div class="grid2">
  <figure><figcaption>WAKE supply grows as the co-op matures</figcaption>
    <div class="cap">Circulating (active members) + Commons Pool. Lapsed influence recycles back.</div>{chartA}
    {leg([("Circulating WAKE","var(--s1)"),("Commons Pool","var(--s2)")])}</figure>
  <figure><figcaption>Power decentralizes over time</figcaption>
    <div class="cap">Founding cohort's share of total votes &mdash; falls as new members join &amp; accrue.</div>{chartB}</figure>
</div>
<figure style="margin-top:12px"><figcaption>Voting weight by tenure (linear, capped at 10 years)</figcaption>
  <div class="cap">weight = 1 + min(months, 120). Loyalty is voice; the cap prevents entrenchment. Anti-whale: no member exceeds 2% of total at tally.</div>{chartC}</figure>

<p class="note"><b>Not legal advice.</b> This is a mechanism design; a securities + cooperative
attorney must review before launch (see docs/16). Launches off-chain (DockOS ledger + Snapshot
voting); optional non-transferable on-chain mirror later. Numbers from
<span style="font-family:ui-monospace,monospace">software/governance/tokenomics_sim.py</span> on the verified subscriber curve.</p>
</div>
"""
open(out_html,"w").write(HTML)
print(f"wrote {out_html} ({len(HTML)//1024} KB)")
