# Arda Atlas: round 4 status report

Against the round 4 fix list (build 5f71374). The fixes are merged to `main` at **14a6b30**.

**Status key**
- **Done:** fixed and checked.
- **Partial:** part of the item was fixed; what remains is listed.
- **Held:** waiting on the owner's decision.
- **Skipped:** not done.

## Commits, in fix order

| Commit | Items |
|---|---|
| d7e3904 | 1, 6 (notice, subtitle, public-text hygiene) |
| f9ded1c | 4, 5 (Barad-dûr artwork, non-film analogues) |
| 549fd67 | 2, 3 (outlines redrawn from text, trace check) |
| ad7187e | 13 (audit rebuilt, new render gate) |
| 17eeab0 | 7–12 (rivers and coast as drawn) |
| 2d248ec | 14–18 (ground views and look) |
| 7f61e5b | 20–31 (sources, dates, attribution, analytics) |
| 14a6b30 | 32–57 (realism and minor) |

## Verification on the final build

`npm run audit` passes all four stages:

1. **`qa_geo.js` passes ("geography ok").**
   - Every segment pair is tested on all 122 rings, and across rings.
   - The island count is checked.
   - Rivers over the sea, river mouths, coastal places and river ports are checked.
   - Every river must end at a shore, a lake or another river.
2. **`trace_check.py` passes (TRACE-PASS).** All 12 formerly traced shapes are at or below 17% within 2 mi of the 4bc9892 trace; the limit is 20%.
3. **`qa_render.py` passes ("render ok", 48 rivers, 5 coast regions).** It runs in a headless browser on the actual renderer and checks:
   - Each drawn river:
     - no more than 0.75 mi over the sea;
     - no more than 1 mi from its authored line;
     - no rise over 5 m within 1 mi downstream;
     - no more than 5 m above the lower bank (2% of miles allowed).
   - Every place stands on rendered land.
   - The rendered coast is within 1% of the vector coast in Umbar, Belfalas, Lindon, Eriador and Forochel.
   - The six named passes are notches.
   - The Ephel Dúath and Ered Lithui stay at or above 1,200 m outside their passes (lowest crests 1,320 m and 1,690 m).
4. **`tools/sources/audit.js` passes.** It regenerates `docs/SOURCES.md`.

**Ground rules held throughout:**
- The Spotify link is unchanged and still opens in a new tab.
- No map label text was changed.
- No history was rewritten.
- No AI model or vendor names and no personal name or email appear in public text.

---

## BLOCKERS

### A. Legal and provenance

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Notice and subtitle | **Done** | Full text in About and the README. The footer text is always visible on desktop and mobile. The subtitle and `<title>` read "Arda: a fan atlas of the Third Age". |
| 2 | Drúadan and Trollshaws redrawn | **Done** | Redrawn from the text by the new `tools/generalize/redraw_text.py`. Drúadan lies about Eilenach and Amon Dîn; the Trollshaws lie between the Hoarwell and the Loudwater, north of the Road. The "none of its shapes are kept" claims are corrected. |
| 3 | Shapes hugging the trace | **Done** | Chetwood, Old Forest, Woods of Lindon, Tolfalas, Lórien, Eryn Vorn, Fangorn and Nîn-in-Eilph are rebuilt. The overlay check is part of the audit. `GEO.COAST` is kept as an internal positions skeleton only; the drawn coast is `shores.js`. |
| 4 | Film-style Eye | **Done** | Barad-dûr is now an iron-crowned, pinnacled tower with red flame at a high window, in both the sprite and the 3D model. There is no floating eye and there are no horns. The "Sauron" label is unchanged. |
| 5 | Film-location analogues | **Done** | Replacements: Shire pasture from East Cork, bog from the Flow Country, the ash plain from Mælifellssandur, lava from Puʻu ʻŌʻō. All are open-licence. The NZ names are gone from About and from `docs/ANALOGUES.md`. |
| 6a | Trailers and commit identity | **Done** (identity **held**) | New commits carry no trailers and use a neutral project identity. The owner has not yet confirmed the final name and email. |
| 6b | Assistant instructions file | **Done** | Now neutral contributor notes in `docs/CONTRIBUTING.md`. The root file is no longer tracked. |
| 6c | Artifact-host mentions | **Done** | Removed from `README.md` and `build.js`. |
| 6d | Username and name in the registry and docs | **Done** | The registry URL is now relative (`./`). |
| 6 (flag) | Site URL and repo name contain the username | **Flagged** | Not acted on, as instructed. The README still links the Pages URL. |

