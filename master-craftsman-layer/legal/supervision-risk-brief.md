# Supervision-risk brief — remote master supervision of augmented technicians

**This is attorney-preparation material, not legal advice.** It organizes the
questions and primary sources a licensed attorney in the chosen state must
resolve *before any hire*. Decision **D2** (greenlight the model) belongs to the
founder + attorney, not to this document and not to an AI.

## The linchpin question

> Does the chosen state permit an unlicensed (or registrant/apprentice-level)
> worker to perform trade work when the supervising master's oversight is
> **remote** (audio/video via AR headset) rather than physically on-site — and
> at a **ratio** of one master per 8–10 concurrent jobs?

Everything about the company's legality and unit economics rides on the answer.
Two failure modes:

1. **"Supervision" is read to require physical presence** → the augmented-tech
   model is unlicensed practice; every job is a violation and, worse, an
   uninsured liability if something goes wrong.
2. **A ratio cap** (e.g., 3:1) exists → even if remote supervision is allowed,
   the 1:8–10 economics are illegal, and the arbitrage collapses.

## What the primary sources already show (retrieved 2026-09-15)

### Arkansas — comparatively favorable, but silent on the crux
- A "registrant" pays $25, registers, and "can only perform work for an HVACR
  licensee." The "designated license holder" is **solely responsible** for the
  HVACR work performed. (A.C.A. § 17-33-303; 17 CAR § 261-104.)
- License to engage in HVACR work is required "unless exempted"; registrants are
  the exemption path. (A.C.A. § 17-33-301.)
- **The statute and rules do not, on their face, define whether the licensee's
  supervision must be physical/on-site.** That silence is the opening — and the
  risk, because silence can be filled by a board interpretation or an
  enforcement action, not just by the text.
- **Attorney questions for AR:**
  1. Has the HVACR Licensing Board issued any interpretation, advisory, or
     enforcement action defining the supervision duty owed by a "designated
     license holder" to a registrant?
  2. Is there a registrant-to-licensee ratio anywhere in statute, rule, or board
     practice?
  3. Does the "solely responsible" language create personal/criminal exposure
     for the remote master on a registrant's error, and how is that insured?
  4. Do gas-fired appliance / gas piping tasks fall under a *different* licensing
     regime (see § 17-38-301 reference) that is stricter than general HVACR?

### Oklahoma — likely incompatible as designed
- Apprentices may perform mechanical work **only under "direct supervision"** of
  a licensed contractor or journeyman (OAC 158:50-9-5(g); 158:50-11-2).
- **Maximum three apprentices per licensed person** (OAC 158:50-9-5(h)).
- No person may act as foreman/supervisor over mechanical work without a
  contractor or journeyman license (OAC 158:50-1-3(g)).
- **Read:** "direct supervision" + a hard 3:1 cap is very hard to reconcile with
  one remote master over 8–10 jobs. Counsel should confirm, but treat OK as
  disqualified for the model unless a *contractor-license-per-branch* structure
  with on-site journeymen is viable — which changes the labor-cost thesis.

## Case-law pull — to be run with CourtListener / Descrybe

Not yet run in this session (keeping the pull scoped to the finalist state once
D1 is picked). The query set for counsel:

- Enforcement actions / disciplinary opinions where a licensee was penalized for
  inadequate supervision of unlicensed labor (per chosen state's board).
- Any ruling construing "supervision" / "direct supervision" as requiring
  physical presence in the trades context.
- Liability cases assigning fault to a supervising license holder for an
  unlicensed worker's error (gas, electrical, water damage).
- Unlicensed-practice-of-trade prosecutions in the last 5 years in-state.

Run via `mcp__CourtListener__search` and `mcp__Descrybe_Legal_Engine__
search_cases_by_concept` scoped to the chosen state once D1 is decided.

## Recommendation to founder (D2 framing)

- **Do not hire against an ambiguity.** Get a written attorney opinion on the
  remote-supervision + ratio question for the chosen state, plus a written board
  position if obtainable. The cost of that opinion is trivial next to "one gas
  leak ends the company."
- **Design the org to the strictest defensible reading**, then relax only if
  counsel says you may — e.g., start with on-site journeyman supervision and
  layer remote assistance on top, proving safety and economics before leaning on
  remote-only supervision where the law allows it.
- **Insurance is part of the legal answer, not separate.** Confirm the GL/E&O
  carrier will actually cover the remote-supervision model as described before
  relying on it (see `insurance-bonding` MCP stub / Phase 2 item 5).

## Status
- Sources pulled: AR + OK statutes/rules. **Confidence: primary text is solid;
  interpretation is explicitly open and reserved for counsel.**
- Not yet done: case-law pull (scoped to finalist state post-D1); KS/MO/SC/ID/TN
  statutory read; written attorney opinion; carrier confirmation.
