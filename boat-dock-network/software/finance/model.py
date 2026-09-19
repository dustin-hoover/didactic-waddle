#!/usr/bin/env python3
"""Boat Dock Network — 5-year pro forma, grounded in the verified GIS analysis.

All inputs are explicit parameters (edit + re-run). Emits:
  data/financial/pro_forma.csv        (income + cash flow by year)
  data/financial/capex_detail.csv     (CapEx line items by year)
  data/financial/model_summary.json   (headline metrics for the dashboard)

No third-party deps. Planning-grade; see caveats in docs/09-accounting-plan.md.
"""
import json, os, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIN  = os.path.join(REPO, "data", "financial")
os.makedirs(FIN, exist_ok=True)
YEARS = [1, 2, 3, 4, 5]

# ---- VERIFIED from GIS analysis (data/gis/outputs) ----
PREM_TOTAL      = 9571          # improved premises <=1mi
PREM_BY_PHASE   = {1: 3341, 2: 2957, 3: 1933, 4: 1340}
NODES_BY_PHASE  = {1: 3, 2: 10, 3: 8, 4: 9}   # 30 total
LOS_COVERED     = 8279          # 87% wireless line-of-sight reachable
SHADOW          = PREM_TOTAL - LOS_COVERED     # ~1292 need relay/fiber
SPINE_CAPEX     = 1_365_000    # from spine_edges (22 licensed MW + land/short hops)

# ---- build schedule: which phase completes in which year ----
PHASE_YEAR = {1: 1, 2: 2, 3: 3, 4: 4}   # Y5 = densification / shadow fill / fiber overbuild

# ---- adoption + revenue assumptions (planning) ----
TAKE_BY_YEAR = {1: 0.25, 2: 0.30, 3: 0.36, 4: 0.40, 5: 0.44}  # blended on cumulative passed
ARPU_MO      = 105            # blended residential + business/marina; premium market
OTHER_REV    = 0.06          # install + add-ons uplift on subscription

# ---- CapEx unit costs (planning; from BOM kits) ----
COST_T2, COST_T3 = 32_000, 14_000       # dock/agg node, relay/fill node
N_T2, N_T3       = 18, 12                # primary vs fill (is_primary split)
COST_HEADEND     = 120_000; N_HEADENDS = 2
COST_CORE_NOC    = 250_000
COST_FLEET_START = 450_000
SHADOW_CAPEX     = 600_000              # extra relays + selective fiber for RF-shadow set
FIBER_OVERBUILD  = 200_000             # Y5 densest-zone fiber overbuild
CONN_COST_BLEND  = 650                  # per subscriber: CPE + install (87% wireless / 13% fiber)

# ---- OpEx (planning; operating team only — construction labor is capitalized) ----
OPEX = {
 "transit_backhaul":       {1:90,  2:150, 3:230, 4:320, 5:400},
 "operating_payroll":      {1:380, 2:620, 3:900, 4:1150,5:1400},
 "site_lease_pole_host":   {1:40,  2:90,  3:140, 4:190, 5:240},
 "sga_software_ins_fuel":  {1:200, 2:320, 3:480, 4:640, 5:780},
}  # $000s

# ---------- derive rollout ----------
passed_cum, added = {}, {}
run = 0
for y in YEARS:
    add = sum(p for p, yr in PHASE_YEAR.items() if yr == y and y != 5)
    add_prem = sum(PREM_BY_PHASE[p] for p, yr in PHASE_YEAR.items() if yr == y) if y != 5 else 0
    run += add_prem
    if y == 5:
        run = PREM_TOTAL
    passed_cum[y] = run
    added[y] = add_prem
# fix Y5 delta
prev = 0
for y in YEARS:
    added[y] = passed_cum[y] - prev; prev = passed_cum[y]

subs_end = {y: round(passed_cum[y] * TAKE_BY_YEAR[y]) for y in YEARS}
subs_new = {}; prev = 0
for y in YEARS:
    subs_new[y] = max(0, subs_end[y] - prev); prev = subs_end[y]
subs_avg = {}; prev = 0
for y in YEARS:
    subs_avg[y] = round((prev + subs_end[y]) / 2); prev = subs_end[y]

# ---------- revenue ($000s) ----------
rev = {y: round(subs_avg[y] * ARPU_MO * 12 * (1 + OTHER_REV) / 1000) for y in YEARS}

# ---------- CapEx ($000s) ----------
node_capex_total = N_T2 * COST_T2 + N_T3 * COST_T3
# allocate node capex across phases by node count
node_share = {y: 0 for y in YEARS}
for p, yr in PHASE_YEAR.items():
    node_share[yr] += NODES_BY_PHASE[p]
tot_nodes = sum(NODES_BY_PHASE.values())
spine_alloc = {1: .40, 2: .30, 3: .20, 4: .10, 5: 0}
capex = {}
for y in YEARS:
    infra = 0
    infra += round(node_capex_total * (node_share.get(y, 0) / tot_nodes) / 1000)
    infra += round(SPINE_CAPEX * spine_alloc[y] / 1000)
    if y == 1:
        infra += round((COST_HEADEND * N_HEADENDS + COST_CORE_NOC + COST_FLEET_START) / 1000)
    if y == 5:
        infra += round((SHADOW_CAPEX + FIBER_OVERBUILD) / 1000)
    conn = round(subs_new[y] * CONN_COST_BLEND / 1000)
    capex[y] = {"infra": infra, "connection": conn, "total": infra + conn}