### B. Geography

| # | Item | Status | Notes |
|---|---|---|---|
| 7 | Rivers climb or leave their valleys | **Done** | Rivers are carved along the same line that is drawn, pre-subdivided and calmed near mouths. The floor is measured from cross-section minima with a running minimum, capped at confluences and branches, and graded back from the mouth. All 48 rivers pass the rise and valley-floor rules. |
| 8 | Harlond | **Done** | Moved to (736.9, −608.0). River ports are in the audit. |
| 9 | River ends inland | **Done** | The Great River of Harad and the Southern River now reach the sea, and both are in the `anchors.json` mouths list. |
| 10 | Drawn rivers over the sea or straying | **Done** | The wiggle tapers out near mouths. Both rules are in the render gate. |
| 11 | Dol Amroth in the sea | **Done** | The rendered coast now follows the vector coast (signed distance within an 8-mi band). Every place is checked for rendered land. |
| 12 | Rendered vs vector coast | **Done** | All five regions are below 1% (most below 0.4%). |
| 13 | Audit | **Done** | See "Verification" above. |

### C. Look

| # | Item | Status | Notes |
|---|---|---|---|
| 14 | Minas Tirith spawn | **Done** | Spawns on the Pelennor before the Great Gate, facing the city. Night has stars, the Milky Way and the moon. Ground labels are de-overlapped, with text unchanged. |
| 15 | Gorgoroth meadow | **Done** | The grass mask excludes ash, arid ground, lava and paving. Flowers appear only in season. Mordor's sky carries reek and haze (fixed again in the final commit, where the sky had stayed blue). |
| 16 | Rohan too dry | **Done** | The grass base is green and tussock is reduced. Only the Wold and the Brown Lands stay tan, and Enedwaith is out of ARID. |
| 17 | Passes and walls | **Done** | Cut: High Pass, Redhorn Gate, Cirith Gorgor, Isenmouthe, Cirith Ungol and the Morgul pass. The Ephel Dúath and Ered Lithui are built up as walls. The pass and wall rule is in the render gate. |
| 18 | Lórien season | **Done** | Gold from autumn to spring, then green with yellow flowers in summer. The imagery refreshes when the season changes. |

## SHOULD-FIX

