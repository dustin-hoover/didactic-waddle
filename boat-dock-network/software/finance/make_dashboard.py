#!/usr/bin/env python3
"""Self-contained financial dashboard (inline SVG, no CDN, no web fonts).
Reads data/financial/model_summary.json + capex_detail.csv. Charts use CSS-variable
fills so they follow light/dark automatically; hover tooltips via native SVG <title>.

Usage: python3 make_dashboard.py <out_html>
Palette: dataviz reference categorical (blue/orange/aqua) — validated both modes.
"""
import csv, json, os, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIN = os.path.join(REPO, "data", "financial")
out_html = sys.argv[1]
S = json.load(open(os.path.join(FIN, "model_summary.json")))
Y = S["years"]; yl = [f"Y{y}" for y in Y]
def arr(d): return [d[str(y)] if str(y) in d else d[y] for y in Y]
rev, opex, ebitda = arr(S["revenue"]), arr(S["opex"]), arr(S["ebitda"])
capex, cfc = arr(S["capex"]), arr(S["cf_cum"])
passed, subs = arr(S["passed_cum"]), arr(S["subs_end"])
infra, conn = [], []
for r in csv.reader(open(os.path.join(FIN, "capex_detail.csv"))):
    if r[0] == "network_infrastructure": infra = [int(x) for x in r[1:6]]
    if r[0] == "subscriber_connections": conn = [int(x) for x in r[1:6]]

# ---------- tiny SVG chart helpers (viewBox 100x62 units; CSS scales width) ----------
W, H = 100, 62; PL, PR, PT, PB = 11, 3, 5, 8
def X(i, n): return PL + (W - PL - PR) * (i / (n - 1 if n > 1 else 1))
def Xb(i, n): return PL + (W - PL - PR) * (i + 0.5) / n
def sy(v, lo, hi): return (H - PB) - (H - PB - PT) * (v - lo) / (hi - lo if hi != lo else 1)
def fmt(v): return f"{v:,}"

def axis(lo, hi, ticks=4, money=True):
    out = []
    for t in range(ticks + 1):
        v = lo + (hi - lo) * t / ticks
        yy = sy(v, lo, hi)
        out.append(f'<line x1="{PL}" y1="{yy:.2f}" x2="{W-PR}" y2="{yy:.2f}" class="grid"/>')
        lab = (f"${v/1000:.1f}M" if money and abs(hi) >= 1000 else (f"{v:,.0f}"))
        out.append(f'<text x="{PL-1.2}" y="{yy+1:.2f}" class="ytick">{lab}</text>')
    return "".join(out)

def xlabels(n):
    return "".join(f'<text x="{Xb(i,n):.2f}" y="{H-1.5}" class="xtick">{yl[i]}</text>' for i in range(n))

def line(series, lo, hi, color, name):
    n = len(series)
    pts = " ".join(f"{X(i,n):.2f},{sy(v,lo,hi):.2f}" for i, v in enumerate(series))
    dots = "".join(
        f'<circle cx="{X(i,n):.2f}" cy="{sy(v,lo,hi):.2f}" r="0.9" fill="{color}">'
        f'<title>{name} {yl[i]}: ${v:,}k</title></circle>' for i, v in enumerate(series))
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="0.7" stroke-linejoin="round"/>{dots}'

def svg(inner, vb=f"0 0 {W} {H}"):
    return f'<svg viewBox="{vb}" preserveAspectRatio="xMidYMid meet" role="img">{inner}</svg>'

# Chart A — cumulative cash (J-curve): area + zero line, min..max padded
lo, hi = min(cfc) * 1.12, max(max(cfc) * 1.4, 300)
z = sy(0, lo, hi); n = len(cfc)
area = " ".join(f"{X(i,n):.2f},{sy(v,lo,hi):.2f}" for i, v in enumerate(cfc))
areaPoly = f'<polygon points="{PL},{z:.2f} {area} {X(n-1,n):.2f},{z:.2f}" fill="var(--s1)" fill-opacity="0.14"/>'
chartA = svg(axis(lo, hi) +
    f'<line x1="{PL}" y1="{z:.2f}" x2="{W-PR}" y2="{z:.2f}" class="zero"/>' +
    areaPoly + line(cfc, lo, hi, "var(--s1)", "Cum. cash") +
    "".join(f'<text x="{X(i,n):.2f}" y="{sy(v,lo,hi)+(-2 if v>=0 else 3):.2f}" class="dl">${v/1000:.1f}M</text>'
            for i, v in enumerate(cfc)) + xlabels(n))

