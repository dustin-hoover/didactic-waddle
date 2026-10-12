# 10 — Materials & Adaptable BOM System

The BOM is designed to be **adaptable**: a small set of standard, versioned
work-order "kits," each a data file, so pricing, quantities, and vendor parts can
change without rewriting the plan. DockOS consumes these files to auto-generate
material pulls and purchase orders per work order (docs 11 + 14).

## 1. How the BOM system works

- Each **work-order type** has a kit file in [`../data/bom/`](../data/bom/) (CSV).
- A kit lists line items: category, spec, quantity, unit, planning unit cost, and
  vendor/alt-vendor notes. **Costs are planning estimates** — replace with quotes.
- Kits are **parameterized** (e.g., drop length, mast height, number of sectors) so one
  kit covers many real jobs by scaling quantities.
- **Versioning:** kits are files in git → every change is tracked, reviewable, and
  revertible. That *is* the "always adaptable" mechanism.
- **Technology-agnostic sites:** the outside-plant items (mount, enclosure, power,
  backhaul) are stable; the **electronics line items are swappable** (radio/OLT model)
  so a kit updates by changing one row when tech improves.

## 2. Work-order types (kit files)

| WO type | Kit file | What it builds |
|---------|----------|----------------|
| Survey | `wo-survey.csv` | Site/link survey (mostly labor + test gear) |
| Head-end POP (T0) | `wo-t0-headend.csv` | Internet on-ramp + core POP |
| Core/Ring node (T1) | `wo-t1-core.csv` | Spine transport + aggregation |
| Dock aggregation node (T2) | `wo-t2-docknode.csv` | Zone serving node (radios + optional PON) |
| Relay/repeater (T3) | `wo-t3-relay.csv` | Cove/finger reach extension |
| Lake crossing (licensed µW) | `wo-lake-crossing-mw.csv` | Over-water spine hop (pair, space diversity) |
| Fiber backbone / mile (aerial) | `wo-fiber-aerial-mile.csv` | Aerial OSP fiber per mile |
| Fiber backbone / mile (underground) | `wo-fiber-ug-mile.csv` | Underground OSP fiber per mile |
| Subaqueous fiber crossing | `wo-subaqueous-fiber.csv` | Armored cable across a cove |
| Fiber drop (aerial) | `wo-drop-aerial-fiber.csv` | FTTH drop, aerial |
| Fiber drop (underground) | `wo-drop-ug-fiber.csv` | FTTH drop, buried |
| Wireless CPE (nLOS/Tarana) | `wo-cpe-wireless-nlos.csv` | Non-LOS customer install |
| Wireless CPE (PtMP LOS) | `wo-cpe-wireless-ptmp.csv` | Clean-LOS customer install |

## 3. Standard kit columns

```
item, category, spec, qty, unit, unit_cost_est_usd, vendor_primary, vendor_alt, notes
```

- `category` ∈ {radio, optics, fiber, enclosure, power, mount, misc, labor, permit,
  transport}.
- `qty` may be a formula placeholder like `LEN_FT` or `N_SECTORS` for parameterized
  kits (DockOS substitutes the survey value).
- `unit_cost_est_usd` is planning-grade; procurement replaces with quoted cost.

## 4. Master materials catalog (the parts we standardize on)

Standardizing on a short vendor list keeps spares interchangeable and training simple:

| Category | Standard choices (adapt as tech improves) |
|----------|-------------------------------------------|
| nLOS access radio | Tarana G1 base + residential nodes (CBRS/6 GHz) |
| PtMP LOS access | Cambium PMP 450m/450v; Ubiquiti LTU/airMAX |
| Short backhaul | Ubiquiti airFiber (AF60/AF11); Cambium cnWave 60 GHz |
| Licensed µW (crossings) | Aviat/Ceragon/RADWIN with space diversity |
| PON | XGS-PON OLT + ONTs (vendor TBD by quote) |
| Switching/routing | MikroTik / Juniper / Arista per tier + budget |
| Fiber cable | OS2 SM: ADSS aerial, armored bury, armored submarine for subaqueous |
| Enclosures | NEMA-4X / marine-rated cabinets |
| Power | PoE + rack UPS; solar panels + LiFePO4 batteries + MPPT for remote |
| Masts/mounts | Aluminum masts, tilt bases, guy kits, dock/pier mounts |
| Test gear | Fusion splicer, OTDR, optical power meter, spectrum analyzer, cleaver |

## 5. Spare kits (carried on each boat)

Each work vessel carries a **repair spare kit** so most fixes are one trip: spare
CPE (both types), spare backhaul radio, patch/pigtails + splice sleeves, connectors,
fuses/PoE injectors, battery, hardware, and a small fiber cleanup kit. Defined as
`wo-spare-kit-boat.csv` (create alongside the others).

## 6. Cost roll-up (planning)

The per-passing and per-connection numbers in doc 09 are the aggregate of these kits
across a zone. As kits are re-priced from quotes, the pro forma updates automatically
from the same source data — one place to change a price.

## 7. Adaptability guarantees (your requirement)

1. **File-based + versioned** → change anything, keep history.
2. **Parameterized quantities** → one kit, many jobs.
3. **Swappable electronics rows** → new radio = one-row change.
4. **Vendor primary/alt columns** → dodge supply shortages fast.
5. **Consumed by software** → kits drive real POs and asset records, so the plan and
   the operation never drift apart.
