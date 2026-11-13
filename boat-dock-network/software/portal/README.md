# Serviceability + Member Signup Portal

The cooperative's front door: check serviceability, pick a plan, and reserve as a
member / founding member / host — the grant-free funding engine (docs/13, docs/16).

## Two implementations

**1. Prototype artifact (this session)** — `make_portal.py` → `data/portal/signup_portal.html`,
published as a claude.ai artifact with the `db` + `user` capabilities.
- Pin-drop serviceability by zone (embedded lake + 18 zones + 30 nodes), plan selection,
  and signup persisted to the artifact's `db`. The **owner** sees a live sign-up pipeline
  panel (counts + recent list).
- **Org-internal:** declaring `db` makes the artifact organization-internal, so it's for
  the founder + team to demo and to gather internal/early sign-ups — not a public campaign
  page. Every reader/writer is a signed-in member of the owner's org.
- **Privacy note:** contact info entered here is stored in the artifact's shared store,
  readable by interacting org members. Fine for a prototype; PII for a public launch
  belongs in the secured backend below.

**2. Production API (`../api/serviceability.py`) + schema (`../db/signup_schema.sql`)** —
FastAPI + PostGIS for the **public launch**:
- Accepts anonymous public submissions with explicit consent.
- True per-point serviceability (`/serviceability?lat=&lon=` or `?address=` with a
  pluggable geocoder / county E-911 address points).
- Persists to `signups` + `pledges` (pre-sale deposits, membership shares, founding
  capital) and exposes `/zones/demand` for **build gating** (release a zone when
  reservations + committed capital clear the threshold — docs/13 §4).

## Regenerate the prototype
```
python3 software/portal/make_portal.py data/portal/signup_portal.html
# then publish via the Artifact tool with capabilities {"db":{},"user":{}}
```
Data embedded from `data/portal/{lake,zones,nodes}.geojson` (zones carry phase +
foliage-LOS% so the serviceability card is accurate).

## How it ties together
- **Serviceability** ← the GIS zones + canopy-LOS work (docs 04–05).
- **Plans / pricing** ← business plan (doc 06).
- **Member / founding / host options** ← cooperative + WAKE (doc 16) and the grant-free
  funding stack (doc 13). Host sign-ups feed the host-node program (1.5× WAKE).
- **Demand gating** ← per-zone reservations + capital vs the pro forma (doc 09).
