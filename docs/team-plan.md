# RedMark — 24-hour team plan

Nov 12, 2026 · @Maksym Shtymak · updated Nov 13, 2026 (see [Corrections and changes](#corrections-and-changes))

## Who owns what

Four people each run several agents, so this plan builds more for real than the outline in the [RedMark project document](project-document.md). Code is no longer the limit. Downloads, decisions, checking results by eye and merging are. Person 2 has the best GPU and Person 4 the lightest machine, so GPU work sits with Person 2 and Person 4 gets the work that needs little computing. Each person also has their own plan file with tickets, blockers and acceptance criteria: [Person 1](person-1-app.md), [Person 2](person-2-data-drone.md), [Person 3](person-3-horizon.md), [Person 4](person-4-route-sim.md). Words like fix, heading, uncertainty circle and hidden pile have one meaning each, set in [GLOSSARY.md](../GLOSSARY.md).

| Person | Owns | Delivers | Hands to others |
| --- | --- | --- | --- |
| 1 · App, service shell and submission | `app/`, `service/`, `pitch/`, the repo root (AGENTS.md, CI, lock files, `.claude/`), demo mode, offline demo, health of the main branch | All 8 key screens; the service the app talks to; a demo that runs from cache with the network off; the visor mockup image; the slides, the live pitch, both videos and the project page | Repo, stubs and tickets tonight, before anyone writes code; guardrails by H2; submission by H24 |
| 2 · Data and drone matcher (best GPU; already has the 23 GB Gale photo map) | `prep/`, `sites/`, `locate/drone/` | Layers 1–3; real drone fix at Jezero with test numbers; the Gale drone-fix screen; GPU runs for Person 3's stage 2 | Jezero pack to Person 4 and crops to everyone tonight; layers by H6; drone numbers by H12 |
| 3 · Horizon matcher | `locate/horizon/`, `locate/ground/`, `layers/location_quality/`, the shared scorer in `contracts/scoring/` | Real horizon fix at Gale with test numbers; the scorer both matchers use; layer 5; lost-mode landmark directions; real stage 2 if it works | Scorer by H3; layer 5 by H10, final by H14; horizon numbers by H12 |
| 4 · Route and simulation (lightest machine) | `route/`, `sim/`, `conditions/` | Drone answer key; walk, science and cart routes; the simulated walk behind the "break it" buttons; conditions strip | Answer key tonight; routes by H8–H10; simulation by H12 |

**Ground rules.**

- One owner per part. Agents write only inside their owner's folders.
- Every ticket goes through the same [ticket cycle](#the-ticket-cycle-matt-pococks-skills), built on Matt Pocock's skills.
- A rule counts only if a check makes it hard to break. Each agent rule below names its check.
- Only measured numbers go in the pitch, and each comes from a script in the repo. Simulated parts are labelled in the app and on the slides.
- Every demo step has a cached result, so a broken service never breaks the demo.
- Feature freeze at H18. New work starts only before H14.

**What the agents add to the scope.**

| Item | Project document | This plan |
| --- | --- | --- |
| Stage 2 ground fix at Gale | Simulated | Real attempt by Person 3, with matching on Person 2's GPU; go or no-go at H12; stays simulated and labelled if it fails |
| Cart route | Placed by hand | Real: its own cost map with no ridge crossings (Person 4) |
| Key screens | Drone fix and Target preview may be static | All 8 live; static images only as the fallback |
| Radio ranging | Described only | A simulated source in the walk simulation, labelled (Person 4) |
| Lost-mode directions | Written by hand | Generated from landmark visibility (Person 3) |
| Offline demo | A laptop stands in | The whole demo runs on the laptop from the cache with Wi-Fi off (Person 1). Installing the app as an offline web app is a stretch goal, not part of the demo |
| Still cut or described only | MARTIAN/Blender renders, the find-an-object test, the Earth drone test, matcher fine-tuning | Unchanged |

## Decisions to make tonight

The repo and the walk area come first: no code is written before the repo exists, and the walk area blocks every crop. The rest take minutes but stop agents from building on guesses.

| Decision | Who | By | Blocks |
| --- | --- | --- | --- |
| Create the shared repo: folders, AGENTS.md, the 9 contracts with stub files, the smoke test, the six plan documents and the glossary in a docs folder, and every ticket as a GitHub issue | Person 1; the others clone it | Tonight, first | Every code ticket (downloads can start before it) |
| Walk area and habitat: inside the Gale mosaic and DEM, off Curiosity's track, with Mount Sharp, the buttes and the rim in view; checked against Curiosity's full traverse | Persons 2, 3 and 4 | Tonight | All crops, layers, routes and the horizon grid |
| Replayed sol: between 4600 and 4709 (the Navcam archive's range), and covered by RAD and REMS too | Person 4 | Tonight | Conditions strip, daylight limit |
| What the uncertainty circle and the confidence % mean. Suggested: the circle is the 95% radius in ground metres; the confidence % is the share of tested fixes, for that method and terrain type, whose true position fell inside their circle | Persons 2, 3 and 4 | Before H0 | The fix result contract, the simulation's filter, the Walk view |
| One Python version and one lock file (suggested: Python 3.11 with uv), with PyTorch in an optional GPU group so only Person 2's machine installs it | Everyone | Tonight | Every agent's environment |
| Shared folder or USB drive for the crops | Everyone | Tonight | Handoffs at the venue |
| The rules on AI use and on work done before the clock | Everyone; Person 1 reads them first | Fri 13 Nov 2026, when the guides come out | How much prep code is allowed, and what the project page must say about agents |

## Everyone: shared setup and agent rules

Up to 16 agents in one repo will collide unless folders, contracts and merges are fixed before anyone starts.

**Setup**

- One shared repo with these owners: `app/`, `service/`, `pitch/` and the repo root (1); `prep/`, `sites/`, `locate/drone/` (2); `locate/horizon/`, `locate/ground/`, `layers/location_quality/`, `contracts/scoring/` (3); `route/`, `sim/`, `conditions/` (4); `contracts/`, `cache/` and `results/` shared. In `cache/` and `results/` each producer writes only its own subfolder.
- `data/` stays out of git, and so do the big map formats (`*.tif`, `*.cub`, `*.img`). A manifest in git lists each file's name, size, source link and checksum; the project page's References field is built from it.
- The data folder's location comes from one setting, `REDMARK_DATA`, and every path in the site configs is relative to it. A new worktree has no `data/` folder of its own, so this is what lets every agent's worktree read the same copy.
- One Python version and one lock file for everyone, plus Node LTS for the app. PyTorch sits in an optional GPU group, so Persons 1, 3 and 4 never install it.
- Person 2's crops travel on a USB drive or a shared folder, so the venue Wi-Fi is not the bottleneck.

**Agent rules and the checks that enforce them**

| Rule | Enforced by |
| --- | --- |
| 1. A repo-root `AGENTS.md` holds the contracts, the folder owners, the ticket cycle and the honesty rules. Every agent reads it first. | CLAUDE.md is the single line `@AGENTS.md`, so Claude Code and Codex read the same file |
| 2. Each agent works on its own branch (a git worktree) and only inside its owner's folders. A contract change is one pull request that both sides approve. | An owner-guard hook blocks an agent's edits outside its person's folders; CI fails a pull request that touches another owner's folders; `contracts/` is in CODEOWNERS, so a contract change needs a review. A git session guard stops two agents sharing one checkout and bans `git add -A` |
| 3. Stubs first. The repo Person 1 creates tonight starts with a fake file for every contract, so no one's agents wait for real data. No code is written outside the repo. | The smoke test validates every stub against its schema |
| 4. Merge to main at least every 2 hours, through a pull request. Main must pass a smoke test: the service starts, the app builds, every cached demo step loads. | CI runs on every pull request; branch protection requires it, so owners merge their own green pull requests and Person 1 doesn't have to review every merge |
| 5. No hand-typed numbers. Every number in the app, the slides or the page comes from a results file that a script wrote. | Every results file records the script, commit and input checksums that wrote it, and its schema requires them. The app reads numbers only from results files. Slide numbers come from `pitch/numbers.md`, which a script writes |
| 6. Hidden piles are off-limits for tuning. They sit in their own folder. | A test fails if any code outside the scoring scripts points at a hidden-pile folder |
| 7. Map work is checked by eye. Every crop, layer and match writes an overlay image on the base map, and a person looks at it before it merges. | The pull request's Evidence section (from the `pr` skill) holds the overlay; no overlay, no merge |
| 8. Simulated results are labelled as simulated everywhere they appear. | `simulated` is a required field with no default; the app shows fixes through one component that always prints the label |
| 9. Each person keeps 2–4 agents busy and spends their own time on decisions, checks and merges. | Nothing: this one is on you |

The Claude Code hooks (git session guard, owner guard, format on edit) and the CI workflow are ticket P1-15. The git session guard is copied from the FitCore repo (`.claude/hooks/git-session-guard.sh` and its tests). Hooks only see Claude Code sessions, so CI is the backstop for Codex and for hand edits.

## The ticket cycle (Matt Pocock's skills)

Every ticket, for every person and every agent, goes through the same loop using [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT licence). The point is that 16 agents stay aligned with the ticket, build test-first at agreed places, get reviewed against both the repo's standards and the ticket, and merge with evidence a person can check in a minute.

**Install (everyone, tonight).** Use one install per agent tool, never both: a plugin plus copied files gives you every skill twice.

- Claude Code: `claude plugin install mattpocock-skills@claude-plugins-official`
- Codex: `codex plugin marketplace add mattpocock/skills`, then `codex plugin add mattpocock-skills@mattpocock`

**Once per repo (Person 1, in P1-01).**

1. `/setup-matt-pocock-skills`: issue tracker **GitHub**, the **default triage labels** (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), and **single-context** domain docs (`GLOSSARY.md` at the root, decisions in `docs/adr/`). It writes the `## Agent skills` block into AGENTS.md.
2. Seed the root [GLOSSARY.md](../GLOSSARY.md) from the glossary in docs/.
3. `/to-tickets` on the ticket index: publish every ticket unchanged as a GitHub issue titled with its ID (`P3-02: First horizon fix`), with native blocking links, assigned to its owner and labelled `ready-for-agent` or `ready-for-human` as its Status says. From H0 the issue is a ticket's live status; the plan files are the brief and are not edited during the build.

**Per ticket.**

| Step | Skill | What happens |
| --- | --- | --- |
| 1. Pick | `/triage` ("what's ready for agents?"), or GitHub: open, `ready-for-agent`, no open blockers, yours | Assign yourself on the issue. That is the claim |
| 2. Branch | None | One worktree per agent: `git worktree add ../redmark-p3-02 -b feat/p3-02-first-horizon-fix origin/main` |
| 3. Align, only if the ticket is unclear or a contract changes | `/grill-with-docs` | At most 10 minutes. New terms go into `GLOSSARY.md`; a hard-to-reverse choice becomes an ADR in `docs/adr/`. A contract change is grilled with the other side present |
| 4. Unknowns, only if needed | `research`, `prototype` | `research` answers a fact question from primary sources (a PDS label field, a file format) as a cited note, in the background. `prototype` answers a design question with throwaway code |
| 5. Build | `/implement <issue>` | Agrees the test seams with you first (answer from the "Test seams" list in your plan), then works `tdd` red to green at those seams, runs typecheck and tests, runs `code-review`, and commits |
| 6. Stuck | `diagnosing-bugs` | When something is red, wrong or slow and the cause isn't obvious |
| 7. Review | `code-review` against `main` | `/implement` runs it; run it yourself after any hand changes. Standards axis: CODING_STANDARDS.md. Spec axis: the issue |
| 8. Pull request | `pr` | Body: Summary, Evidence (the overlay image or test output) and Merge danger, plus `Closes #<issue>` |
| 9. Merge | None | CI green and the owner has looked at the overlay: the owner squash-merges. A contract change also needs the other side's review |
| 10. Hand over | `/handoff` | Before an agent's context fills up, or when a fresh session takes over the ticket |

**Rules of the cycle**

- Branches are `<type>/<ticket>-<slug>` (`feat/p3-02-first-horizon-fix`); commits are `type: description (#<issue>)`, so `code-review` finds the ticket from the commit messages.
- Agree the seams before any test is written. Each person plan lists its seams; `tdd` tests only there, so testing effort goes on the numbers we pitch, not on every edge case.
- No pull request without the agreed tests passing and a `code-review` pass.
- Time-boxes: grilling 10 minutes, a research question 20 minutes.
- When a merge conflicts, the session that wrote the change resolves it, because it knows the intent.
- At the H6 and H12 gates each person may run `/retro` on their worst session. Adopt only fixes that take under 15 minutes, and prefer a new check over a new rule.
- Not used during the build: `/to-spec` (the project document is the spec), `/implement-spec` and `/wayfinder` (the tickets are already sliced, and their many subagents would swamp Person 4's machine), `/improve-codebase-architecture`.

**Review standards.** `CODING_STANDARDS.md` holds only the judgement calls that `code-review` checks. Anything a check can catch belongs in CI instead.

- A test's expected value comes from a worked example or a known answer, never from recomputing it the way the code does.
- A number on screen or in a results file can be traced to the script that wrote it.
- The "simulated" label is visible wherever a simulated result is shown, in the app, on slides and in videos.
- An overlay image actually shows what the pull request claims (alignment, match outline, route).
- Nothing beyond the ticket: no extra options, layers or settings that no ticket asked for.

## Contracts between the parts

These nine contracts ship with the repo tonight, are confirmed at H0 and live in `contracts/` as JSON Schemas. The schemas are the single source: the TypeScript types and the Python models are generated from them, and CI fails if a generated file is out of date.

**Positions and metres.** All positions are metres in each site map's own projection, the same frame as Curiosity's recorded positions, so map, route and answer key line up without conversion. Person 2 checks the shared frame in P2-01 by plotting rover positions from PLACES on the base-map overlay. Errors and distances are **ground metres**. Both site maps are equirectangular with true scale at the equator. At Gale (about 4.6°S) east–west map metres are within 0.3% of ground metres, which is close enough. At Jezero (about 18.4°N) they are about 5% too long, so Person 2 reprojects the Jezero crops to a frame with true scale at the site before anyone keys or matches on them.

| Contract | Producer | Used by | Contents | Real by |
| --- | --- | --- | --- | --- |
| Site config `sites/gale.yaml`, `sites/jezero.yaml` | 2 (sol from 4) | All | Projection, walk-area bounds, habitat, base camp, science targets, checkpoints, file paths relative to `REDMARK_DATA`, replayed sol | Before H0 |
| Layer files `data/<site>/layers/<name>/` | 2 (layers 1–3), 3 (layer 5) | 1, 4 | Map tiles in local metres plus `layer.json`: name, units, resolution in metres, legend, source | Layer 1 H4; layers 2–3 H6; layer 5 H10, final H14 |
| Route API `POST /route` | 4 (engine), served by 1's service | 1, 4 | In: start, goal, mode (fastest, science, cart), uncertainty circle in metres, limits. Out: path, time per leg, total time, walk-back margin, every limit check, checkpoints | Fastest H8; all routes H10 |
| Fix result | 2 (drone), 3 (horizon, ground) | 1, 4 | Photo id, site, method, estimated position, heading, uncertainty circle (radius in ground metres), confidence %, time per fix, terrain type, simulated (required, no default), overlay image. Tested photos also carry true position, true heading and error; a fix on the demo walk has none | First fixes H6 |
| Scorer `contracts/scoring/` | 3 (2 reviews) | 2, 3 | One shared implementation of position error (ground metres), heading error (wraps at 360°, so 359° against 1° is 2°), median, and share within 1, 5 and 10 m (exactly 5 m counts as within 5 m), split by terrain type | H3 |
| Test summary `results/<test>.json` | 2, 3 | 1 (Test lab chart, slides), 4 (simulation) | Median error, share within 1, 5 and 10 m, heading error, split by terrain type (textured, plain); written only through the scorer, plus the script, commit and input checksums that produced it | H12 |
| Walk simulation `POST /simulate` | 4 | 1 | In: route, fix schedule, break-it flags. Out: one step per time tick with true and estimated position, circle, active sources, events and mode (normal, offline, lost) | H12; break-it runs H14 |
| Conditions `conditions/<sol>.json` | 4 | 1, 4 (daylight limit) | Local time, daily radiation, temperature, pressure, dust (measured or estimated), sun direction, sunset | H8 |
| Demo cache `cache/demo/` | Each producer | 1 | The saved response for every step of the 3-minute script | H16 |

Every contract has a stub file in the repo from the start; "Real by" is when the real data replaces it. Swapping a stub for the real file needs no code change. The meaning of the uncertainty circle and the confidence % is set tonight (see Decisions) and written into the fix result schema.

## Person 1: app

Person 1 owns everything the judges see, the local service the app talks to, the health of the main branch, and the whole submission: slides, live pitch, videos and project page.

**Downloads and installs.** Nothing from NASA; about 1 GB of tools.

- Node.js with Vite, React, TypeScript and deck.gl (through npm).
- Python with FastAPI, to run the service locally.
- From the data person, not downloaded: the cropped map tiles and layer files for the walk area.

**Agent lanes**

| Lane | Builds | Due |
| --- | --- | --- |
| A · Service and map | Service shell that serves layers, results and conditions, forwards route and simulation requests to Person 4's engines, and records the demo cache; then deck.gl in local metres, base map tiles, 3D terrain, layer toggles that show each layer's resolution | Service H3; map H6 |
| B · Planning and walk | Planning screen (layers, habitat, base camp, route options, limit checks); Walk view (dot, circle, next waypoint, time and distance left, walk-back margin, conditions strip) | H8; H12 |
| C · Results | Test lab (pick a tested photo, predicted vs true, error in metres, results chart next to JPL's benchmark); Drone fix screen; Target preview | H12; H17 |
| D · Simulation and offline | Simulation controls and "break it" buttons; Photo checkpoint guidance; Lost mode; demo mode that reads only the cache; the offline demo run; the visor mockup image | H15; H18 |
| E · Submission | About 6 slides from the outline, with numbers only from `pitch/numbers.md`; scripts for the 2-minute and 30-second videos; project page text and References from the data manifest | Slides draft H16, final H20; videos H23; page H24 |
| F · Guardrails | CI, branch protection, the Claude Code hooks, the pull request template (P1-15) | H2 |

**Person 1's own work.** Create the repo tonight, before anyone else writes code: run `/setup-matt-pocock-skills` and publish the tickets with `/to-tickets`, then confirm the contracts at H0. Decide the look and the demo flow. Review each screen against the 3-minute script. Run the smoke test together at each gate; between gates, owners merge their own green pull requests. Give the live pitch, and rehearse it at least twice, once with the network off. Record the screens by H21 and the videos at H22, and submit the project page by H24.

**Done means**

- [ ] All 8 key screens work, built in this order: Planning, Walk view, Test lab, Simulation controls; then Photo checkpoint and Lost mode; then Drone fix and Target preview.
- [ ] The 3-minute demo runs end to end from the cache with the network off.
- [ ] Every simulated result shows a visible "simulated" label.
- [ ] Each layer's legend shows its resolution.

**If it slips.** Drone fix and Target preview fall back to static images. Demo mode reads only the cache.

## Person 2: data and drone matcher

Person 2 owns the map data everyone builds on and the real drone fix at Jezero. They have the best GPU and already have the 23 GB Gale photo map, so the heavy data and the GPU matching sit here, including Person 3's stage 2 batches.

**Downloads and installs.** About 15 GB still to fetch; the Gale photo map is done.

- [Gale photo map, 25 cm](https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/MSL_Gale_Orthophoto_Mosaic_25cm_v3.tif) (23 GB): already downloaded. Crop the walk area and share the crop with the others.
- [Gale 3D terrain, 1 m](https://planetarymaps.usgs.gov/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif) (3.6 GB), for slope and the crops. Person 3 already has the full file and can copy it over by USB.
- THEMIS thermal inertia, 30S120E tile ([page](https://astrogeology.usgs.gov/search/map/themis_thermal_inertia_mosaic_quantitative_30s120e_100mpp)). This is the right tile; see Corrections below.
- CRISM mineral maps for the walk area: [CRISM archive](https://pds-geosciences.wustl.edu/missions/mro/crism.htm) or the [map search](https://ode.rsl.wustl.edu/mars/).
- Curiosity chemistry (APXS, ChemCam): [MSL archive](https://pds-geosciences.wustl.edu/missions/msl/).
- [Jezero photo map, 25 cm](https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first): a 3.2 GB compressed GeoTIFF or the 6.9 GB TIF ([direct link](https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first.tif)).
- Ingenuity Navcam photos for a few flights, higher flights first, plus one or two extra flights used only for tuning: [Mars 2020 archive page](https://pds-geosciences.wustl.edu/missions/mars2020/), then "Helicam Bundles at the PDS Imaging Node".
- [JPL matcher weights](https://huggingface.co/dpisanti/mbl-mars), [LoFTR code](https://github.com/zju3dv/LoFTR), and [LightGlue](https://github.com/cvg/LightGlue) as the fallback.
- Python packages: GDAL/rasterio, scikit-image, numpy, OpenCV, PyTorch with GPU support.

**Tonight, before the clock**

- [ ] First, the Jezero pack for Person 4: photos from 3 to 5 higher flights plus map crops around them, reprojected so map metres are ground metres, so Person 4 can hand-match the answer key tonight.
- [ ] Start the remaining downloads.
- [ ] With Persons 3 and 4, pick the walk area and habitat (see Decisions).
- [ ] Crop every Gale source to the walk area, write `sites/gale.yaml`, and copy the crops to the USB drive.
- [ ] Check that LoFTR loads JPL's weights on the GPU for one image pair.

**Agent lanes**

| Lane | Builds | Due |
| --- | --- | --- |
| A · Data prep | Crops, reprojection to the base map's frame, an overlay image per layer, tiles and `layer.json`; the Jezero pack | Tonight; final H4 |
| B · Layers 2 and 3 | Slope; ridge map from the 25 cm photos; THEMIS sand vs rock; CRISM highlights; Curiosity chemistry points; the science-target list | H6 |
| C · Drone matcher and test | Straighten the fisheye, shrink to 25 cm, search a wide window, match with LoFTR and JPL's weights on the GPU (LightGlue as the fallback); then the test on Person 4's answer key through the shared scorer: share within 1, 5 and 10 m next to JPL's 89.4% within 5 m and 99.8% within 10 m, split by terrain, with hard mode. Tuning uses only flights with no answer-key frames | First fix H6; numbers H12 |
| D · Gale drone fix and GPU jobs | Simulated Gale drone fix: top-down views cut from the Gale map with suit markers drawn in, through the real matcher; the astronaut-detection mock-up; Person 3's stage 2 batches | Batches by H12; images H16 |

The Gale drone views come from the same map they are matched to, so they show the pipeline, not accuracy. They are labelled simulated, and no numbers are reported from them.

**Person 2's own work.** Check every layer overlay by eye, since CRISM and THEMIS can be offset from the HiRISE map. Check that PLACES rover positions sit on Curiosity's tracks in the base map. Judge the ridge map against the photo. Look at every drone match overlay, and keep answer-key flights out of tuning.

**Done means**

- [ ] Layers 1 to 3 in the app, aligned, each labelled with its resolution.
- [ ] Drone results at Jezero on at least 20 answer-key frames, next to JPL's benchmark, split by terrain, with hard mode shown.
- [ ] Gale drone-fix screen images, labelled simulated.
- [ ] Person 3's stage 2 batches run before the H12 call.

**If it slips.** Switch the matcher to LightGlue. Use fewer flights, higher ones first. Hand-trace the ridge map along the demo route only. Serve cached match results in the demo.

## Person 3: horizon matcher and location quality

Person 3 owns the real position result at Gale and the location-quality layer, which is what sets RedMark apart from other teams.

**Downloads and installs.** About 6 GB plus photos; both terrain files are already downloaded.

- [Gale 3D terrain, 1 m](https://planetarymaps.usgs.gov/mosaic/Mars/MSL/MSL_Gale_DEM_Mosaic_1m_v3.tif) (3.6 GB). This person needs the full file, not a crop, because the skyline comes from terrain far outside the walk area.
- [MOLA terrain, 463 m](https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif) (2 GB). Needed: the Gale file covers only about 137.12–137.68°E and 4.13–5.10°S (33 × 57 km), so the top of Mount Sharp and most of the crater rim are outside it.
- Curiosity Navcam photos with labels for sols 4600 to 4709: [processed images](https://pds.nasa.gov/data/pds4/releases/img/msl_navcam_processed-20260317/). A few hundred frames is enough.
- Rover positions, as the answer key: [PLACES archive](https://planetarydata.jpl.nasa.gov/img/data/msl/msl_places/).
- For the stage 2 attempt: [Navcam mosaics](https://pds.nasa.gov/data/pds4/releases/img/msl_navcam_mosaic-20260317/), plus the photo-map crop from the data person.
- Python packages: numpy, OpenCV, GDAL/rasterio.

**Tonight, before the clock**

- [x] Download the terrain. The Gale file does not reach the rim or the top of Mount Sharp, so MOLA is in.
- [ ] Download the frames and the PLACES positions. Check the height offset between MOLA and the Gale terrain where they overlap before joining them.
- [ ] Help Persons 2 and 4 pick the walk area: which candidate spots can see Mount Sharp, Mishe Mokwa, Texoli and the rim.
- [ ] Split the frames into a tuning pile and a hidden pile by stretch of the traverse, before anything is tuned. Curiosity often stays parked for several sols, so splitting by sol would put frames of the same spot on both sides.

**Agent lanes**

| Lane | Builds | Due |
| --- | --- | --- |
| A · Horizon renderer and scorer | The shared scorer first (H3). Horizon lines ray-cast on a grid of candidate spots across the walk area, cached to disk: 1 m terrain near, coarser further out, MOLA beyond the Gale file, with Mars's curvature included (the surface drops about 530 m at 60 km, about 0.5° of elevation) | Scorer H3; grid H4 |
| B · Skyline matcher and test | Skyline from each Navcam frame; camera pointing from the image labels; match to the cached horizons, giving position, heading and a circle; frames from one rover position combined into a wider skyline where possible; run on the hidden pile against PLACES through the scorer | First fix H6; numbers H12 |
| C · Location-quality layer | Landmark visibility from the terrain, plus the error map from the tests, as layer 5; checkpoint candidates on ridge tops and open ground; lost-mode landmark directions such as "keep the upper Mount Sharp peak on your left" | Visibility-only version H10; final H14 |
| D · Real stage 2 | An overhead view from the Navcam mosaics or stereo pairs, matched to the 25 cm photo map and scored against the same answer key; heavy matching runs on Person 2's GPU | First batch to Person 2 by H6; go or no-go H12 |

**Person 3's own work.** Guard the hidden pile. Look at extracted skylines on sample frames before trusting a number. Make the stage 2 call at H12. Sign off every number before it goes to Persons 1 and 4. Get Person 2's review on the scorer, since both test summaries depend on it.

**Done means**

- [ ] Horizon results on the hidden pile, through the shared scorer: median position error (m), heading error (degrees) and time per fix (s), split by terrain type.
- [ ] A fix result and an overlay image for every tested frame, ready for the Test lab.
- [ ] Layer 5 delivered to Persons 1 and 4.
- [ ] Stage 2 is either real with its own measured numbers, or still simulated and labelled.

**If it slips.** Report heading alone if position is unstable, since heading is stage 1's most reliable output. Use cached results for the demo frames. Stage 2 stays simulated.

## Person 4: route and simulation

Person 4 owns the route planner, the simulated walk behind the "break it" buttons, and the conditions strip; Person 1 owns the submission. None of it needs a strong machine, which suits the team's lightest laptop: Person 4 downloads only small files and gets every crop from Person 2. They also hand-make the drone answer key, so it comes from someone other than the person running the matcher.

**Downloads and installs.** Under 1 GB, plus crops from Person 2.

- Conditions for the replayed sol: [RAD](https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/AAREADME.TXT), [REMS](https://pdsatmospheres.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html) and the [dust record](https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/atmospheric_opacity.html).
- Check whether the [Zubarev mosaic](<https://epizodyspace.ru/bibl/inostr-yazyki/Lunar_and_Planetary_Science/2025/Zubarev_et_al_The_Complete_Orthophotomosaic_of_Ingenuity_Navcam_Images_56th_LPSC_no_1302_(2025).pdf>) data is published before hand-matching the answer key.
- Python packages: numpy, scikit-image, GDAL/rasterio. No PyTorch: install without the GPU group.
- From Person 2, not downloaded: the Jezero pack tonight, and the Gale walk-area crops and layers.

**Tonight, before the clock**

- [ ] Check for the Zubarev data, then have an agent build a small tie-point tool and hand-match about 20 frames from the Jezero pack. Allow a few hours; Ingenuity's own position estimates can be about 20 m off, so they cannot be the key.
- [ ] With Persons 2 and 3, pick the walk area: science targets within 2 km of the habitat, and a base camp the cart can reach on firm, open ground.
- [ ] Pick the replayed sol and tell Person 2 for the site config.

**Agent lanes** (2 or 3 at a time on this machine)

| Lane | Builds | Due |
| --- | --- | --- |
| A · Route | Cost map, minimum-cost path, the hard limits from the project document, science alternative, cart route with no ridge crossings, walk-back and daylight, then location-aware routing with layer 5 | Fastest H8; all routes H10; layer 5 H14 |
| B · Walk simulation | Kalman filter combining visual odometry drift, steps and sun heading with fixes (sizes read from Persons 2 and 3's test summaries: the stubs until H12, the real files after, with no code change); fix requests at 3, 5 and 10 m; radio ranging (simulated); break-it scenarios; lost-mode trigger; cached runs | H12; scenarios H14 |
| C · Conditions | Conditions file for the replayed sol: daily radiation, temperature, pressure, dust (measured or estimated), sun direction, sunset | H8 |

**Person 4's own work.** Make the answer key. Pick the sol. Tune the simulation so the circle grows and shrinks believably.

**Done means**

- [ ] Three routes: fastest safe, science alternative with its extra time shown, and the cart's route to base camp; each lists every limit check and moves away from hazards when the circle grows.
- [ ] Cached simulation runs for the normal walk and for each break-it case: camera off, radio off, drone grounded, and everything at once (lost mode).
- [ ] A conditions strip for one real sol, with dust labelled as measured or estimated.

**If it slips.** Use slope and walking time as the only route costs. Keep the simulation to the normal walk plus one break-it case.

## Timeline

Seven phases and six gates. At each gate all four people stop, merge to main and run the smoke test together.

| Phase | Hours | Focus | Gate at the end |
| --- | --- | --- | --- |
| Prep | Tonight | Repo, contracts, stubs and tickets; downloads, crops, the Jezero pack, the answer key; decisions | H0: contracts confirmed |
| Build 1 | H0–H6 | Scorer (H3), service shell (H3), guardrails (H2), base map (H4), horizon grid (H4), first fixes, first route | H6: checkpoint 1 |
| Build 2 | H6–H12 | Layers 2, 3 and 5, all routes, walk simulation, both tests on their hidden piles, Test lab | H12: checkpoint 2, stage 2 go or no-go |
| Build 3 | H12–H14 | Break-it scenarios, location-aware routing, demo fixes, layer 5 final | H14: last new work starts |
| Finish | H14–H18 | Remaining screens, every demo cache by H16, the offline demo run | H18: feature freeze |
| Pitch | H18–H22 | Slides final (H20), rehearsals, screen recordings (H21) | H22: record |
| Submit | H22–H24 | Videos (H23), project page and References | H24: submit |

Each agent lane above carries the hour it is due by.

## Risks that come with agents

Each person's fallbacks are in their own section. These are the extra risks of running many agents at once; the project document's risk table still applies.

| Risk | Mitigation |
| --- | --- |
| Agents on different branches break each other's code | Folder owners enforced by hook and CI, contracts as schemas with generated types, CI on every pull request, merges every 2 hours |
| Two agents share one checkout and commit to each other's branch | One worktree per agent; the git session guard blocks a second session in a claimed checkout |
| An agent skips tests or builds past the ticket | The ticket cycle: `/implement` agrees seams first and ends with `code-review` on the Spec axis; no pull request without both |
| Ticket status drifts across six documents | The GitHub issue is the live status from H0; the plan files are not edited during the build |
| An agent hard-codes or invents a result | Numbers only from results files, which record the script, commit and inputs that wrote them; slide numbers from a generated `pitch/numbers.md` |
| Tuning leaks into the hidden piles | Split by stretch of the traverse (Gale) and by flight (Jezero); a test fails if tuning code points at a hidden-pile folder |
| Someone commits a crop or a terrain file | Big map formats and `data/` are ignored by git, and CI rejects any file over 5 MB |
| A layer looks right but sits metres off | An overlay image per layer, checked by eye before it merges |
| Too much lands at H17 | New work starts only before H14; H14 to H18 is for finishing |
| Agents and matchers fight for one laptop's CPU or GPU | GPU matching runs on Person 2's machine, including Person 3's stage 2 batches; Person 4's light machine runs no heavy jobs and at most 2 or 3 agents |
| The rules limit AI use or work done before the clock | Read the guides first thing tomorrow; scale prep back if needed; say on the project page how agents were used, if asked |

## Corrections and changes

### Changes on Nov 13

Person 1 can veto the two scope changes marked *(scope)*; everything else fixes a gap or a mistake.

- **Ticket cycle.** Every ticket now goes through Matt Pocock's skills: claim the GitHub issue, worktree branch, `/implement` with `tdd` at agreed seams, `code-review`, a pull request written with `pr`. Each person plan lists its test seams.
- **Tickets on GitHub.** Person 1 publishes every ticket as a GitHub issue with `/to-tickets` tonight. From H0 the issue is the live status. Tickets that need a person (the answer key clicks, slides, pitch, recordings, videos, submission) are now `ready-for-human`.
- **Rules have checks.** Each agent rule names what enforces it. The new ticket **P1-15** (CI, branch protection, hooks, pull request template, by H2) builds them, so P1-01 stays short and nobody waits on it.
- **Shared scorer.** The new ticket **P3-09** (Person 3, by H3, reviewed by Person 2) holds the one implementation of error, heading error and "share within". Both test summaries go through it, so "within 5 m" means the same thing in both, and 359° against 1° counts as 2°.
- **Hidden piles.** The Gale split is now by stretch of the traverse, not by sol: Curiosity often stays parked for several sols, so splitting by sol puts frames of the same spot in both piles. At Jezero, tuning uses only flights with no answer-key frames.
- **Fix result contract.** True position, true heading and error are only on tested photos. What the circle and the confidence % mean is a decision for tonight, with a suggested answer. "Direction error" is now "heading error" everywhere, and results are split by terrain type (textured or plain).
- **Ground metres.** Errors are reported in ground metres. Jezero's map is about 5% long east–west at 18.4°N, so its crops are reprojected before the answer key is made.
- **Gale terrain coverage.** The Gale file covers 137.12–137.68°E and 4.13–5.10°S (read from the file on Nov 13), so the top of Mount Sharp and most of the rim are outside it. MOLA is needed and already downloaded; the horizon renderer includes Mars's curvature.
- **Blocking loop removed.** P2-08 waited on P3-07, and P3-07 waited on P2-08. P2-08 now starts from P3-07's first batch, at about H6.
- **Same-hour handoffs.** Where a ticket is due at the hour its input lands (Test lab, Walk view, walk simulation, location-aware routing), the ticket is done when it works on the stub and shows the real file within an hour, with no code change. The demo cache is now due at H16, not H18, so the H18 offline demo has two hours to come together.
- **Data folder.** A worktree has no `data/` folder of its own, so its location now comes from `REDMARK_DATA`. Big map formats are ignored by git and CI rejects files over 5 MB.
- **Dependencies.** PyTorch sits in an optional GPU group in the one lock file, so only Person 2 installs it.
- **Offline demo** *(scope)*. The demo runs from the laptop with Wi-Fi off; installing the app as an offline web app is a stretch goal.
- **Slide numbers** *(scope)*. Slides take numbers only from `pitch/numbers.md`, which a script writes from the results files.
- **Glossary.** [GLOSSARY.md](../GLOSSARY.md) fixes the words agents use. It becomes the repo-root `GLOSSARY.md` that the skills read.
- **Project document.** Its build outline, roles, cart route, future work and THEMIS link now match this plan, and its three missing diagrams are back as Mermaid diagrams and a table.

### Corrections to the download lists (Nov 12)

- **THEMIS tile.** 30S120E, as in Person 2's list, is the right tile. The project document used to link 30S060E, which covers 60°E to 120°E and 0° to 30°S, so it misses Gale at about 137.8°E; it now links 30S120E. The 30S120E page did not load when checked. By the same naming, its file should be `THEMIS_TI_Mosaic_Quant_30S120E_100mpp.cub`, in ISIS format, which GDAL reads; the 30S060E file is about 2.5 GB.
- **Jezero map size.** Both figures are right: the [USGS page](https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first) lists a 3.2 GB compressed GeoTIFF and a 6.9 GB TIF, now linked directly in Person 2's list.
- **Dust record.** The project document notes that the PDS dust bundle stops at sol 3902, before the boxwork sols. Check the record for the chosen sol; if it is not covered, show a typical value for the season, labelled as an estimate.
- **Simulation owner.** The walk simulation had no owner; it is now Person 4's.
