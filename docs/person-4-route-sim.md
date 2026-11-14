# RedMark: Person 4 plan (route and simulation)

As of Fri 13 Nov 2026. Shared [team plan](team-plan.md) (it wins if this file disagrees), [project document](project-document.md) and [glossary](../GLOSSARY.md).

## Your role

You own the route planner, the walk simulation behind the "break it" buttons, and the conditions strip. Person 1 owns the whole submission (slides, live pitch, videos, project page). You also hand-make the drone answer key, so the key comes from someone other than the person running the drone matcher. None of this needs a strong machine: you download only small files and get every crop from Person 2.

**Your machine.** It is the team's lightest, so:

- No large downloads and no PyTorch. Crops come from Person 2 by USB or shared folder.
- Run 2 or 3 agents at a time, not more. Count `code-review`'s two parallel reviewers as agents.
- Plan routes on a coarser grid (for example 2 m) if one route takes more than a few seconds.
- Seed the simulation so every run replays the same way, and cache every demo run.

**How to read the tickets.** "Blocked by" is what must be done before a ticket starts. Stub files come with the repo, so "Needs to finish" lists the real data from other people that a ticket needs before it counts as done. When that real data is due at the same hour as your ticket, your ticket is done once it works on the stub; the real file must then show up within an hour of landing, with no code change. Hours are from the start of the 24-hour clock (H0). From H0 each ticket's live status is its GitHub issue; this file is the brief and is not edited during the build. "Status" is the issue's triage label: `ready-for-agent` tickets can be built by an agent end to end, `ready-for-human` tickets need you, though an agent can draft for them.

## Your ticket cycle

