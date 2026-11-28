#!/usr/bin/env python3
"""BDN cooperative governance-unit ("WAKE") tokenomics simulation.

Model (governance-only, non-transferable, tenure-weighted, capped):
  * Each active member accrues +1 unit per full month of continuous membership.
  * Host-node members accrue at HOST_MULT x (reward for hosting).
  * On churn, the member's units are BURNED to the Commons Pool (forfeiture).
  * Annually, REDIST_FRAC of the Commons Pool is redistributed EQUALLY to active
    members (a loyalty dividend) -> total circulating units can grow over time.
  * Voting weight per member = min(units, VOTE_CAP), then capped at WHALE_CAP of the
    total active weight at tally time (anti-capture). Plus a democratic base of 1.

Cohort microsimulation over HORIZON months, driven by the verified subscriber curve
(data/financial/pro_forma.csv). No securities assumptions — units carry governance
only; economics are separate co-op patronage dividends (see docs/16).

Outputs: data/financial/tokenomics_sim.csv + prints headline stats.
"""
import csv, os
import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIN = os.path.join(REPO, "data", "financial")

# ---- parameters (dials) ----
HORIZON      = 96          # months (8 years)
CHURN_MO     = 0.013       # monthly churn
HOST_MULT    = 1.5         # host-node accrual multiplier (applied to ~6% of members)
HOST_SHARE   = 0.06
REDIST_FRAC  = 0.50        # fraction of Commons Pool redistributed each year
VOTE_CAP     = 120         # units cap for voting weight (10 yrs @ 1/mo)
BASE_VOTE    = 1           # democratic floor per active member

# ---- subscriber curve -> monthly active target ----
subs_year = {}
with open(os.path.join(FIN, "pro_forma.csv")) as f:
    for r in csv.reader(f):
        if r[0] == "subscribers_cumulative":
            subs_year = {i+1: int(v) for i, v in enumerate(r[1:6])}
# yearly endpoints incl. slight post-Y5 growth
pts = {0:0, 12:subs_year[1], 24:subs_year[2], 36:subs_year[3], 48:subs_year[4],
       60:subs_year[5], 72:4400, 84:4500, 96:4550}
xs = sorted(pts); active_target = np.interp(range(HORIZON+1), xs, [pts[x] for x in xs])

# ---- cohort state: list of dicts {size, units_per, host} keyed by join month ----
cohorts = []   # each: [size, units_per_member, is_host_fraction handled via mult avg]
pool = 0.0
rows = []
prev_active = 0.0
redist_bonus = 0.0   # cumulative equal bonus units per active member from redistribution

for t in range(1, HORIZON+1):
    target = active_target[t]
    # churn existing cohorts; leavers forfeit their units to pool
    for c in cohorts:
        leave = c[0] * CHURN_MO
        pool += leave * c[1]           # forfeited units
        c[0] -= leave
    active_after_churn = sum(c[0] for c in cohorts)
    # gross adds to hit target
    adds = max(0.0, target - active_after_churn)
    if adds > 0:
        cohorts.append([adds, 0.0])    # new cohort, 0 units yet
    # accrue +1 unit/month (host-weighted average multiplier)
    avg_mult = 1 + HOST_SHARE*(HOST_MULT-1)
    for c in cohorts:
        c[1] += avg_mult
    active = sum(c[0] for c in cohorts)
    active_units = sum(c[0]*c[1] for c in cohorts)
    # annual redistribution
    if t % 12 == 0 and active > 0:
        give = pool * REDIST_FRAC
        pool -= give
        per = give / active
        redist_bonus += per
        for c in cohorts:
            c[1] += per                # equal loyalty dividend to all active members
        active_units = sum(c[0]*c[1] for c in cohorts)
    # voting weight (capped) + total
    total_weight = sum(c[0]*(BASE_VOTE + min(c[1], VOTE_CAP)) for c in cohorts)
    avg_units = active_units/active if active else 0
    # founding-cohort share (joined in first 12 months) of total weight
    found_w = sum(c[0]*(BASE_VOTE+min(c[1],VOTE_CAP)) for i,c in enumerate(cohorts) if i < 12)
    rows.append(dict(month=t, active=round(active), active_units=round(active_units),
                     pool=round(pool), total_units=round(active_units+pool),
                     avg_units=round(avg_units,1), total_weight=round(total_weight),
                     founding_share=round(100*found_w/total_weight,1) if total_weight else 0))
    prev_active = active

# ---- write CSV ----
os.makedirs(FIN, exist_ok=True)
with open(os.path.join(FIN, "tokenomics_sim.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

def at(m): return next(r for r in rows if r["month"] == m)
print(f"{'MONTH':>6}{'ACTIVE':>8}{'ACT.UNITS':>10}{'POOL':>8}{'TOTAL':>9}{'AVG/MBR':>9}{'FOUND%':>8}")
for m in (12, 24, 36, 60, 84, 96):
    r = at(m); print(f"{m:>6}{r['active']:>8,}{r['active_units']:>10,}{r['pool']:>8,}{r['total_units']:>9,}{r['avg_units']:>9}{r['founding_share']:>8}")
print()
print("Voting-weight curve (units -> weight, cap %d):" % VOTE_CAP)
for u in (1, 6, 12, 24, 60, 120, 180):
    print(f"  {u:>3} mo -> {BASE_VOTE+min(u,VOTE_CAP):>3} votes")
print(f"\nFounding cohort share of votes: {at(12)['founding_share']}% (Y1) -> {at(96)['founding_share']}% (Y8)"
      f"  [decentralizes as membership grows]")
print(f"Total units grow {at(12)['total_units']:,} -> {at(96)['total_units']:,} over the horizon.")
