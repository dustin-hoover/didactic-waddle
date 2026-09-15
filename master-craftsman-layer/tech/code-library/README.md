# code-library/ — RAG index of state + local code interpretations

Notion-backed retrieval index of the state + local code that governs residential
HVAC work in the beachhead metro. Every citation the platform surfaces (in
diagnosis, the AR overlay, sign-off) resolves back to a row here.

## Seed set
Top ~200 residential HVAC code citations for the chosen state — populated once
D1 fixes the state. Each row mirrors `code_citations` in `schema.sql`:
`code_body, section, state, jurisdiction, edition_year, source_url`.

## Provenance is mandatory
No citation without a `source_url`. A code interpretation with no traceable
source is not usable in the field, full stop — a wrong citation on a gas or
panel job is exactly the failure that ends the company.

## Editions matter
IMC/UPC/NEC editions and local amendments differ by jurisdiction and change on a
cycle. The index stores `edition_year` and must be re-validated whenever a
jurisdiction adopts a new code cycle (flag such changes in the weekly RED
section — "a state's code just changed").

## Not built
Notion connector not live; corpus not seeded (waiting on D1). Schema + sourcing
rules defined.