# Chart B — Revenue / OpEx / EBITDA lines
lo2, hi2 = min(min(ebitda), 0) * 1.15, max(rev) * 1.08
chartB = svg(axis(lo2, hi2) +
    f'<line x1="{PL}" y1="{sy(0,lo2,hi2):.2f}" x2="{W-PR}" y2="{sy(0,lo2,hi2):.2f}" class="zero"/>' +
    line(rev, lo2, hi2, "var(--s1)", "Revenue") +
    line(opex, lo2, hi2, "var(--s2)", "OpEx") +
    line(ebitda, lo2, hi2, "var(--s3)", "EBITDA") +
    f'<text x="{X(len(rev)-1,len(rev))-0.5:.2f}" y="{sy(rev[-1],lo2,hi2)-1.4:.2f}" class="dl" text-anchor="end">Rev ${rev[-1]/1000:.1f}M</text>' +
    f'<text x="{X(len(ebitda)-1,len(ebitda))-0.5:.2f}" y="{sy(ebitda[-1],lo2,hi2)+2.6:.2f}" class="dl" text-anchor="end">EBITDA ${ebitda[-1]/1000:.1f}M</text>' +
    xlabels(len(rev)))

# Chart C — Premises passed vs Subscribers (grouped bars)
hi3 = max(passed) * 1.08; n = len(passed); bw = (W - PL - PR) / n * 0.36
def gbar(vals, off, color, name):
    o = []
    for i, v in enumerate(vals):
        x = Xb(i, n) + off; yy = sy(v, 0, hi3); h = (H - PB) - yy
        o.append(f'<rect x="{x-bw/2:.2f}" y="{yy:.2f}" width="{bw:.2f}" height="{max(h,0):.2f}" rx="0.6" fill="{color}"><title>{name} {yl[i]}: {v:,}</title></rect>')
    return "".join(o)
chartC = svg(axis(0, hi3, 4, money=False) +
    gbar(passed, -bw*0.55, "var(--s1)", "Premises passed") +
    gbar(subs, bw*0.55, "var(--s2)", "Subscribers") + xlabels(n))

# Chart D — CapEx composition (stacked infra + connection)
tot = [infra[i] + conn[i] for i in range(len(infra))]
hi4 = max(tot) * 1.12; n = len(tot); bw2 = (W - PL - PR) / n * 0.5
def stack(i):
    x = Xb(i, n) - bw2/2
    y0 = H - PB
    segs = []
    for v, c, nm in [(infra[i], "var(--s1)", "Infrastructure"), (conn[i], "var(--s3)", "Connections")]:
        h = (H - PB - PT) * v / hi4
        y = y0 - h
        segs.append(f'<rect x="{x:.2f}" y="{y+0.2:.2f}" width="{bw2:.2f}" height="{max(h-0.4,0):.2f}" rx="0.5" fill="{c}"><title>{nm} {yl[i]}: ${v:,}k</title></rect>')
        y0 = y
    segs.append(f'<text x="{Xb(i,n):.2f}" y="{y0-1:.2f}" class="dl">${tot[i]/1000:.1f}M</text>')
    return "".join(segs)
chartD = svg(axis(0, hi4, 4) + "".join(stack(i) for i in range(n)) + xlabels(n))

def leg(items):
    return '<div class="legend">' + "".join(
        f'<span><i style="background:{c}"></i>{t}</span>' for t, c in items) + '</div>'

TILES = [
    (f"{S['premises_total']:,}", "premises ≤1 mi"),
    (f"${S['capex_5y_000']/1000:.1f}M", "5-yr CapEx"),
    (f"${S['peak_funding_need_000']/1000:.1f}M", "peak funding need"),
    (f"${S['cost_per_passing']:,}", "cost / passing"),
    (f"Y{S['ebitda_positive_year']}", "EBITDA positive"),
    (f"Y{S['cash_positive_year']}", "cash-flow positive"),
]
tiles = "".join(f'<div class="tile"><b>{v}</b><span>{k}</span></div>' for v, k in TILES)

