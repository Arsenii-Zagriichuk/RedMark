# RedMark: Person 2 plan (data and drone matcher)

As of Fri 13 Nov 2026. Shared [team plan](team-plan.md) (it wins if this file disagrees), [project document](project-document.md) and [glossary](../GLOSSARY.md).

## Your role

You own the map data everyone builds on and the drone position fix at Jezero. You have the best GPU and already have the 23 GB Gale photo map, so the heavy data and the GPU matcher sit with you. You also run GPU batches for Person 3's stage 2 attempt. Most of the data work happens tonight; the drone matcher runs during the build.

**How to read the tickets.** "Blocked by" is what must be done before a ticket starts. Stub files come with the repo, so "Needs to finish" lists the real data from other people that a ticket needs before it counts as done. When that real data is due at the same hour as your ticket, your ticket is done once it works on the stub; the real file must then show up within an hour of landing, with no code change. Hours are from the start of the 24-hour clock (H0). From H0 each ticket's live status is its GitHub issue; this file is the brief and is not edited during the build. "Status" is the issue's triage label: `ready-for-agent` tickets can be built by an agent end to end, `ready-for-human` tickets need you, though an agent can draft for them.

## Your ticket cycle

Every ticket follows the [ticket cycle](team-plan.md#the-ticket-cycle-matt-pococks-skills): claim the issue, worktree branch, `/implement <issue>`, `code-review`, then a pull request written with the `pr` skill. Each crop, layer and match puts its overlay image in the pull request's Evidence section.

**Test seams.** When `/implement` asks which seams to test, answer from this list. Use small fixture crops committed to the repo (under the 5 MB limit), since CI has no `data/` folder.

- Crop and reproject: a point with known coordinates in the source file lands at the expected place in the crop, and Jezero map metres come out as ground metres.
- Layer writer: every layer it writes validates against the layer schema, with resolution and source in the metadata.
- Drone pipeline on one fixture frame: the frame with a known position comes back within the expected error, through the shared scorer.
- Same frame as the key: an answer-key frame scored against itself gives zero error, which proves the matcher and the key share a frame.

**Skills you'll lean on.** `research` for file-format questions (the PDS Helicam bundles, Ingenuity's camera model for straightening the fisheye, the THEMIS 30S120E file) while your agents keep building. `diagnosing-bugs` when the matcher won't lock on or a layer sits metres off. `code-review` on Person 3's scorer pull request, since your numbers depend on it.

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

About 15 GB still to fetch; the Gale photo map is already done.

