# BOM Kits

One CSV per work-order type. Columns:

```
item, category, spec, qty, unit, unit_cost_est_usd, vendor_primary, vendor_alt, notes
```

- `category` ∈ radio | optics | fiber | enclosure | power | mount | misc | labor | permit | transport
- `qty` may be a parameter placeholder (e.g. `LEN_FT`, `N_SECTORS`) that DockOS
  substitutes from the survey record.
- `unit_cost_est_usd` is **planning-grade** — replace with real quotes during procurement.

**CSV rule:** quote any field that contains a comma (e.g. `"clamps, span/dead-end, NID"`).
The work-order engine (`software/api/dispatch.py`) parses these kits directly; 15 unquoted rows
were repaired when it became the first consumer.

Costs here are illustrative planning estimates (see `docs/ASSUMPTIONS.md`), not quotes.
Edit freely; git tracks every change (that's the "always adaptable" mechanism, doc 10).

## Kit index
| File | Work order |
|------|-----------|
| `wo-survey.csv` | Site/link survey |
| `wo-t0-headend.csv` | Head-end / on-ramp POP (T0) |
| `wo-t1-core.csv` | Core / ring node (T1) |
| `wo-t2-docknode.csv` | Dock aggregation node (T2) |
| `wo-t3-relay.csv` | Relay / repeater (T3) |
| `wo-lake-crossing-mw.csv` | Licensed microwave over-water hop (pair) |
| `wo-fiber-aerial-mile.csv` | Aerial OSP fiber, per mile |
| `wo-fiber-ug-mile.csv` | Underground OSP fiber, per mile |
| `wo-subaqueous-fiber.csv` | Armored fiber cove crossing |
| `wo-drop-aerial-fiber.csv` | FTTH aerial drop |
| `wo-drop-ug-fiber.csv` | FTTH underground drop |
| `wo-cpe-wireless-nlos.csv` | Non-LOS wireless CPE (Tarana) |
| `wo-cpe-wireless-ptmp.csv` | PtMP LOS wireless CPE |
| `wo-spare-kit-boat.csv` | Per-boat repair spares |