# ---------- P&L + cash ----------
opex_tot = {y: sum(OPEX[k][y] for k in OPEX) for y in YEARS}
ebitda   = {y: rev[y] - opex_tot[y] for y in YEARS}
cf       = {y: ebitda[y] - capex[y]["total"] for y in YEARS}
cf_cum = {}; run = 0
for y in YEARS:
    run += cf[y]; cf_cum[y] = run

# ---------- write pro_forma.csv ----------
def row(name, d, fmt=lambda v: v): return [name] + [fmt(d[y]) for y in YEARS]
lines = [["line_item"] + [f"Y{y}" for y in YEARS]]
lines += [
    row("premises_passed_cumulative", passed_cum),
    row("subscribers_cumulative", subs_end),
    row("take_rate", TAKE_BY_YEAR, lambda v: f"{v:.2f}"),
    row("avg_subscribers", subs_avg),
    row("revenue_total_$000s", rev),
    row("opex_total_$000s", opex_tot),
    row("ebitda_$000s", ebitda),
    row("capex_total_$000s", {y: capex[y]["total"] for y in YEARS}),
    row("cash_flow_pre_financing_$000s", cf),
    row("cash_flow_cumulative_$000s", cf_cum),
]
with open(os.path.join(FIN, "pro_forma.csv"), "w") as f:
    f.write("\n".join(",".join(str(c) for c in r) for r in lines) + "\n")

# ---------- write capex_detail.csv ----------
cl = [["capex_line_$000s"] + [f"Y{y}" for y in YEARS]]
cl += [
    row("network_infrastructure", {y: capex[y]["infra"] for y in YEARS}),
    row("subscriber_connections", {y: capex[y]["connection"] for y in YEARS}),
    row("capex_total", {y: capex[y]["total"] for y in YEARS}),
]
with open(os.path.join(FIN, "capex_detail.csv"), "w") as f:
    f.write("\n".join(",".join(str(c) for c in r) for r in cl) + "\n")

# ---------- headline metrics ----------
capex_5y   = sum(capex[y]["total"] for y in YEARS)
infra_5y   = sum(capex[y]["infra"] for y in YEARS)
peak_need  = -min(cf_cum.values())
cost_per_passing = round(infra_5y * 1000 / PREM_TOTAL)
cost_per_sub     = round(capex_5y * 1000 / subs_end[5])
summary = {
    "premises_total": PREM_TOTAL, "los_covered": LOS_COVERED, "shadow": SHADOW,
    "subs_year5": subs_end[5], "ultimate_take": TAKE_BY_YEAR[5], "arpu_mo": ARPU_MO,
    "capex_5y_000": capex_5y, "infra_5y_000": infra_5y, "spine_capex": SPINE_CAPEX,
    "peak_funding_need_000": peak_need,
    "ebitda_positive_year": next(y for y in YEARS if ebitda[y] > 0),
    "cash_positive_year": next((y for y in YEARS if cf_cum[y] > 0), None),
    "cost_per_passing": cost_per_passing, "cost_per_sub": cost_per_sub,
    "years": YEARS, "passed_cum": passed_cum, "subs_end": subs_end,
    "revenue": rev, "opex": opex_tot, "ebitda": ebitda,
    "capex": {y: capex[y]["total"] for y in YEARS}, "cf_cum": cf_cum,
}
with open(os.path.join(FIN, "model_summary.json"), "w") as f:
    json.dump(summary, f, indent=2)

# ---------- console ----------
def money(v): return f"${v/1e6:.1f}M" if abs(v) >= 1e6 else f"${v/1e3:.0f}k"  # v in dollars
print("YEAR                " + "".join(f"{'Y'+str(y):>9}" for y in YEARS))
print("Premises passed     " + "".join(f"{passed_cum[y]:>9,}" for y in YEARS))
print("Subscribers         " + "".join(f"{subs_end[y]:>9,}" for y in YEARS))
print("Revenue ($000)      " + "".join(f"{rev[y]:>9,}" for y in YEARS))
print("OpEx ($000)         " + "".join(f"{opex_tot[y]:>9,}" for y in YEARS))
print("EBITDA ($000)       " + "".join(f"{ebitda[y]:>9,}" for y in YEARS))
print("CapEx ($000)        " + "".join(f"{capex[y]['total']:>9,}" for y in YEARS))
print("Cash cum ($000)     " + "".join(f"{cf_cum[y]:>9,}" for y in YEARS))
print()
print(f"5-yr CapEx {money(capex_5y*1000)} (infra {money(infra_5y*1000)}) | peak funding need {money(peak_need*1000)}")
print(f"cost/passing ${cost_per_passing:,} | cost/sub ${cost_per_sub:,} | "
      f"EBITDA+ Y{summary['ebitda_positive_year']} | cash+ Y{summary['cash_positive_year']}")