- [x] [Gale photo map, 25 cm](https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/MSL_Gale_Orthophoto_Mosaic_25cm_v3.tif) (23 GB): already downloaded.
- [Gale 3D terrain, 1 m](https://planetarymaps.usgs.gov/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif) (3.6 GB), for slope and the crops. Person 3 already has the full file and can copy it to you by USB.
- THEMIS thermal inertia, 30S120E tile ([page](https://astrogeology.usgs.gov/search/map/themis_thermal_inertia_mosaic_quantitative_30s120e_100mpp)). This is the right tile: 30S060E, linked in the project document, covers only 60°E to 120°E and misses Gale at about 137.8°E. The 30S120E page did not load when checked; by the naming pattern the file is `THEMIS_TI_Mosaic_Quant_30S120E_100mpp.cub` (ISIS format, which GDAL reads; the neighbouring tile is about 2.5 GB).
- CRISM mineral maps for the walk area: [CRISM archive](https://pds-geosciences.wustl.edu/missions/mro/crism.htm) or the [map search](https://ode.rsl.wustl.edu/mars/).
- Curiosity chemistry (APXS, ChemCam): [MSL archive](https://pds-geosciences.wustl.edu/missions/msl/).
- [Jezero photo map, 25 cm](https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first): a 3.2 GB compressed GeoTIFF or the 6.9 GB TIF ([direct link](https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first.tif)).
- Ingenuity Navcam photos for a few flights, higher flights first, plus one or two extra flights used only for tuning: [Mars 2020 archive page](https://pds-geosciences.wustl.edu/missions/mars2020/), then "Helicam Bundles at the PDS Imaging Node".
- [JPL matcher weights](https://huggingface.co/dpisanti/mbl-mars).
- [LoFTR code](https://github.com/zju3dv/LoFTR), and [LightGlue](https://github.com/cvg/LightGlue) as the fallback.
- Python packages: GDAL/rasterio, scikit-image, numpy, OpenCV, and PyTorch with GPU support (the lock file's GPU group).
- Matt Pocock's skills for your agent tool (install commands in the [team plan](team-plan.md#the-ticket-cycle-matt-pococks-skills)).

## Tonight, before the clock

- [ ] Start the remaining downloads (THEMIS, CRISM, chemistry, Jezero, Ingenuity, weights, code), and get the Gale terrain from Person 3 by USB.
- [ ] P2-04 first: Person 4 needs the Jezero pack to hand-match the answer key tonight.
- [ ] With Persons 3 and 4, pick the walk area and habitat: inside the Gale photo map and terrain, off Curiosity's track, with Mount Sharp, Mishe Mokwa, Texoli and the crater rim in view, base camp on firm open ground, science targets within 2 km of the habitat. Check the choice against Curiosity's full traverse.
- [ ] Install Matt Pocock's skills. Clone the repo as soon as Person 1 says it is ready, and run the smoke test. Until then, only downloads and the Jezero pack; crop scripts go into the repo, not loose on your machine.
- [ ] P2-01: build the walk-area crop pack and put it on the USB drive or shared folder.
- [ ] Install PyTorch with GPU support and check that LoFTR loads JPL's weights on one image pair.
- [ ] Read the AI-use and pre-work rules when the guides come out on Fri 13 Nov; scale back pre-work if they require it.

## Tickets

### P2-01: Walk-area crop pack

**What to build:** Everything the team needs about the Gale walk area, cut out of the big files and lined up on one map: the site config plus crops of the photo map, the terrain, THEMIS, CRISM and the Curiosity chemistry points, each with an overlay image on the base map. Delivered on the USB drive or shared folder so nobody downloads the big files at the venue.

**Blocked by:** Walk-area decision (tonight, with Persons 3 and 4), P1-01 (the repo and the site-config contract).

**Due:** Before H0.

**Status:** ready-for-agent

- [ ] Every crop is in the base map's projection and covers the same bounds, with a margin for the 2 km walk radius.
- [ ] One overlay image per source, checked by eye; CRISM and THEMIS offsets from the HiRISE map are corrected or written down.
- [ ] A few rover positions from PLACES (Person 3 has the file), plotted on the base-map overlay, sit on Curiosity's tracks. This proves the map and the answer key share a frame.
- [ ] The site config holds projection, bounds, habitat, base camp and file paths (sol added by Person 4, targets added in P2-03).
- [ ] The data manifest lists each file's name, size, source link and checksum.
- [ ] Copies are on the USB drive or shared folder.

### P2-02: Base map tiles and slope (layer 1)

**What to build:** The base map and the slope layer in the agreed layer contract, so Person 1's map shows the real Gale ground and Person 4's route has slope to work with.

**Blocked by:** P2-01, P1-01.

**Due:** H4.

**Status:** ready-for-agent

- [ ] Person 1's map shows the real base map tiles in the right place.
- [ ] Slope in degrees from the 1 m terrain, with resolution and legend in the layer metadata.
- [ ] Overlay of slope on the photo map checked by eye.

### P2-03: Walkability and science layers (2 and 3)

**What to build:** Layer 2 (walkability): THEMIS loose sand vs solid rock at 100 m, plus a boxwork ridge map drawn from the 25 cm photos, because the 1 m terrain barely sees 1 to 2 m ridges. Layer 3 (science): CRISM mineral highlights (about 18 m), Curiosity chemistry points along its track, and the science-target list, including one ridge centre and one hollow that Curiosity did not reach.

**Blocked by:** P2-01, P1-01.

**Due:** H6 (Checkpoint 1).

**Status:** ready-for-agent

- [ ] Both layers in the agreed contract, each with resolution and source in its metadata.
- [ ] The ridge map is checked by eye against the photo in at least 3 sample areas.
- [ ] No science target sits on a spot Curiosity already drilled.
- [ ] The science targets are added to the site config.

### P2-04: Jezero pack for Person 4

**What to build:** What Person 4 needs to hand-match the drone answer key on a light machine: photos from 3 to 5 of Ingenuity's higher flights, plus crops of the Jezero photo map around each flight path. Pick flights over textured ground first, plus one of the last flights over sand ripples for hard mode.

**Blocked by:** None (can start immediately).

**Due:** Tonight, before anything else.

**Status:** ready-for-agent

- [ ] At least 30 candidate frames, so 20 good ones can be keyed.
- [ ] Each flight's crop has a wide margin around the flight path.
- [ ] The crops are reprojected to a frame with true scale at Jezero's latitude (about 18.4°N), the same frame the drone matcher uses, so map metres are ground metres. The published map is true to scale only at the equator, which makes its east–west metres about 5% too long here.
- [ ] A frame list with flight number and file name goes with the pack.
- [ ] Delivered to Person 4 by shared folder or USB.

### P2-05: First drone fix

**What to build:** One Ingenuity frame placed on the Jezero photo map, end to end: straighten the fisheye, shrink the photo to the map's 25 cm scale, search a wide window of the map around the previous photo's position, match with LoFTR and JPL's weights on the GPU, and compute the position. The output is a fix result with an overlay image.

**Blocked by:** P1-01.

**Due:** H6 (Checkpoint 1).

**Status:** ready-for-agent

- [ ] The overlay shows the photo's outline on the map, checked by eye.
- [ ] The result is a fix result in the agreed contract, with time per fix recorded.
- [ ] LightGlue runs as a drop-in fallback on the same frame.

### P2-06: Drone test at Jezero

**What to build:** Run the drone matcher on every answer-key frame and report the result against JPL's benchmark. This is one of the two real position claims in the pitch.

**Blocked by:** P2-05, P4-01, P3-09 (the shared scorer).

**Due:** H12 (Checkpoint 2).

**Status:** ready-for-agent

- [ ] A test summary, written through the shared scorer: median error, share within 1, 5 and 10 m next to JPL's 89.4% within 5 m and 99.8% within 10 m.
- [ ] The same numbers split by terrain type (textured, plain); hard-mode frames over sand ripples reported separately.
- [ ] A fix result and overlay image for every frame, ready for the Test lab.
- [ ] Tuning uses only flights with no answer-key frames. Frames from the same flight overlap, so tuning on a key flight's other frames would see the key's ground.
- [ ] Person 4 checks 3 overlays by eye against their tie-points.

### P2-07: Gale drone fix (simulated)

**What to build:** The drone fix for the Gale demo. Cut top-down views from the Gale photo map, draw suit markers in, and run them through the real matcher; add the astronaut-detection mock-up; produce images and cached results for Person 1's Drone fix screen. Because these views come from the same map they are matched to, they show the pipeline, not accuracy: label them simulated and report no numbers from them.

**Blocked by:** P2-05, P2-02.

**Due:** H16.

**Status:** ready-for-agent

- [ ] Cached results and images for at least one drone fix along the demo route.
- [ ] Every image and result is labelled simulated.
- [ ] No accuracy numbers are produced from these views.

### P2-08: GPU jobs for stage 2

**What to build:** Run Person 3's stage 2 matching batches on your GPU and hand back the results, so Person 3's attempt at a real ground fix is not limited by their machine.

**Blocked by:** P3-07's first batch, due at about H6. (P3-07 itself finishes only after your results come back, so wait for the batch, not the whole ticket.)

**Due:** By H12, when Person 3 makes the go or no-go call.

**Status:** ready-for-agent

- [ ] A simple handoff agreed with Person 3: an input folder, an output folder, one command.
- [ ] Each batch's results returned with the run time.

## Handoffs

| You give | To | By |
| --- | --- | --- |
| Jezero pack | Person 4 | Tonight, first |
| Walk-area crop pack and site config | Everyone | Before H0 |
| Base map tiles and slope | Persons 1 and 4 | H4 |
| Layers 2 and 3, science-target list | Persons 1 and 4 | H6 |
| Drone test summary and fix results | Persons 1 and 4 | H12 |
| Stage 2 batch results | Person 3 | As requested, by H12 |
| Gale drone-fix images | Person 1 | H16 |

| You get | From | By |
| --- | --- | --- |
| Repo, contracts, stubs | Person 1 | Tonight, first |
| Full Gale terrain file, and the PLACES file for the frame check | Person 3 | Tonight |
| Drone answer key | Person 4 | Before H0, H6 at the latest |
| Shared scorer | Person 3 | H3 |
| Replayed sol for the site config | Person 4 | Tonight |
| Stage 2 batches | Person 3 | From about H6 |

## If it slips

- Switch the matcher to LightGlue.
- Use fewer flights, higher ones first.
- Hand-trace the ridge map along the demo route only.
- Serve cached match results in the demo.
