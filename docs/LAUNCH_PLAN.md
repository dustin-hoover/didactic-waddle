# Otherworldly: launch and business plan

A plan only. Nothing here changes the live atlases until the owner says "merge" on the work that carries it out.
Written area by area with the owner; sections marked **draft** are not yet agreed.

## Decisions so far

| Topic | Decision | When |
|---|---|---|
| Name | **Otherworldly** (the name already used by the visit counter) | 2026-10-09 |
| Domain | Not chosen yet. `otherworldly.com` and `.app` are taken; `otherworldlyatlas.com` (~$16 first year) and `otherworldly.world` (~$47) were available on 2026-10-09 | open |
| Owner's name | Must not be tied to the combined site once worlds are merged | 2026-10-09 |
| Repos | Stay in the owner's account for now (no move to an organisation yet) | 2026-10-09 |
| Page hosting | Stay on GitHub Pages for now | 2026-10-09 |
| Scale | Plan for pre-rendered, ever more detailed map tiles, which need storage and a CDN beyond GitHub Pages | 2026-10-09 |
| Budget | Up to about $100 a month before the site earns anything (lawyer not included) | 2026-10-09 |
| Lawyer | Owner is in the US and has no IP lawyer yet | 2026-10-09 |

## Found while reading the repos (for the lawyer review)

- **Arda has no "unofficial fan project" notice.** The Known World has one; the laws (I.5) require it on every page.
  Fix before any public launch push.
- **Arda's sources conflict with law I.2.** Its notes say the coast is traced from Christopher Tolkien's general map
  and hill country and forest outlines are sampled from Karen Wynn Fonstad's atlas. The Known World was built without
  tracing. This is the first question for the lawyer, and may mean redrawing Arda's geography the Known World way.
- **Neither repo has a licence.** Legally that is "all rights reserved", but both repos are public, so the code can be
  read and copied by anyone. See area 5.
- The visit counter is live on both atlases; the owner's own visits are not yet excluded (`#toggle-goatcounter`
  untested).

## 1. Deployment and scaling

### Where things stand
Each world is one ~1 MB HTML page on GitHub Pages. Every tile of terrain and imagery is generated in the visitor's
browser, so hosting costs nothing and the page never grows with detail. The limit is the visitor's phone: detail is
capped by what a phone can compute in a moment.

### Where it is going
The owner expects the worlds to become far more granular. Arda's own blueprint (`dist/blueprint.html`) already
sets the direction: eroded 30 m terrain, a model that paints realistic imagery, cities as 3D tiles, and tiles
**pre-rendered on a server** and served from storage instead of computed on the phone.

Rough size per world, pre-rendered to zoom 14 (about 1.5 km per tile, a town is a few tiles across):

| World | Area | Tiles to z14 | Imagery + terrain |
|---|---|---|---|
| Arda | ~4–5 million km² | ~2–3 million | ~100–200 GB |
| The Known World | ~10× Arda (Westeros, Essos, Sothoryos) | ~20–30 million | ~1–2 TB |
| Seasons | each season level is another imagery set | ×2–5 imagery | |

That is far beyond GitHub Pages (1 GB per site, 100 GB/month soft bandwidth, 100 MB per file).

### The plan: three layers, added as they are needed

1. **Pages** (the gallery and each world's app): stay on GitHub Pages now. Small and rarely changing.
2. **Tiles** (terrain, imagery, vector layers): object storage behind a CDN, at a subdomain such as
   `tiles.<domain>`. Stored as **PMTiles**: one big file per world, layer and season, which the map reads in small
   slices. Static files, no tile server to run.
3. **Deep zoom on demand**: pre-render to z12–14 everywhere, and deeper (z15–18) only along the story corridors
   (places, roads, journeys, battlefields). Anything deeper still is generated the first time someone asks for it
   and cached. Because the engine is deterministic, a tile rendered on the server is identical to one the browser
   would make, so the browser's own generator remains the fallback: nothing breaks if a tile is missing.

Seasons: store one base imagery set and draw snow and browning as a light overlay in the browser, instead of
storing every season as its own imagery. This keeps the Known World's storage from multiplying.

### Storage and CDN options

| Option | Storage | Bandwidth out | Notes |
|---|---|---|---|
| **Cloudflare R2** (recommended) | ~$15 per TB-month | **free** | Built-in CDN; a small Worker can render missing tiles on demand |
| Backblaze B2 + Cloudflare CDN | ~$6 per TB-month | free through Cloudflare | Cheapest storage, one more account |
| AWS S3 + CloudFront | ~$23 per TB-month | ~$85 per TB | Egress makes it costly at fan-site scale |

Free bandwidth matters most: a visitor who explores for a few minutes pulls a few hundred tiles (~5–15 MB).
100,000 visits a month is ~1 TB out, $0 on R2 and ~$85 on AWS.

Estimated tile hosting cost on R2: Arda alone ~$2–5 a month; both worlds at z14 with corridor detail ~$20–40 a
month; read and write charges add a few dollars. Rendering the first full set takes days of GPU time, one-off,
~$50–300 on rented GPUs depending on how far the blueprint's imagery model has got by then.

### When to move off GitHub Pages
Pages stay where they are until one of these happens:
- **Ads or a store go live.** GitHub's terms say Pages is not for sites run as a business. This is the firm trigger.
- **Traffic nears ~100 GB a month** (roughly 80–100k visits to a 1 MB page).
- **A world needs files over 100 MB** or the site passes 1 GB.

Then the pages move to the same CDN as the tiles (Cloudflare Pages or R2: free at this scale).

### The combined site and adding worlds
- **Gallery** at the root: still images or short looping clips of each globe, no map engine, loads in under a second
  on a phone. Each world opens on its own page (`/arda/`, `/known-world/`) only when tapped.
- **Each world keeps its own repo.** A small site repo pulls in each world's approved build at a pinned version
  (a git tag), so one world's update can never break another; a new world is one new entry. Arda's repo stays
  untouched by other worlds.
- **Shared engine:** extracted behind Arda as `docs/otherworldly/WORLD_SPEC.md` plans, re-shot screen by screen.

### Phones
- Gallery first, worlds on tap (above).
- A **lighter mode** for weak phones: fewer workers, coarser terrain, no ground view by default.
- If WebGL is missing, a friendly message and a short video of the globe instead of a blank page.
- Pre-rendered tiles (layer 2) make phones faster, because they download instead of compute. This is the biggest
  phone win and a reason to start layer 2 with Arda early.

### Keeping the owner's name off the site
The repos stay in the owner's account for now (decided above), so `dustin-hoover.github.io` stays in the
addresses until they move. When the owner is ready:
- A GitHub organisation holds the repos; old `github.io` links get a forwarding page for a few months.
- The domain is registered with privacy (Cloudflare includes it free).
- Commits from then on use a project identity, not a personal email.
- Payments (ads, donations, store) go to a single-member LLC (~$50–300 to form, depending on the state), after the
  lawyer review.

### Cost of area 1
| Item | Now | At scale |
|---|---|---|
| Domain | ~$10–16 a year | same |
| Pages | $0 (GitHub Pages) | $0 (Cloudflare) |
| Tile storage and CDN | $0 (browser-generated) | ~$20–40 a month |
| First tile render | — | ~$50–300 one-off |
