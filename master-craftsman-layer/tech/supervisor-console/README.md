# supervisor-console/ — remote master's cockpit

Web app for the remote licensed master. WebRTC + Twilio Video for the live tech
feed; one-click sign-off, override, and callout.

## Core screens
- **Live queue** — techs currently on jobs, hazard flags surfaced first.
- **Live view** — audio+video from the tech's AR headset; annotate the feed.
- **Sign-off** — records a `sign_offs` row + stamps `jobs.sign_off_ts`. For a
  hazard-classed job the button is **disabled until `live_view_ts` is set** (the
  schema constraint enforces it server-side too; the UI just fails fast).
- **Override / callout** — halt a tech, escalate, or dispatch a second pair of
  eyes.

## The over-signing risk (flag in weekly RED)
A master signing off faster than they can plausibly have live-viewed is the
single most dangerous failure mode of this whole model. The console must:
- Log every sign-off with whether it was backed by a live-view (`sign_offs.
  live_view` boolean).
- Compute a per-master "sign-offs without live-view" rate and a
  "seconds-of-live-view per sign-off" metric.
- Feed both into the Phase 7 weekly report; a spike goes under **RED**.

## Not built
WebRTC/Twilio Video not wired (no connector). This is the interface + the
invariants it must honor.
