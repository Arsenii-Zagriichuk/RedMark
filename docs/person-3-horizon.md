# RedMark: Person 3 plan (horizon matcher and location quality)

As of Fri 13 Nov 2026. Shared [team plan](team-plan.md) (it wins if this file disagrees), [project document](project-document.md) and [glossary](../GLOSSARY.md).

## Your role

You own the real position result at Gale and the location-quality layer (layer 5), which is what sets RedMark apart from other teams. Stage 1 compares the helmet camera's skyline with horizon lines calculated from the 3D terrain; its most reliable output is heading, and published horizon methods reach about 100 m in position. You also make one time-boxed attempt at a real stage 2 ground fix, with heavy matching run on Person 2's GPU. And you write the shared scorer that both test summaries go through, so the drone and horizon numbers mean the same thing.

**How to read the tickets.** "Blocked by" is what must be done before a ticket starts. Stub files come with the repo, so "Needs to finish" lists the real data from other people that a ticket needs before it counts as done. When that real data is due at the same hour as your ticket, your ticket is done once it works on the stub; the real file must then show up within an hour of landing, with no code change. Hours are from the start of the 24-hour clock (H0). From H0 each ticket's live status is its GitHub issue; this file is the brief and is not edited during the build. "Status" is the issue's triage label: `ready-for-agent` tickets can be built by an agent end to end, `ready-for-human` tickets need you, though an agent can draft for them.

## Your ticket cycle

