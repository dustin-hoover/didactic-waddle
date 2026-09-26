# 11 — Procurement & Materials-Ordering Process

Goal: a repeatable, low-overhead process that turns a released work order into
delivered materials on the right boat, with clean records for accounting and grant
compliance. It runs on the BOM kits (doc 10) and the DockOS procurement module
(doc 14).

## 1. Flow: work order → materials → asset

```
Design (GIS) ──► Release WO (type + params) ──► DockOS expands BOM kit
      ──► Check inventory ──► Reserve on-hand / raise PO for shortfall
      ──► Vendor order ──► Receive + QC ──► Stage to zone cache / boat
      ──► Install (consume) ──► As-built ──► Asset record + cost captured
```

Every step is a state in DockOS so nothing is bought twice or lost, and every dollar
lands on the right asset/grant.

## 2. Inventory model

- **Central warehouse** (the shoreline yard) holds bulk + long-lead items.
- **Zone caches** at host-node/marina partners hold fast-moving spares to cut boat
  travel.
- **Boat kits** (doc 10 `wo-spare-kit-boat.csv`) travel with crews.
- **Reorder points** per SKU: DockOS flags when on-hand < (lead-time demand + safety
  stock) and drafts a PO. Tune from consumption history.
- **Serialized tracking** for radios/OLT/ONT/CPE (feeds `node_equipment`/`cpe` in GIS
  and warranty/RMA).

## 3. Purchasing controls

- **Approval tiers:** small (auto/coordinator), medium (ops lead), large (owner/CFO).
- **Preferred-vendor list** with primary + alternate per SKU (the BOM `vendor_alt`
  column) to survive shortages and price spikes.
- **3-quote rule** above a threshold, and for any grant-funded purchase (compliance).
- **Blanket POs / volume agreements** for high-run items (drop fiber, CPE, connectors)
  to lock pricing and lead times.
- **Grant-funded purchases** are flagged and segregated at PO creation (doc 09/13) so
  reimbursement paperwork is automatic, and any **domestic-sourcing / Build America
  Buy America (BABA)** requirements are checked *before* ordering.

## 4. Vendor categories

| Category | Examples | Notes |
|----------|----------|-------|
| Wireless radios | Tarana, Cambium, Ubiquiti, licensed-µW OEM | Standardize models |
| Fiber/OSP | fiber cable, closures, hardware distributors | Blanket POs |
| PON/optics | XGS-PON OLT/ONT vendor + optics | Interop-test first |
| Power | solar/battery/UPS, PoE | Marine/outdoor rated |
| Enclosures/mounts | NEMA-4X, masts, dock mounts | Marine-rated |
| Fleet/marine | boats, motors, trailers, safety | Local dealer + service |
| Test gear/tools | splicer, OTDR, meters | Calibration tracking |
| Services | tower/climb, boring/HDD, permit expediters | Subcontracts |

## 5. Lead-time & risk management

- Maintain a **long-lead list** (OLT, licensed-µW radios, some fiber) and pre-order
  ahead of build phases.
- Keep **safety stock** on outage-critical spares (CPE, backhaul radios, PoE) so
  repairs never wait on shipping.
- Track **BABA/domestic-content** status per SKU where grants require it.
- Dual-source everything critical (the `vendor_alt` column is the mechanism).

## 6. Receiving & QC

- Match receipt to PO to BOM; inspect, record serials, flag damage/RMA.
- Bench-test radios/OLT/ONT before staging (catch DOA before a boat trip).
- Update inventory + asset records on receipt and again on install (consume).

## 7. Records & audit

- Every PO links to a work order, a vendor, and (if applicable) a grant program.
- Every install consumes inventory and creates/updates an asset with cost basis.
- This chain gives clean **CapEx capture**, **grant reimbursement packages**, and
  **warranty/RMA** history — all from one system.

## 8. Automation with DockOS + Claude

- BOM expansion, reorder drafting, and PO packages are automated (doc 14).
- A **procurement assistant** (Claude API) can draft RFQs, compare quotes, and check
  BABA/grant eligibility per line — a cheap way to run lean.
- A **grants/finance Routine** (doc 13) can watch for NOFOs and price/lead-time shifts.