HTML = f"""<title>Boat Dock Network Pro Forma</title>
<style>
:root{{--bg:#eef1f2;--surface:#ffffff;--ink:#0b0b0b;--muted:#52514e;--line:#dfe4e6;--grid:#e7e7e2;
 --zero:#9aa3a7;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0c0f10;--surface:#16191a;
 --ink:#f3f5f5;--muted:#c3c2b7;--line:#2a2f30;--grid:#282d2e;--zero:#5b6466;--s1:#3987e5;--s2:#d95926;--s3:#199e70;}}}}
:root[data-theme="dark"]{{--bg:#0c0f10;--surface:#16191a;--ink:#f3f5f5;--muted:#c3c2b7;--line:#2a2f30;
 --grid:#282d2e;--zero:#5b6466;--s1:#3987e5;--s2:#d95926;--s3:#199e70;}}
*{{box-sizing:border-box}} html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--ink);
 font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 padding:max(16px,env(safe-area-inset-top)) 16px calc(24px + env(safe-area-inset-bottom))}}
.wrap{{max-width:1080px;margin:0 auto}}
header h1{{margin:0 0 2px;font-size:22px;letter-spacing:-.01em}}
header p{{margin:0 0 4px;color:var(--muted);font-size:13px}}
.mono{{font-variant-numeric:tabular-nums;font-family:ui-monospace,Menlo,Consolas,monospace}}
.tiles{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:16px 0 6px}}
.tile{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:11px 12px}}
.tile b{{display:block;font-size:20px;font-variant-numeric:tabular-nums;letter-spacing:-.01em}}
.tile span{{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}
figure{{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px 14px}}
figcaption{{font-size:13px;font-weight:600;margin-bottom:2px}}
.sub{{font-size:11px;color:var(--muted);margin-bottom:6px}}
svg{{width:100%;height:auto;display:block;overflow:visible}}
.grid{{stroke:var(--grid);stroke-width:0.2}} .zero{{stroke:var(--zero);stroke-width:0.35;stroke-dasharray:1 1}}
.ytick{{font-size:2.5px;fill:var(--muted);text-anchor:end}} .xtick{{font-size:2.8px;fill:var(--muted);text-anchor:middle}}
.dl{{font-size:2.7px;fill:var(--ink);text-anchor:middle;font-variant-numeric:tabular-nums}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:8px}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}}
.note{{color:var(--muted);font-size:12px;line-height:1.5;margin-top:16px;border-top:1px solid var(--line);padding-top:12px}}
@media (max-width:820px){{.tiles{{grid-template-columns:repeat(3,1fr)}} .grid2{{grid-template-columns:1fr}}}}
</style>
<div class="wrap">
<header>
  <h1>Boat Dock Network — 5-Year Pro Forma</h1>
  <p class="mono">Whole-lake, wireless-first · grounded in verified GIS (9,571 premises · 30 nodes · 87% LOS)</p>
</header>
<div class="tiles">{tiles}</div>

<div class="grid2">
  <figure><figcaption>Cumulative cash flow (pre-financing)</figcaption>
    <div class="sub">Peak funding need ${S['peak_funding_need_000']/1000:.1f}M (end Y2); turns positive Y5.</div>{chartA}</figure>
  <figure><figcaption>Revenue · OpEx · EBITDA</figcaption>
    <div class="sub">EBITDA positive from Year 2.</div>{chartB}
    {leg([("Revenue","var(--s1)"),("OpEx","var(--s2)"),("EBITDA","var(--s3)")])}</figure>
  <figure><figcaption>Premises passed vs subscribers</figcaption>
    <div class="sub">Take rate ramps 25% → 44% as zones mature.</div>{chartC}
    {leg([("Premises passed","var(--s1)"),("Subscribers","var(--s2)")])}</figure>
  <figure><figcaption>CapEx composition</figcaption>
    <div class="sub">Infrastructure incl. $1.37M spine; connections scale with subscribers.</div>{chartD}
    {leg([("Network infrastructure","var(--s1)"),("Subscriber connections","var(--s3)")])}</figure>
</div>
<p class="note"><b>Why so much cheaper than a fiber build:</b> the viewshed analysis shows 87% of premises
are reachable by wireless line-of-sight from shoreline high points, so cost-per-passing is
~${S['cost_per_passing']:,} (vs ~$1,800 for a fiber overbuild) — collapsing whole-lake CapEx to
~${S['capex_5y_000']/1000:.1f}M. Planning-grade; the bare-earth LOS is optimistic (real foliage adds relays/fiber).
Regenerate with <span class="mono">software/finance/model.py</span> + <span class="mono">make_dashboard.py</span>.</p>
</div>
"""
open(out_html, "w").write(HTML)
print(f"wrote {out_html} ({len(HTML)//1024} KB)")
