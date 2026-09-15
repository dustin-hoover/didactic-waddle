# diagnosis/ — fault-tree service

Python service. Input: symptom + equipment model + reading set. Output: ranked
fault tree, each node citing the governing code section (NEC / IMC / UPC) with
provenance.

## Contract

```
POST /diagnose
{
  "equipment_model": "Carrier 24ACC6",
  "symptom": "no cooling, compressor runs",
  "readings": [
    {"metric": "superheat", "value": 22, "unit": "F"},
    {"metric": "subcooling", "value": 3, "unit": "F"}
  ]
}
->
{
  "ranked_faults": [
    {"fault": "low refrigerant charge / leak", "confidence": 0.61,
     "why": "high superheat + low subcooling", "next_check": "..."}
  ],
  "citations": [
    {"code_body": "IMC", "section": "1101.10", "edition_year": 2021,
     "state": "AR", "jurisdiction": "...", "source_url": "..."}
  ],
  "audit_id": "uuid"   // row in diagnosis_audit: model, prompt, retrieved_doc
}
```

## Non-negotiables (see EXECUTION_BOUNDARY + schema.sql)

- **Every** call writes a `diagnosis_audit` row (model, prompt, retrieved doc,
  output) before returning. No audit row → no response.
- The model call is **stubbed** here. Wire retrieval over a starter corpus of
  manufacturer service manuals; do not ship a diagnosis that isn't grounded in a
  retrieved, cited document.
- Hazard-classed symptoms (gas smell, scorching, CO) short-circuit to
  "STOP — escalate to supervisor live-view," never a self-serve fault tree.

## Files
- `service.py` — FastAPI app, stubbed model call, retrieval interface.
- `corpus/` — starter service-manual corpus (to be added; licensing of manuals
  must be cleared first).