Every ticket follows the [ticket cycle](team-plan.md#the-ticket-cycle-matt-pococks-skills): claim the issue, worktree branch, `/implement <issue>`, `code-review`, then a pull request written with the `pr` skill. Each match puts its overlay image (photo skyline on the calculated skyline) in the pull request's Evidence section.

**Test seams.** When `/implement` asks which seams to test, answer from this list. Expected values come from worked examples, never from recomputing them the way the code does.

- Scorer: 359° against 1° is a 2° heading error; a 3 m by 4 m offset is a 5 m error; exactly 5 m counts as within 5 m; the median of a known list.
- Horizon renderer on made-up terrain: a wall of known height and distance gives its known elevation angle; flat ground 60 km away sits about 0.5° below the flat-world horizon, because of Mars's curvature.
- Skyline matcher: a calculated skyline turned by a known heading comes back with that heading.
- Hidden-pile isolation: the test fails if any code outside the scoring scripts points at the hidden-pile folder.

**Skills you'll lean on.** `research` for fact questions (which Navcam label fields give camera pointing and field of view, the PLACES file layout) while your agents keep building. `diagnosing-bugs` when a fix comes back wrong and the overlay doesn't say why. `/grill-with-docs` with Person 2 before the scorer is written, since both test summaries depend on what it counts as an error.

## Team context

Copied from the [team plan](team-plan.md). If the two ever differ, the team plan wins.

### Who owns what

| Person | Role | Machine | Folders |
| --- | --- | --- | --- |
| 1 | App, service shell and submission | | `app/`, `service/`, `pitch/`, and the repo root (AGENTS.md, CI, lock files, `.claude/`) |
| 2 | Data and drone matcher | Best GPU; has the 23 GB Gale photo map | `prep/`, `sites/`, `locate/drone/` |
| 3 | Horizon matcher and location quality | | `locate/horizon/`, `locate/ground/`, `layers/location_quality/`, and the shared scorer in `contracts/scoring/` |
| 4 | Route and simulation | Lightest machine | `route/`, `sim/`, `conditions/` |

Shared folders: `contracts/` (a change needs a review from the other side), `results/` and `cache/` (each producer writes only its own subfolder). The `data/` folder never goes into git. Its location comes from one setting, `REDMARK_DATA`, so every worktree reads the same copy.

### Gates

At each gate all four people stop, merge to main and run the smoke test together.

| Hour | Gate | What must be true |
| --- | --- | --- |
| Tonight | Repo ready | Person 1 creates the repo with folders, contracts, stubs, the smoke test and every ticket as a GitHub issue; everyone clones it and installs the skills before writing any code |
| H0 | Contracts confirmed | Any change to the contracts agreed in 15 minutes, including what the uncertainty circle and confidence mean; every agent briefed from AGENTS.md |
| H6 | Checkpoint 1 | Real Gale map, layers 1 to 3 and a route in the app; both matchers return a first fix |
| H12 | Checkpoint 2 | Real test numbers in the Test lab; layer 5 in; stage 2 go or no-go |
| H14 | Last new work starts | H14 to H18 is for finishing, not starting |
| H18 | Feature freeze | Only fixes, cached results and the pitch from here |
| H22 | Record | 2-minute video and 30-second cut |
| H24 | Submit | Project page, videos and References in, before pages close Sun 15 Nov, 23:59 local |

### Contracts

All positions are metres in each site map's own projection, the same frame as Curiosity's recorded positions. Errors and distances are ground metres; Jezero's crops are reprojected so that map metres are ground metres there too (see the team plan). Each contract is a JSON Schema in `contracts/`; the TypeScript types and Python models are generated from it.

| Contract | Producer | Used by | Contents |
| --- | --- | --- | --- |
| Site config (Gale, Jezero) | 2 (sol from 4) | All | Projection, walk-area bounds, habitat, base camp, science targets, checkpoints, file paths relative to `REDMARK_DATA`, replayed sol |
| Layer files | 2 (layers 1 to 3), 3 (layer 5) | 1, 4 | Map tiles in local metres plus metadata: name, units, resolution in metres, legend, source |
| Route request and response | 4 (engine), served by 1 | 1, 4 | In: start, goal, mode (fastest, science, cart), uncertainty circle in metres, limits. Out: path, time per leg, total time, walk-back margin, every limit check, checkpoints |
| Fix result | 2 (drone), 3 (horizon, ground) | 1, 4 | Photo id, site, method, estimated position, heading, uncertainty circle (radius in ground metres), confidence %, time per fix, terrain type, simulated (required, no default), overlay image. Tested photos also carry true position, true heading and error |
| Scorer | 3 (2 reviews) | 2, 3 | One shared implementation of position error (ground metres), heading error (wraps at 360°), median and share within 1, 5 and 10 m |
| Test summary | 2, 3 | 1, 4 | Median error, share within 1, 5 and 10 m, heading error, split by terrain type; written only through the scorer, with the script, commit and input checksums that produced it |
| Walk simulation | 4 | 1 | In: route, fix schedule, break-it flags. Out: one step per time tick with true and estimated position, circle, active sources, events, mode (normal, offline, lost) |
| Conditions | 4 | 1, 4 | Local time, daily radiation, temperature, pressure, dust (measured or estimated), sun direction, sunset |
| Demo cache | Each producer | 1 | The saved response for every step of the 3-minute script, due by H16 |

### Agent rules (everyone)

1. Every agent reads AGENTS.md at the repo root first. CLAUDE.md is the single line `@AGENTS.md`, so Claude Code and Codex read the same rules.
2. Every ticket goes through the ticket cycle in the team plan: claim the issue, work in a worktree branch, build with `/implement` (tests first at agreed seams, then `code-review`), and open a pull request written with the `pr` skill.
3. Each agent works on its own branch (a git worktree) and only inside its owner's folders; a hook and CI block edits outside them. A contract change is one pull request that both sides approve.
4. Stubs first: the repo starts with a fake file for every contract, so nobody waits for real data. No code is written outside the repo.
5. Merge to main at least every 2 hours, through a pull request with green CI. Main must pass the smoke test.
6. No hand-typed numbers. Every number in the app, slides or page comes from a results file a script wrote, and each results file records the script, commit and inputs that wrote it.
7. Hidden piles are never read by tuning code; a test fails if anything outside the scoring scripts points at them.
8. Every crop, layer and match writes an overlay image. It goes in the pull request's Evidence section, and a person looks at it before it merges.
9. Simulated results are labelled as simulated everywhere they appear.

### Ticket index (all four people)

From H0 the GitHub issue is each ticket's live status. "ready-for-human" tickets need a person; agents can still draft for them.

| ID | Ticket | Owner | Blocked by | Needs to finish | Due |
| --- | --- | --- | --- | --- | --- |
| P1-01 | Create the repo: folders, contracts, stubs, smoke test, tickets as issues | 1 | None | | Tonight, first |
| P1-02 | Service shell and demo cache | 1 | P1-01 | | H3 |
| P1-03 | Map view on the real Gale map | 1 | P1-01 | P2-02 | H6 |
| P1-04 | Planning screen | 1 | P1-02, P1-03 | P4-03 | H8 |
| P1-05 | Walk view | 1 | P1-04 | P4-05, P4-02 | H12 |
| P1-06 | Test lab | 1 | P1-02 | P2-06, P3-03 | H12 |
| P1-07 | Simulation controls and Lost mode | 1 | P1-05 | P4-06, P3-06 | H15 |
| P1-08 | Photo checkpoint | 1 | P1-05 | P3-04 | H15 |
| P1-09 | Drone fix and Target preview | 1 | P1-03 | P2-07, P2-03 | H17 |
| P1-10 | Offline demo | 1 | P1-04 to P1-09 | Every producer's demo cache (H16) | H18 |
| P1-11 | Screen recordings and visor mockup | 1 | P1-10 | | H21 |
| P1-12 | Slides and live pitch | 1 | None | P2-06, P3-03 | Draft H16, final H20, rehearse to H22 |
| P1-13 | Videos | 1 | P1-11, P1-12 | | H23 |
| P1-14 | Project page and submit | 1 | None | P1-13 | H24 |
| P1-15 | Guardrails: CI, hooks, branch protection | 1 | P1-01 | | H2 |
| P2-01 | Walk-area crop pack | 2 | Walk-area decision, P1-01 | | Before H0 |
| P2-02 | Base map tiles and slope (layer 1) | 2 | P2-01, P1-01 | | H4 |
| P2-03 | Walkability and science layers (2 and 3) | 2 | P2-01, P1-01 | | H6 |
| P2-04 | Jezero pack for Person 4 | 2 | None | | Tonight, first |
| P2-05 | First drone fix | 2 | P1-01 | | H6 |
| P2-06 | Drone test at Jezero | 2 | P2-05, P4-01, P3-09 | | H12 |
| P2-07 | Gale drone fix (simulated) | 2 | P2-05, P2-02 | | H16 |
| P2-08 | GPU jobs for stage 2 | 2 | P3-07's first batch (about H6) | | By H12 |
| P3-01 | Horizon grid | 3 | Walk-area decision, P1-01 | | H4 |
| P3-02 | First horizon fix | 3 | P3-01, P1-01 | P3-09 | H6 |
| P3-03 | Horizon test on the hidden pile | 3 | P3-02, P3-09 | | H12 |
| P3-04 | Demo fixes | 3 | P3-03 | | H14 |
| P3-05 | Layer 5: landmark visibility | 3 | P3-01, P1-01 | | H10 |
| P3-06 | Layer 5 final | 3 | P3-03, P3-05 | P4-03 | H14 |
| P3-07 | Stage 2 attempt | 3 | P2-01, P1-01 | P2-08 | Go or no-go H12 |
| P3-08 | Stage 2 result | 3 | P3-07 | | H14 |
| P3-09 | Shared scorer | 3 | P1-01 | | H3 |
| P4-01 | Drone answer key | 4 | P2-04, P1-01 | | Before H0 (H6 at the latest) |
| P4-02 | Conditions for the replayed sol | 4 | Sol decision, P1-01 | | H8 |
| P4-03 | Fastest safe route | 4 | P1-02 | P2-02, P2-03 | H8 |
| P4-04 | Science and cart routes, walk-back and daylight | 4 | P4-03, P4-02 | | H10 |
| P4-05 | Walk simulation | 4 | P1-02 | P2-06, P3-03 | H12 |
| P4-06 | Break-it scenarios | 4 | P4-05, P4-04 | | H14 |
| P4-07 | Location-aware routing | 4 | P4-03, P3-05 | P3-06 | H14 |

## Downloads and installs

About 6 GB plus photos.

- [x] [Gale 3D terrain, 1 m](https://planetarymaps.usgs.gov/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif) (3.6 GB): downloaded. You need the full file, not a crop, because the skyline comes from terrain far outside the walk area. Copy it to Person 2 by USB. What's in it: 32,980 × 57,440 heights at 1 m, equirectangular on the Mars 2000 sphere, covering about 137.12–137.68°E and 4.13–5.10°S (33 × 57 km). As 32-bit floats it is about 7.6 GB in memory, so read it in windows.
- [x] [MOLA terrain, 463 m](https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif) (2 GB): downloaded, and needed. The Gale file stops short of the top of Mount Sharp and of most of the crater rim, so MOLA supplies the far skyline.
- Curiosity Navcam photos with labels for sols 4600 to 4709: [processed images](https://pds.nasa.gov/data/pds4/releases/img/msl_navcam_processed-20260317/). A few hundred frames is enough. The March 2026 release covers sols up to 4709; check for a newer release before using a later sol.
- Rover positions, as the answer key: [PLACES archive](https://planetarydata.jpl.nasa.gov/img/data/msl/msl_places/).
- For the stage 2 attempt: [Navcam mosaics](https://pds.nasa.gov/data/pds4/releases/img/msl_navcam_mosaic-20260317/) (whether top-down mosaics exist for the boxwork sols is not confirmed), plus the photo-map crop from Person 2.
- Python packages: numpy, OpenCV, GDAL/rasterio (install without the GPU group; stage 2's heavy matching runs on Person 2's machine).
- Matt Pocock's skills for your agent tool (install commands in the [team plan](team-plan.md#the-ticket-cycle-matt-pococks-skills)).

## Tonight, before the clock

- [x] Download the terrain. The Gale file doesn't reach the crater rim or the top of Mount Sharp, so MOLA is in.
- [ ] Download the Navcam frames, and the PLACES positions for those sols. Give Person 2 the terrain file and the PLACES file.
- [ ] Check the height offset between MOLA and the Gale terrain where they overlap, before joining them.
- [ ] With Persons 2 and 4, pick the walk area: which candidate spots can see the upper Mount Sharp peak, Mishe Mokwa, Texoli and the crater rim.
- [ ] Install Matt Pocock's skills. Clone the repo as soon as Person 1 says it is ready, and run the smoke test. Until then, only downloads; the horizon code goes into the repo.
- [ ] Split the frames into a tuning pile and a hidden pile by stretch of the traverse, before anything is tuned: consecutive rover positions stay on the same side. Curiosity often stays parked for several sols, so splitting by sol would put frames of the same spot on both sides.
- [ ] Look through the Navcam mosaic release for top-down products from the boxwork sols, to judge whether stage 2 is worth attempting.
- [ ] Read the AI-use and pre-work rules when the guides come out on Fri 13 Nov; scale back pre-work if they require it.

## Tickets

### P3-01: Horizon grid

**What to build:** Horizon lines calculated from the full Gale terrain, plus MOLA for the far skyline, for a grid of candidate spots across the walk area, cached to disk. Each spot gets its 360° skyline: the elevation angle of the horizon in every direction. Two things decide whether this finishes by H4:

- **Several scales.** Use the 1 m terrain near the spot, a coarser copy further out, and MOLA beyond the edge of the Gale file. Ray-casting at 1 m all the way to a rim 40 to 80 km away is too slow for a whole grid.
- **Curvature.** Mars is small: 60 km away, the surface sits about 530 m below a flat plane, about 0.5° of elevation, or roughly 10 Navcam pixels. Include it, or the far skyline comes out too high.

**Blocked by:** Walk-area decision, P1-01.

**Due:** H4.

**Status:** ready-for-agent

- [ ] The grid covers the whole walk area; grid spacing and computing time are written down.
- [ ] Terrain out to the crater rim is included, so far landmarks shape the skyline, and the ray casting includes Mars's curvature.
- [ ] One calculated skyline is checked by eye against a real Navcam panorama from a nearby spot.

### P3-02: First horizon fix

**What to build:** One Navcam frame turned into a position fix, end to end: extract the skyline from the photo, take the camera's pointing and field of view from the image labels, match against the cached horizons, and return position, heading and an uncertainty circle as a fix result with an overlay image (photo skyline on top of the matched calculated skyline). A Navcam frame sees only about 45° of skyline, so also try combining the frames taken from one rover position into a wider skyline, the way an astronaut turns on the spot.

**Blocked by:** P3-01, P1-01.

**Needs to finish:** P3-09 (the shared scorer, for the heading error).

**Due:** H6 (Checkpoint 1).

**Status:** ready-for-agent

- [ ] Output is a fix result in the agreed contract, with time per fix recorded.
- [ ] The overlay shows the photo skyline against the best-matching calculated skyline.
- [ ] Heading error is computed through the shared scorer against the camera pointing in the image labels.

### P3-03: Horizon test on the hidden pile

**What to build:** Run the horizon matcher on every frame of the hidden pile and score it against the PLACES positions. This is one of the two real position claims in the pitch.

**Blocked by:** P3-02, P3-09.

**Due:** H12 (Checkpoint 2).

**Status:** ready-for-agent

- [ ] A test summary, written through the shared scorer: median position error (m), heading error (degrees), time per fix (s).
- [ ] The same numbers split by terrain type, and by ridge top or open ground versus hollow.
- [ ] A fix result and overlay image for every frame, ready for the Test lab.
- [ ] The hidden pile was never read by tuning code; you sign off the numbers before they go to Persons 1 and 4.

### P3-04: Demo fixes

**What to build:** Cached fixes for the 3 to 5 frames the demo uses in the Photo checkpoint and the Test lab, including one honest weak case.

**Blocked by:** P3-03.

**Due:** H14.

**Status:** ready-for-agent

- [ ] Each demo frame has its fix result and overlay in the demo cache.
- [ ] At least one frame is a weak case (for example a hollow where nearby ridges hide the skyline).

### P3-05: Layer 5, landmark visibility

**What to build:** The first version of the location-quality layer: for each map cell, which landmarks are visible (the upper Mount Sharp peak, Mishe Mokwa, Texoli, the crater rim), combined into one score, delivered to Person 1's map and Person 4's route.

**Blocked by:** P3-01, P1-01.

**Due:** H10.

**Status:** ready-for-agent

- [ ] Layer files in the agreed contract, with resolution (about 1 m) in the metadata.
- [ ] One mask per landmark plus the combined score.
- [ ] Spot-checked: ridge tops score higher than hollows near tall ridges.

### P3-06: Layer 5 final

**What to build:** The full location-quality layer: landmark visibility combined with the error map from the horizon test (by terrain type), checkpoint candidates on ridge tops and open ground, and lost-mode landmark directions along Person 4's route, such as "keep the upper Mount Sharp peak on your left".

**Blocked by:** P3-03, P3-05.

**Needs to finish:** P4-03 (the route the directions follow).

**Due:** H14.

**Status:** ready-for-agent

- [ ] The error map comes from the test results file, not from typed numbers.
- [ ] Checkpoint candidates are listed with their landmark view.
- [ ] Landmark directions are generated for each leg of the demo route.

### P3-07: Stage 2 attempt

**What to build:** One time-boxed try at a real ground fix at Gale: build an overhead view of the nearby ground from Navcam mosaics or stereo pairs, match it to the 25 cm photo-map crop, and score it against PLACES. Heavy matching runs on Person 2's GPU. If it works, stage 2 stops being simulated in the pitch.

**Blocked by:** P2-01, P1-01.

**Needs to finish:** P2-08 (GPU batches).

**Due:** Go or no-go at H12.

**Status:** ready-for-agent

- [ ] The first batch is in Person 2's input folder by about H6. P2-08 starts from that batch; it can't wait for this whole ticket, which needs P2-08's results to finish.
- [ ] By H12, either a set of matched frames with errors measured against PLACES through the shared scorer, or a written no-go with the reason.
- [ ] Frames used for scoring are not used for tuning.

### P3-08: Stage 2 result

**What to build:** The stage 2 result that the simulation and the app use. If the attempt worked: real numbers and fix results. If not: an error model based on JPL's published results (sub-metre on 264 real Perseverance locations), labelled simulated, handed to Person 4's simulation.

**Blocked by:** P3-07.

**Due:** H14.

**Status:** ready-for-agent

- [ ] A results file that says clearly whether stage 2 is measured or simulated.
- [ ] Person 4's simulation reads it without any typed numbers.

### P3-09: Shared scorer

**What to build:** The one implementation of the numbers both tests report, in `contracts/scoring/`: position error in ground metres, heading error, median, and the share of fixes within 1, 5 and 10 m, split by terrain type. Both test summaries (P2-06 and P3-03) and stage 2 are written only through it, so "within 5 m" means the same thing for the drone and the horizon results. It is small; build it test-first from worked examples.

**Blocked by:** P1-01.

**Due:** H3.

**Status:** ready-for-agent

- [ ] Heading error wraps around: 359° against 1° is 2°, not 358°.
- [ ] Position error is the horizontal distance in ground metres.
- [ ] "Within 5 m" includes exactly 5 m, and the same rule holds for 1 m and 10 m.
- [ ] Every test summary it writes records the script, commit and input checksums that produced it.
- [ ] Person 2 has reviewed the pull request, since their test summary depends on it.

## Handoffs

| You give | To | By |
| --- | --- | --- |
| Landmark-visibility advice for the walk area | Persons 2 and 4 | Tonight |
| Full Gale terrain file and the PLACES file | Person 2 | Tonight |
| Shared scorer | Person 2 | H3 |
| First horizon fix | Person 1 | H6 |
| Stage 2 batches for the GPU (the first one by H6) | Person 2 | From about H6 |
| Layer 5 (visibility) | Persons 1 and 4 | H10 |
| Horizon test summary and fix results | Persons 1 and 4 | H12 |
| Demo fixes, layer 5 final, landmark directions | Persons 1 and 4 | H14 |
| Stage 2 result or error model | Person 4 | H14 |

| You get | From | By |
| --- | --- | --- |
| Walk-area crop pack and site config | Person 2 | Before H0 |
| Repo, contracts, stubs | Person 1 | Tonight, first |
| Stage 2 batch results | Person 2 | By H12 |
| The route the landmark directions follow | Person 4 | H8 |

## If it slips

- Report heading alone if position is unstable, since heading is stage 1's most reliable output.
- Ship layer 5 as visibility only, without the error map.
- Stage 2 stays simulated and labelled.
- Use cached results for the demo frames.
