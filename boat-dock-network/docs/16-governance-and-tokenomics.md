# 16 — Cooperative Governance & Tokenomics

> **Not legal advice.** This designs a *mechanism*. A token/co-op that touches ownership,
> voting, and value must be reviewed by securities + cooperative counsel before launch.
> The design below is deliberately shaped to keep the governance unit **out of
> securities territory** and make that review straightforward.

Boat Dock Network is structured as a **member cooperative**: the people the lake network
serves collectively govern it. Governance runs on a non-transferable, tenure-earned
unit (working name **WAKE**); economics run on standard cooperative **patronage
dividends**. Keeping those two things separate is what makes the crypto/DAO layer safe.

## 1. The two-rail design (why it's safe)

| Rail | Vehicle | Who gets it | Legal nature |
|------|---------|-------------|--------------|
| **Governance** | WAKE units (non-transferable) | Earned by membership tenure | Not a security — no price, not tradable, no profit expectation |
| **Economics** | Patronage dividends (cash/bill credit) | Allocated by patronage (service purchased) | Recognized cooperative mechanism, not a token |

Because WAKE **cannot be bought or sold and confers no direct financial return**, it
fails the Howey "expectation of profit from a tradable instrument" test that would make
it a security. Members share in surplus through **patronage dividends** — the same way
electric/telephone co-ops have for a century — not through token appreciation.

## 2. How WAKE works (the mechanism)

- **Accrual:** every active member earns **+1 WAKE per full month** of continuous paid
  membership. **Host-node members** (who host a T1–T3 node) accrue at **1.5×** as a
  reward for extending the network.
- **Non-transferable ("soulbound"):** WAKE lives in your member account. It can't be
  sold, sent, or speculated on. It is a transparent ledger of loyalty + a voting weight.
- **Forfeiture on churn:** if you cancel, your WAKE is **burned to the Commons Pool**
  (a cooperative treasury of voting weight). You stop voting.
- **Redistribution (supply grows over time):** each year, **50% of the Commons Pool is
  redistributed equally to all active members** as a *loyalty dividend* of WAKE. Lapsed
  members' influence flows back to those still building the network — so total
  circulating WAKE grows as the co-op matures (exactly the requested dynamic).
- **Rejoining:** returning members start a fresh accrual (prior WAKE stays burned);
  a tenure-credit option for returnees is a governance decision, not baked in.

### Voting weight (tenure-weighted, capped)
```
weight(member) = 1  +  min(WAKE_units, 120)
```
- **+1 base** = a democratic floor (every active member always has a vote).
- **1 unit/month, linear** — your loyalty literally is your voice, as intended.
- **Capped at 120** (≈10 years) so the earliest members can't entrench permanently.
- **Anti-capture:** at tally time, no single member may exceed **2%** of total active
  weight (excess is clipped), and members may **delegate** their weight to another
  member (liquid democracy).

| Tenure | Votes | | Tenure | Votes |
|--------|-------|-|--------|-------|
| 1 mo | 2 | | 5 yr | 61 |
| 6 mo | 7 | | 10 yr | 121 |
| 1 yr | 13 | | 15 yr | 121 (capped) |

## 3. What the numbers do (verified simulation)

From `software/governance/tokenomics_sim.py` (driven by the real subscriber curve;
`data/financial/tokenomics_sim.csv`):

| End of | Active members | Circulating WAKE | Commons Pool | Total WAKE | Founding-cohort vote share |
|--------|----------------|------------------|--------------|-----------|----------------------------|
| Year 1 | 835 | 5,461 | 129 | 5,590 | 100% |
| Year 3 | 2,963 | 50,454 | 3,052 | 53,506 | 39% |
| Year 5 | 4,211 | 134,338 | 11,461 | 145,798 | 20% |
| Year 8 | 4,550 | 279,595 | 30,524 | 310,120 | **11%** |

Two designed outcomes fall right out of the math:
1. **Total supply grows** (5,590 → 310,120) as the co-op matures — the pool keeps
   recycling lapsed influence back to active members.
2. **It decentralizes over time** — the founding cohort's share of votes falls from
   100% to ~11% as new members join and accrue. Early loyalty is rewarded *and* power
   spreads. That's the healthy version of "the longest-signed-up have a say."

## 4. Governance scope (what members vote on)

**Members decide:** board/steward elections; which zone is built next; the host-node
program terms; pricing-tier changes; how annual surplus splits between patronage
dividends and reinvestment; community fund grants; major capital projects above a
threshold; bylaw amendments (supermajority).

**Reserved to the board/management** (to stay operable + lender-/grant-compliant):
day-to-day operations, safety, regulatory compliance, debt-covenant obligations,
emergency response. Lenders (RUS/CoBank) and grant programs require this — a co-op that
can't honor covenants isn't fundable.

**Mechanics:** proposal threshold (e.g., 0.5% of active weight to table); quorum
(e.g., 15% of active weight); simple majority for ordinary matters, 2/3 for bylaws;
time-boxed voting; all results on a public ledger.

## 5. Technology & phasing (cheap first, on-chain when justified)

- **Phase A — off-chain ledger (launch).** WAKE accrual is computed by DockOS from
  billing tenure; a `wake_ledger` records every accrual/forfeit/redistribute event;
  voting runs in-app or via **Snapshot** (gasless, signature-based). Zero gas, fully
  reversible, compliant. This is where we start.
- **Phase B — on-chain mirror (scale).** Once membership + legal clear it, mirror
  balances as **non-transferable soulbound tokens** (ERC-5192 / ERC-1155 with transfers
  disabled) on a low-fee L2 (Base/Optimism); keep Snapshot for gasless voting; optional
  on-chain treasury (Moloch/Aragon-style) for community-fund spends. Transfer stays
  disabled — that's the property that keeps WAKE non-security.
- **Never:** an ICO, a public sale, or a tradable market for WAKE. If the co-op ever
  wants a true economic token, that is a separate, counsel-led securities process.

## 6. Legal structure checklist (for counsel)

- Form as an **Arkansas cooperative** (or LLC operated on cooperative principles);
  adopt bylaws encoding §2–§4 above.
- Confirm **WAKE is non-transferable, no redemption for cash, no dividend** → memo the
  securities analysis (Howey/Reves) concluding governance-only.
- Patronage-dividend accounting under Subchapter T (co-op tax treatment); coordinate
  with the CPA (doc 09).
- Ensure governance **reserved matters** satisfy lender covenants and grant conditions
  (doc 13) — decentralization must not jeopardize RUS/BEAD compliance.
- Data/consumer protection for the member ledger; clear member agreement.

## 7. DockOS integration (data model)

New tables (see `software/db/governance_schema.sql`): `members` (links `customers`),
`wake_ledger` (accrual/forfeit/redistribute events), `wake_balances` (materialized),
`commons_pool`, `proposals`, `votes`, `delegations`. Accrual is a monthly job off the
billing/subscription state; voting weight is computed from `wake_balances` with the cap
+ anti-whale clip at tally time. Full governance app is a backlog item (BACKLOG.md).

## 8. Why this is a genuine advantage

- **Acquisition + retention:** every month a member stays, their voice grows — a
  loyalty mechanic no incumbent ISP can match.
- **Aligned expansion:** host-node bonus WAKE turns members into network-builders.
- **Local trust:** the lake community literally governs the lake's network.
- **Fundable:** governance is real but bounded, so grants and low-interest telecom debt
  remain available — you get the co-op story *without* scaring lenders or the SEC.
