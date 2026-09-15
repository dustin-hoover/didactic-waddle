# Execution boundary

What this workspace automates, and what it deliberately does not — with the
reasoning, so a future operator (human or agent) does not "helpfully" cross a
line that ends the company or violates someone's trust.

## Automated / safe to do without a gate

- Directory + document scaffolding (this repo).
- Financial *modeling* from operator-supplied assumptions (no money moves).
- Data-model and application *scaffolds* (no live customer or worker data).
- Market and legal *research* against connected read-only sources
  (Bigdata.com, CourtListener, Descrybe, Exa, Firecrawl) — clearly labeled with
  sourcing and confidence.
- Drafting documents for human review (JDs, brief outlines, email drafts held
  in Drafts, not sent).

## NOT automated — founder-owned, human-in-the-loop required

These are irreversible or outward-facing. Approval for one does not extend to
the next; each needs an explicit go from a person.

| Action | Why it is gated |
|--------|-----------------|
| Forming the C-corp / LLC | Legal entity with tax + liability consequences; needs correct jurisdiction, cap table, and counsel. |
| Signing the master-supervision agreements | **The linchpin document.** Getting the unlicensed-labor / remote-supervision model wrong is the single largest existential + regulatory risk. Requires a licensed attorney in the beachhead state — no AI brief substitutes. |
| Any money movement (Ramp/Stripe/QuickBooks/Gusto) | Real funds; card programs, payroll, customer charges. |
| Launching paid ads ($500–$2k/day) | Real spend, brand exposure, and legal claims ("master-supervised") that must be truthful and licensable. |
| Extending offers / hiring | Employment law, equity grants, real people's livelihoods. |
| Pulling / exporting homeowner records (the "5,000 households" list) | Third-party **personal data**. Sourcing, consent, and marketing-contact law (TCPA/telemarketing, state privacy) govern this. Do not assemble or export a PII prospecting list on autopilot. |
| Sending outbound email to insurers/vendors | Outward-facing commitments in the company's name. Draft, don't send, until a person approves. |

## Hard safety invariants (must be enforced in code, not policy)

Baked into `tech/schema.sql` and the service specs:

1. **No job closes without an explicit supervisor `sign_off_ts`.**
2. **Any gas, main-panel, or roof-penetration task auto-escalates to a
   synchronous supervisor live-view** — hard-coded, not a configurable flag.
3. **Every diagnosis and code citation is logged** with model, prompt, and
   retrieved document for audit.
4. **Any Class-A safety incident (gas, fire, injury) halts operations** and
   pages the founder before any further phased work proceeds.