| # | Item | Status | Notes |
|---|---|---|---|
| 19 | Lamedon river order | **Held** | Involves a river rename, which touches the frozen labels. Waiting on the owner. |
| 20 | Gandalf at Caras Galadhon on 17 Feb | **Done** | |
| 21 | September 3018 ride | **Done** | Rohan, the Isen, the Greyflood, Sarn Ford, Bree and Crickhollow on the stated dates. |
| 22 | Radagast on Mid-year's Day | **Done** | A new journey and event, before Orthanc on 10 July. |
| 23 | Homeward journey | **Done** | Farewells 14 Aug, Helm's Deep 18 Aug, Bywater 2 Nov, the battle 3 Nov. |
| 24 | Dawnless Day pin | **Done** | Moved to Dunharrow. |
| 25 | Glorfindel | **Done** | Finds the party on 18 Oct and reaches the Ford on 20 Oct. Has his own sprite. The start is marked as approximate. |
| 26 | Hobbit dates estimated | **Done** | |
| 27 | Fell beasts from 1 Dec 3018 | **Done** | Marked as an estimate. |
| 28 | About overstates source checking | **Done** | Now reads "positions are approximate; source checks in progress". |
| 29 | Source grading | **Done** | A "Tolkien's drafts / later sources" tier; Baynes is graded "position from map". A distant-features table marks drafts versus ours. |
| 30 | Map attribution | **Done** | Compact attribution with LINZ CC BY 4.0, Copernicus, NASA GIBS and Natural Earth. |
| 31 | Analytics disclosed | **Done** | One GoatCounter line added to About. |
| 32 | Minas Tirith setting | **Done** | Finer far mesh (321 samples). The city and Mindolluin show from the Pelennor. |
| 33 | Mordor surface | **Done** | Ash-plain noise replaces the blocky stain. Lava is confined to Orodruin's flanks. |
| 34 | Edoras ground view | **Partial** | Done: Edoras stands on its hill (75 m) with an earth wall, houses no longer float, and the White Mountains rise to the south. Not done: longhouse building forms. |
| 35 | Shire | **Partial** | Done: hedgerows and copses in the farmland, and a raised Hill (85 m) with smials. Not done: trees on the ground still look fairly uniform. |
| 36 | Pelennor ground | **Done** | Fewer, irregular orchards. The city is visible from the fields. |
| 37 | Forest rendering | **Done** | Canopy mottling at mid zoom. The redrawn outlines give ragged edges. |
| 38 | Sprite scale on the globe | **Held** | Possibly a deliberate round 3 choice. Waiting on the owner. |
| 39 | Argonath gorge | **Done** | Cliffs follow the drawn Anduin. The final commit fixed the walls so the river no longer climbs into the gorge. |
| 40 | Dawnless Day without weather | **Done** | A "lore-dark" map tint is drawn even with weather off. |

## MINOR

| # | Item | Status | Notes |
|---|---|---|---|
| 41 | Carrock | **Done** | Moved to (547, 55.1), in the river. |
| 42 | Barad-dûr spur | **Done** | A "Barad-dûr spur" ridge was added. |
| 43 | Enchanted River | **Done** | Now rises at (663, 49.8), on the mountains' southern flank. |
| 44 | Lake-end hooks | **Done** | Celduin, both Nurn rivers and the Red River end cleanly. The overshoot vertex was dropped rather than trimmed, so each river still meets its lake. |
| 45 | Cerin Amroth | **Done** | Moved into the Naith at (451.2, −244.4). |
| 46 | Graft fade comment | **Done** | The `reshape.py` comment now matches the code. |
| 47 | Minas Tirith Baynes rows | **Done** | The sources note records which row is used. |
| 48 | Balrog horns | **Done** | Removed. |
| 49 | Orthanc light | **Done** | Marked as ours. |
| 50 | "Well, I'm back." | **Done** | Paraphrased. |
| 51 | Orodruin "shattered ruin" | **Done** | Marked as "our staging" in the description text. |
| 52 | Data tidy | **Partial** (label merge **held**) | Done: Enedwaith is in GRASS only, and the Havens pin sits at Mithlond. Held: merging the duplicate DRUWAITH IAUR label waits on the owner because labels are frozen. |
| 53 | Favicon | **Done** | An inline SVG favicon; no more 404. |
| 54 | Console warnings | **Partial** | Done: no fog on the globe, so the calculateFogMatrix warning is gone. Skipped: the WebGL READ-usage buffer warnings. |
| 55 | Mobile timeline | **Done** | Fixed for 390×844. |
| 56 | Stale coordinate HUD | **Done** | Shows the map centre until the pointer moves. |
| 57 | Peak oddities | **Done** | The terrain hole east of Gundabad is filled. Halifirien is now a beacon hill of 320 m. |
| 58 | Self-hosted fonts | **Skipped** | Optional; not done this round. |

---

## Summary

| Status | Count | Items |
|---|---|---|
| Done | 51 | |
| Partial | 4 | 34, 35, 52, 54 |
| Held for the owner | 2 | 19, 38 (plus the 52 label merge and the 6a identity) |
| Skipped | 1 | 58 |
| Flagged, not acted on | 1 | the site URL and repo name |

**Suggested for round 5**
- Longhouse forms at Edoras.
- Irregular tree placement in the Shire.
- The WebGL READ-usage warnings.
- Self-hosted fonts.
- Items 19, 38 and 52 once the owner decides.