Every ticket follows the [ticket cycle](team-plan.md#the-ticket-cycle-matt-pococks-skills): claim the issue, worktree branch, `/implement <issue>`, `code-review`, then a pull request written with the `pr` skill. Each route puts its overlay on the photo map in the pull request's Evidence section.

**Test seams.** When `/implement` asks which seams to test, answer from this list. Use tiny made-up grids, so the tests run fast on this machine and in CI.

- Route engine: on a small grid with one obvious best path, it returns that path; the cart route never crosses a ridge cell.
- Limit checks: each hard limit has one route that passes and one that fails.
- Walk simulation: the same seed gives the same run; the circle grows with no fixes and shrinks at a fix; error sizes come from the test-summary file it is given.
- Conditions: sunset and sun direction for the chosen sol match a worked Mars24 value.
- Tie-point tool: 4 known point pairs give the known position and heading.

**Skills you'll lean on.** `research` for the RAD, REMS and dust-record file formats and for Mars24, in the background. `diagnosing-bugs` when a route is slow or a run won't replay the same way. Skip `/implement-spec` and anything else that starts many subagents at once.

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

Under 1 GB of your own, plus crops from Person 2.

- Conditions for the replayed sol: [RAD](https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/AAREADME.TXT), [REMS](https://pdsatmospheres.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html) and the [dust record](https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/atmospheric_opacity.html). The project document notes that the PDS dust bundle stops at sol 3902, before the boxwork sols: check the record for your sol, and if it is not covered, use a typical value for the season, labelled as an estimate.
- Check whether the [Zubarev mosaic](https://epizodyspace.ru/bibl/inostr-yazyki/Lunar_and_Planetary_Science/2025/Zubarev_et_al_The_Complete_Orthophotomosaic_of_Ingenuity_Navcam_Images_56th_LPSC_no_1302_(2025).pdf) data is published before hand-matching the answer key.
- Python packages: numpy, scikit-image, GDAL/rasterio. No PyTorch: install without the lock file's GPU group.
- Matt Pocock's skills for your agent tool (install commands in the [team plan](team-plan.md#the-ticket-cycle-matt-pococks-skills)).
- From Person 2, not downloaded: the Jezero pack (tonight) and the Gale walk-area crops and layers.

## Tonight, before the clock

- [ ] Check for the Zubarev data. If a georeferenced Ingenuity mosaic is out, it may replace most of the hand-matching.
- [ ] Install Matt Pocock's skills. Clone the repo as soon as Person 1 says it is ready, and run the smoke test. The tie-point tool goes into the repo.
- [ ] Have an agent build a small tie-point tool: click 4 or more matching points on a photo and on the map crop, and it saves the photo's true position and heading.
- [ ] P4-01: hand-match about 20 frames from Person 2's Jezero pack. Allow a few hours.
- [ ] With Persons 2 and 3, pick the walk area and habitat. Your check: the habitat is within 2 km of the science targets, and the cart can reach a base camp on firm, open ground.
- [ ] Pick the replayed sol: between 4600 and 4709 (the Navcam archive's range), covered by RAD and REMS. Tell Person 2 for the site config.

## Tickets

### P4-01: Drone answer key

**What to build:** The answer key for the drone test at Jezero: the true position and heading of about 20 Ingenuity frames, found by hand with tie-points between each photo and the Jezero photo map. Ingenuity's own position estimates can be about 20 m off, so they cannot be the key.

**Blocked by:** P2-04, P1-01.

**Due:** Before H0; H6 at the latest.

**Status:** ready-for-human (an agent builds the tie-point tool; you click the points)

- [ ] At least 20 frames keyed, each with its tie-points saved.
- [ ] Keys are in the frame of Person 2's reprojected Jezero crops, so their positions are in ground metres.
- [ ] An overlay image per frame, checked by eye.
- [ ] Each frame tagged with its terrain type (textured or plain); hard-mode frames over sand ripples marked.
- [ ] The key is stored apart from anything Person 2 tunes on, and the key's flights are listed so Person 2 can keep them out of tuning.

### P4-02: Conditions for the replayed sol

**What to build:** The conditions file for one real sol from Curiosity's boxwork campaign: local time steps, one daily radiation value (it changes little within a sol), temperature and pressure from REMS, dust, sun direction and sunset. It feeds the Walk view's conditions strip and the route's daylight limit.

**Blocked by:** Sol decision, P1-01.

**Due:** H8.

**Status:** ready-for-agent

- [ ] Every value comes from a script reading the PDS files; sources go in the data manifest.
- [ ] Dust is labelled measured or estimated.
- [ ] Sun direction and sunset are computed for Gale's position on that sol (for example with the Mars24 algorithm).

### P4-03: Fastest safe route

**What to build:** The route engine behind the Planning screen. Every map cell gets a cost from the layers (walking time from slope and sand vs rock, ridge crossings); a minimum-cost path search finds the shortest walking time that breaks no hard limit. The service returns the path, time per leg, total time, walk-back margin and every limit check. Starts on stub layers; done on Person 2's real ones.

**Blocked by:** P1-02.

**Needs to finish:** P2-02 (slope), P2-03 (walkability).

**Due:** H8.

**Status:** ready-for-agent

- [ ] Default hard limits: steepest slope 20° (15° as an option), 2 km from the habitat, 2 km/h planning speed, about 6 h walk.
- [ ] No returned route ever breaks a hard limit.
- [ ] A route comes back within a few seconds on this machine.
- [ ] The route shows on Person 1's Planning screen and is checked by eye against the photo map.

### P4-04: Science and cart routes, walk-back and daylight

**What to build:** The other two routes and the remaining limits. The science alternative passes more targets (boxwork ridges off Curiosity's track and mineral highlights) and shows the extra time it costs. The cart route uses its own cost map: it cannot cross 1 to 2 m ridges, and it drives to the base camp on firm, open ground, where the walkers' route starts. The walk-back rule keeps the crew able to walk home from any point, and the daylight limit gets them back before sunset.

**Blocked by:** P4-03, P4-02.

**Due:** H10.

**Status:** ready-for-agent

- [ ] Three route modes: fastest, science, cart.
- [ ] The science route reports its extra time compared with the fastest route.
- [ ] The cart route never crosses a ridge on Person 2's ridge map.
- [ ] Walk-back and daylight show as limit checks; daylight uses the sunset from P4-02.

### P4-05: Walk simulation

**What to build:** The simulated walk along a route. A simple Kalman filter tracks true and estimated position: visual odometry, step counting and sun direction carry the position between fixes, and the circle grows; fixes shrink it. Fix error sizes come from the results files: horizon from Person 3's test, ground from Person 3's stage 2 result, drone at 5 to 10 m from Person 2's test. The app asks for a new fix when the circle passes 3 m near hazards, 5 m in the boxwork, 10 m on open ground.

**Blocked by:** P1-02.

**Needs to finish:** P2-06, P3-03 (real error numbers); refresh when P3-08 lands at H14.

**Due:** H12.

**Status:** ready-for-agent

- [ ] Error sizes are read from results files, never typed in. Until H12 these are the stub test summaries; the real ones replace them with no code change.
- [ ] The circle visibly grows between fixes and shrinks at each fix.
- [ ] Runs are seeded, so the same inputs replay the same walk.
- [ ] Person 1's Walk view plays a run end to end.

### P4-06: Break-it scenarios

**What to build:** What happens when things fail, as the "break it" buttons show it. Camera off: motion sensor, steps and sun carry the position, and the buddy's camera takes fixes. Radio off: offline mode. Drone grounded: drone fixes greyed out. Radio ranging to the habitat and between the two astronauts is a simulated source. The hazard margin grows with the circle, so the route re-plans away from hazards, and the app says to stop and take a fix when the circle is too big near a hazard. Everything at once triggers lost mode.

**Blocked by:** P4-05, P4-04.

**Due:** H14.

**Status:** ready-for-agent

- [ ] Cached runs for the normal walk and for camera off, radio off, drone grounded and everything at once.
- [ ] In at least one case the route visibly moves away from a hazard as the circle grows.
- [ ] Lost mode starts in the everything-at-once run.
- [ ] Radio ranging is labelled simulated.

### P4-07: Location-aware routing

**What to build:** The route prefers ground where position finding works well: a good landmark view and a low error-map value. Photo checkpoints sit on ridge tops or open ground where Mount Sharp, the buttes or the crater rim are visible.

**Blocked by:** P4-03, P3-05.

**Needs to finish:** P3-06 (final layer 5 with the error map).

**Due:** H14.

**Status:** ready-for-agent

- [ ] Layer 5 is part of the route cost, with a weight that can be changed.
- [ ] Checkpoints come from Person 3's checkpoint candidates.
- [ ] The demo route shows a visible difference with and without location-aware routing.

## Handoffs

| You give | To | By |
| --- | --- | --- |
| Replayed sol | Person 2 (site config) | Tonight |
| Drone answer key | Person 2 | Before H0, H6 at the latest |
| Conditions file | Person 1 | H8 |
| Fastest route | Persons 1 and 3 | H8 |
| Science and cart routes | Person 1 | H10 |
| Walk simulation | Person 1 | H12 |
| Break-it runs | Person 1 | H14 |

| You get | From | By |
| --- | --- | --- |
| Jezero pack | Person 2 | Tonight, first |
| Walk-area crops and site config | Person 2 | Before H0 |
| Repo, contracts, stubs | Person 1 | Tonight, first |
| Service shell | Person 1 | H3 |
| Slope; walkability and science layers | Person 2 | H4; H6 |
| Layer 5 | Person 3 | H10, final H14 |
| Test summaries | Persons 2 and 3 | H12 |
| Stage 2 result or error model | Person 3 | H14 |

## If it slips

- Use slope and walking time as the only route costs.
- Keep the simulation to the normal walk plus one break-it case.
