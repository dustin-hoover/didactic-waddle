#!/usr/bin/env python3
"""Middle-mile / transit capacity sizing for Boat Dock Network.

Turns the subscriber curve into how much internet to actually BUY each year:
peak busy-hour demand, provisioned capacity (headroom), a redundant 2-on-ramp
port plan (each path able to carry the load if the other fails), and an indicative
cost that reconciles to the pro forma's transit line. Outputs data/financial/
transit_plan.csv. No third-party deps.
"""
import csv, os
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIN = os.path.join(REPO, "data", "financial")

subs = {}
for r in csv.reader(open(os.path.join(FIN, "pro_forma.csv"))):
    if r[0] == "subscribers_cumulative":
        subs = {i+1: int(v) for i, v in enumerate(r[1:6])}

# --- dials ---
BH_PER_SUB = {1: 2.5, 2: 2.8, 3: 3.2, 4: 3.6, 5: 4.0}   # busy-hour Mbps/sub (grows)
BIZ_UPLIFT = 1.30      # ~8% business/marina at higher draw
HEADROOM   = 1.40      # provision above peak
BILL_FRAC  = 0.75      # 95th-percentile billed vs peak
TRANSIT_PER_MBPS = {10:0.90, 25:0.60, 100:0.35}  # $/Mbps/mo by port tier (planning)
TRANSPORT_MO = {10:1500, 25:2500, 100:6000}       # per-path DWDM/wave lease $/mo by tier

def port_for(gbps):   # smallest standard port that carries `gbps` with margin
    for p in (10, 25, 100):
        if gbps <= p*0.85: return p
    return 100

rows=[]
for y in (1,2,3,4,5):
    n=subs[y]; peak=n*BH_PER_SUB[y]*BIZ_UPLIFT/1000.0        # Gbps
    prov=peak*HEADROOM
    # redundant: each of 2 on-ramps sized to carry the whole load alone (1+1)
    port=port_for(peak)                                       # each path port tier
    committed=peak*BILL_FRAC*1000                             # Mbps billed (blended over both)
    transit=committed*TRANSIT_PER_MBPS[port]                  # $/mo IP transit
    transport=2*TRANSPORT_MO[port]                            # 2 diverse paths
    mo=transit+transport
    rows.append(dict(year=f"Y{y}", subscribers=n, peak_gbps=round(peak,1),
        provision_gbps=round(prov,1), billed_mbps=round(committed),
        port_each_path=f"{port}G x2", est_monthly_usd=round(mo), est_annual_000s=round(mo*12/1000)))

with open(os.path.join(FIN,"transit_plan.csv"),"w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

print(f"{'YEAR':>5}{'SUBS':>7}{'PEAK Gb':>9}{'PROV Gb':>9}{'PORTS':>10}{'$/mo':>9}{'$k/yr':>7}")
for r in rows:
    print(f"{r['year']:>5}{r['subscribers']:>7,}{r['peak_gbps']:>9}{r['provision_gbps']:>9}"
          f"{r['port_each_path']:>10}{r['est_monthly_usd']:>9,}{r['est_annual_000s']:>7}")
print("\nPort plan = each of TWO diverse on-ramps carries the full load if the other fails (1+1).")
print("Reconciles to pro_forma opex_transit_backhaul; replace dials with real quotes (doc 17).")
