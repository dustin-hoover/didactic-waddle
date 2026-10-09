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
| Social accounts | Mostly automated: clips and posts prepared and scheduled, owner only approves | 2026-10-09 |
| Launch timing | No public push until the combined site (gallery and domain) exists | 2026-10-09 |

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

## Legal read (high level, not legal advice)

The owner asked for an analysis from the research tools connected to these sessions. CourtListener (US case law)
and a web search were used; the Descrybe legal engine needs signing in again and was not available. Case citations
below were confirmed in CourtListener; what each case held is summarised from general knowledge, because the
service throttled full-text checks. **A lawyer should confirm all of it.**

### What the cases say about projects like this
- **The "facts" of a novel are not free facts.** *Castle Rock Entertainment v. Carol Publishing*, 150 F.3d 132
  (2d Cir. 1998): a Seinfeld trivia book infringed, because invented events and characters are the author's
  expression, not facts about the world. Our law I.1 ("facts in our own words") lowers the risk but does not remove
  it: a story's geography, timeline and who-went-where are themselves the author's creation.
- **Reference works can be fair use, until they copy too much.** *Warner Bros. v. RDR Books*, 575 F. Supp. 2d 513
  (S.D.N.Y. 2008), the Harry Potter Lexicon: the court accepted that a reference guide can be transformative, but
  the Lexicon lost because it lifted too much of the author's own wording. That is the closest case to ours, and it
  supports our rules (no copied prose, short captions in our words). It is also a warning for the planned Harry
  Potter world: Warner Bros. enforces.
- **Money changes the weighing.** *Andy Warhol Foundation v. Goldsmith*, 598 U.S. 508 (2023), narrowed
  "transformative" use when a use is commercial and serves a purpose close to the original's. Ads and a store make
  fair use harder to win than a free hobby site.
- **Titles on merchandise.** *Jack Daniel's v. VIP Products*, 599 U.S. 140 (2023): when a name or mark is used as
  the brand of your own goods, the free-speech shield for parody and expressive works does not apply. A store must
  never put book titles, character names or house words on products.
- **The Tolkien Estate sues.** *The Tolkien Trust v. Polychron*, No. 2:23-cv-04300 (C.D. Cal. 2023): a fan's
  unauthorised sequel ended in a permanent injunction, and the Estate then sought contempt when it kept circulating.
  The Estate's own FAQ refuses permission for its works in promotion and says it "takes copyright very seriously".

### Risk by world
| World | Risk | Why |
|---|---|---|
| Arda | **Highest** | An active, litigious estate; and our own notes say the coast was traced from Christopher Tolkien's map and outlines sampled from Fonstad's atlas (law I.2) |
| The Known World | Moderate | Built without tracing and labelled unofficial; the rights holders are watchful of the TV brand, which we never use |
| Harry Potter (planned) | High | Warner Bros. won the Lexicon case and polices fan commerce |
| Dungeon Crawler Carl (planned) | Lower, and an opportunity | A living author with a smaller operation: worth asking for an informal blessing before building |

### What this means for the plan
1. **See the lawyer before the public launch, not only before money.** Launch is when the rights holders notice,
   and Arda's sourcing is a question best answered privately first. One flat-fee consult (~$300–800) or a free one
   through Volunteer Lawyers for the Arts, the state bar's referral service, or a law-school IP clinic.
2. **Bring the lawyer a packet:** the laws, a link to each world, the sources ledger, the Arda tracing note, and
   the money plan (area 3). Ask: Is Arda's geography safe or must it be redrawn? Are ads on a fan reference site
   acceptable? What disclaimers and DMCA process do we need? Should payments go through an LLC?
3. **Redraw Arda the Known World way** if the lawyer says so: our own generalised coastline and outlines, positions
   graded from the text. This is the cleanest fix and fits the scaling work anyway.
4. **Ask before building** the Harry Potter and Dungeon Crawler Carl worlds; a short letter to the author's agent
   costs nothing.
5. **GitHub Pages and money:** GitHub's terms allow donation buttons and crowdfunding links on Pages, but not a site
   run as a business. Donations can start on Pages; ads or a store mean moving hosting first (area 1).

## 2. Sharing and launch

### Before any push
- Arda gets its "unofficial fan project" notice (law I.5).
- The owner tests leaving their own visits out of the counter (`#toggle-goatcounter`) on each device.
- Each world gets a link-preview image and description, so a shared link shows a globe, not a blank card.
- A clip recorder: the existing headless screenshot tool (`tools/app_test.py`) extended to save frame sequences,
  turned into video with ffmpeg. All footage is our own app, never book art or adaptation material.
- The lawyer consult (above).

### When
The owner decided: **no public push until the combined site exists** (gallery and domain). Suggested shape once it
does:
- **Soft launch** for two to three weeks to small, friendly audiences, to catch bugs and phone problems.
- **Main push** pinned to a date the app can play: Tolkien Reading Day, 25 March, is the day the Ring is
  destroyed in the story ("watch it happen on its anniversary"); Hobbit Day, 22 September, is Bilbo and Frodo's
  birthday and the Long-expected Party. For the Known World, any news of the next novel brings the fandom back.

### Where, in order (one stop every few days)
1. **Builders and makers**: r/proceduralgeneration, r/webgl, r/MapPorn. They like the technique and give honest
   feedback.
2. **Book-first fan communities**: r/asoiaf (a books-focused sub, which fits our books-only law), the Westeros.org
   forums, r/tolkienfans, r/lotr. Read each community's self-promotion rules first; post as a fan sharing a project,
   not as a brand.
3. **Wide audiences**: a "Show HN" on Hacker News (the in-browser generation is the hook), then the same clips on
   TikTok, YouTube Shorts and Instagram Reels; X and Bluesky for developers and map people.
4. **Lore creators**: a short personal note to a few book-lore YouTubers offering clips. Never paid.

### What to show
15–30 second captioned clips, no face or voice (keeps the owner anonymous):
- orbit to ground over Minas Tirith; the Fellowship's road playing out on the timeline;
- snow creeping south over Westeros as winter comes; standing at the foot of the Wall;
- seasons and rulers changing as the slider moves.
No violence for its own sake (law III.5): battles appear as badges, not gore.

### Mostly automated, as the owner chose
- Clips and captions are prepared in batches in a work session; the owner approves the batch.
- A scheduler posts them: Postiz (open source, free to self-host, or ~$29/month hosted) covers TikTok, YouTube,
  Instagram, X, Bluesky and Reddit from one queue. Buffer's free tier is the simpler alternative.
- Replies and community questions still need a human now and then; area 4 routes them.
- Reddit and forums are posted by hand: automated posting there reads as spam and gets banned.

### Measuring with GoatCounter
- Each platform gets its own tagged link (`?ref=tiktok`, `?ref=reddit-asoiaf`), so GoatCounter's referrer view
  shows which post brought people.
- A few in-app events counted with GoatCounter's event call (still cookieless): pressed play, opened the ground
  view, switched story, stayed past one minute. Those say whether visitors explore or bounce.
- A weekly one-line summary: visits, top three sources, share who pressed play.

### Cost of area 2
| Item | Cost |
|---|---|
| Clip recorder, link previews | $0 (our own work) |
| Scheduler | $0–29 a month |
| Paid promotion | none before the lawyer review |
