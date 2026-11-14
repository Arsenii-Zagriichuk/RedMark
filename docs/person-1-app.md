# RedMark: Person 1 plan (app, service shell and submission)

As of Fri 13 Nov 2026. Shared [team plan](team-plan.md) (it wins if this file disagrees), [project document](project-document.md) and [glossary](../GLOSSARY.md).

## Your role

You create the team's repo tonight, before anyone else writes code: the other three start their code tickets only once they have cloned it. After that you own everything the judges see: the React app with its 8 key screens, the local service shell the app talks to, the demo cache, and the offline demo. You also own the repo root and the guardrails that keep main green, and you run the smoke test with everyone at every gate; between gates, owners merge their own pull requests once CI is green. Your agents build the screens; you decide the look and the demo flow, review every screen against the 3-minute script, and merge your own work. You also own the whole submission: the slides, the live demo and pitch, the 2-minute and 30-second videos, and the project page.

**How to read the tickets.** "Blocked by" is what must be done before a ticket starts. Stub files come with the repo, so "Needs to finish" lists the real data from other people that a ticket needs before it counts as done. When that real data is due at the same hour as your ticket, your ticket is done once it works on the stub; the real file must then show up within an hour of landing, with no code change. Hours are from the start of the 24-hour clock (H0). From H0 each ticket's live status is its GitHub issue; this file is the brief and is not edited during the build. "Status" is the issue's triage label: `ready-for-agent` tickets can be built by an agent end to end, `ready-for-human` tickets need you, though an agent can draft for them.

## Your ticket cycle

Every ticket follows the [ticket cycle](team-plan.md#the-ticket-cycle-matt-pococks-skills): claim the issue, worktree branch, `/implement <issue>`, `code-review`, then a pull request written with the `pr` skill. You also set the cycle up for everyone tonight (P1-01).

**Test seams.** When `/implement` asks which seams to test, answer from this list. Screens are checked in the browser, not by tests.

- The API client: in live mode it calls the service; in demo mode it answers every step of the 3-minute script from the cache and never touches the network.
- Results to Test lab: a results file goes in, the chart rows and the photo list come out, and a simulated result never appears.
- Fix display: a fix with `simulated: true` always shows the label.
- The smoke test: it fails when a stub, cache or results file doesn't match its schema.
- Slide numbers: the script that writes `pitch/numbers.md` takes every number from a results file.

**Skills you'll lean on.** `/setup-matt-pocock-skills` and `/to-tickets` tonight. `prototype` for two or three throwaway layouts of the Planning and Walk view screens before your agents build the real ones. `/grill-with-docs` at H0, when the team confirms the contracts. `wizard` if you'd rather be walked through the GitHub steps only a person can do (adding the team, branch protection). `/triage` at each gate, to see what's ready and what's stuck.

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

Nothing from NASA; about 1 GB of tools.

- Node.js (LTS) with Vite, React, TypeScript and deck.gl, through npm.
- Python (the team's agreed version) with FastAPI, to run the service locally, without the GPU group.
- Matt Pocock's skills for your agent tool (install commands in the [team plan](team-plan.md#the-ticket-cycle-matt-pococks-skills)), and the `gh` command-line tool, signed in to GitHub.
- From Person 2, not downloaded: the cropped map tiles and layer files for the walk area.
- A few Curiosity pictures of the science stops, for the Target preview, from the [Analyst's Notebook](https://an.rsl.wustl.edu/), once Person 2 has the science-target list.
- Tomorrow: the [challenge resources](https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/) and the [submission](https://www.spaceappschallenge.org/resources/project-submission-guide/) and [judging](https://www.spaceappschallenge.org/resources/judging-awards-guide) guides. You own the submission, so you read these first.

## Tonight, before the clock

- [ ] Install the toolchain above.
- [ ] Agree the team's Python version and lock-file tool (suggested: Python 3.11 with uv, PyTorch in an optional GPU group).
- [ ] P1-01, before anything else: create the repo and publish the tickets (see the ticket), then tell the team it is ready to clone.
- [ ] P1-15 if there's time tonight: the guardrails. Otherwise by H2.
- [ ] Read the AI-use and pre-work rules when the guides come out on Fri 13 Nov. Keep everything before the clock to setup, and hold app code until the rules allow it. Tell the team what the guides mean for pre-work and for the project page.

## Tickets

### P1-01: Create the repo: folders, contracts, stubs, smoke test

**What to build:** The team's shared repo, created tonight before anyone writes code, so every person's agents start from the same folders, contracts, rules and tickets. It holds the folder owners, AGENTS.md, the 9 contracts as JSON Schemas, a stub file for each contract, a smoke test that passes on the stubs, one Python lock file, an empty app shell, and every ticket as a GitHub issue. The other three review the contracts when they clone it; any change is agreed in 15 minutes at H0. Keep it to this list: CI and hooks are P1-15, so nobody waits on them.

**Blocked by:** None (can start immediately, tonight).

**Due:** Tonight, first. Everyone else's code tickets wait for it; downloads don't.

**Status:** ready-for-agent

- [ ] The repo is on GitHub, with all four people added.
- [ ] The folders from the ownership table exist, each with a short README naming its owner.
- [ ] AGENTS.md lists folder owners, the 9 contracts, the agent rules, the ticket cycle and the merge routine. CLAUDE.md is the single line `@AGENTS.md`.
- [ ] `/setup-matt-pocock-skills` has run: GitHub Issues as the tracker, the default triage labels, and single-context domain docs. Its `## Agent skills` block is in AGENTS.md.
- [ ] `GLOSSARY.md` at the repo root, seeded from the glossary in this docs folder; `docs/adr/` exists for decisions.
- [ ] The six plan documents (project document, team plan, four person plans) are in `docs/`, and AGENTS.md links to them.
- [ ] `CODING_STANDARDS.md` holds the review standards from the team plan.
- [ ] Every ticket in the index is a GitHub issue, published with `/to-tickets`: titled with its ID, assigned to its owner, labelled with its Status, with its blocking links.
- [ ] Each contract has a JSON Schema in `contracts/` and a stub file that validates against it. The TypeScript types and Python models are generated from the schemas, not written by hand.
- [ ] One command runs the smoke test: the service starts, the app builds, every stub loads.
- [ ] One Python version and one lock file, with PyTorch in an optional GPU group; Node LTS for the app; TypeScript in strict mode.
- [ ] `data/` and the big map formats (`*.tif`, `*.cub`, `*.img`) are ignored by git. The data folder's location comes from the `REDMARK_DATA` setting. A data manifest file exists (name, size, source link, checksum per file).
- [ ] Persons 2, 3 and 4 have cloned the repo, installed the skills and run the smoke test.

The Space Apps rules on work done before the hackathon come out on Fri 13 Nov. Keep the repo to setup (folders, contracts, stubs, the smoke test, tickets) and check it against the guides then.

### P1-02: Service shell and demo cache

**What to build:** The local service the app talks to. It serves layer tiles and layer metadata, results files, fix results and the conditions file, and forwards route and simulation requests to Person 4's engines (stubs until those land). Every live response can be recorded into the demo cache, and a demo mode serves only from the cache.

**Blocked by:** P1-01.

**Due:** H3.

**Status:** ready-for-agent

- [ ] Endpoints exist for layers, route, simulation, conditions, fix results and test summaries.
- [ ] Person 4's route and simulation engines plug in without any change to the shell.
- [ ] A recorded session replays exactly in demo mode with the network off.
- [ ] The app can switch between live and demo mode.
- [ ] The app reaches the service only through one client module; a lint rule bans `fetch` anywhere else, so demo mode can't be bypassed.

### P1-03: Map view on the real Gale map

**What to build:** A deck.gl map in local metres that shows the Gale base map, 3D terrain and toggles for the five layers, each with a legend that states its resolution. Habitat, base camp and science targets from the site config are drawn on it. Starts on the stub tile; done when Person 2's real tiles show.

**Blocked by:** P1-01.

**Needs to finish:** P2-02 (real base map tiles and slope).

**Due:** H6 (Checkpoint 1).

**Status:** ready-for-agent

- [ ] The real base map renders, and the slope layer lines up with it.
- [ ] Each of the 5 layers can be shown or hidden; the legend shows its resolution in metres.
- [ ] Habitat, base camp and science targets from the site config appear on the map.
- [ ] Pan, zoom and 3D tilt stay smooth on the demo laptop.

### P1-04: Planning screen

**What to build:** The habitat screen where the crew plans a walk. The planner picks a route option (fastest safe, science alternative, cart), sees it on the map with total time and walk-back margin, and sees every walk limit marked pass or fail. The slope limit can be switched between 20° (default, from Artemis) and 15°.

**Blocked by:** P1-02, P1-03.

**Needs to finish:** P4-03 (real fastest route); P4-04 adds the science and cart routes.

**Due:** H8.

**Status:** ready-for-agent

- [ ] The three route options can be switched, and each draws on the map.
- [ ] Every limit (slope, 2 km from habitat, 2 km/h planning speed, about 6 h walk, walk-back, daylight, hazard margin) shows pass or fail.
- [ ] Changing the slope limit requests a new route.
- [ ] The science route shows its extra time compared with the fastest route.

### P1-05: Walk view

**What to build:** The wrist-tablet screen during the walk. It plays a simulation run along the chosen route: the dot with its uncertainty circle and confidence %, the next waypoint, time and distance left, the walk-back margin, and a conditions strip (radiation, temperature, dust, daylight). Large buttons and high contrast, for stiff gloves.

**Blocked by:** P1-04.

**Needs to finish:** P4-05 (walk simulation), P4-02 (conditions).

**Due:** H12.

**Status:** ready-for-agent

- [ ] Play, pause and scrub through a simulation run.
- [ ] The circle grows between fixes and shrinks at each fix, as the simulation says.
- [ ] The conditions strip shows values from the sol file, with dust labelled measured or estimated.
- [ ] Fix events (horizon, ground, drone) appear on the walk's timeline.

### P1-06: Test lab

**What to build:** The judges' screen. A judge picks a tested Curiosity or Ingenuity photo and sees the photo, its overlay, the predicted and true positions on the map, and the error in metres (plus heading error for horizon fixes). A results chart shows the share within 1, 5 and 10 m next to JPL's benchmark of 89.4% within 5 m and 99.8% within 10 m, split by terrain.

**Blocked by:** P1-02.

**Needs to finish:** P2-06 (drone test), P3-03 (horizon test).

**Due:** H12 (Checkpoint 2).

**Status:** ready-for-agent

- [ ] Every number on the screen comes from a results file; none is typed in.
- [ ] The photo list is built from the fix results.
- [ ] The chart updates when a results file changes.
- [ ] Simulated results never appear in the Test lab.

### P1-07: Simulation controls and Lost mode

**What to build:** The "break it" buttons (camera off, radio off, drone grounded, everything at once) re-run the walk through Person 4's simulation. The app shows the badges ("Camera off", "Offline mode", drone fixes greyed out), the route moving away from hazards, and the Lost mode screen: last known position, return direction and landmark instructions such as "keep the upper Mount Sharp peak on your left".

**Blocked by:** P1-05.

**Needs to finish:** P4-06 (break-it scenarios), P3-06 (landmark directions).

**Due:** H15.

**Status:** ready-for-agent

- [ ] Each button plays its cached scenario run.
- [ ] Badges match the backup table in the team plan.
- [ ] Lost mode shows the landmark directions from layer 5, not hand-written text.

### P1-08: Photo checkpoint

**What to build:** The guided capture at a checkpoint: "turn left… capture" prompts, a progress ring, then the result in ±m with a confidence %. When confidence is low, the app asks for photos facing other directions. The result shown is a real cached horizon fix from a Curiosity frame; any ground fix is labelled simulated unless Person 3's stage 2 went real.

**Blocked by:** P1-05.

**Needs to finish:** P3-04 (demo fixes).

**Due:** H15.

**Status:** ready-for-agent

- [ ] Uses Person 3's real cached Curiosity fixes.
- [ ] Shows heading and position, each with its error.
- [ ] Stage 2 results carry the label Person 3's results file gives them.

### P1-09: Drone fix and Target preview

**What to build:** The Drone fix screen shows the top-down photo, its matched outline on the map and the detected astronauts, labelled simulated at Gale. The Target preview shows Curiosity pictures of the next science stop. Both fall back to static images if time runs short.

**Blocked by:** P1-03.

**Needs to finish:** P2-07 (Gale drone fix images), P2-03 (science-target list).

**Due:** H17.

**Status:** ready-for-agent

- [ ] Both screens work from the cache.
- [ ] Static fallback images exist for both.
- [ ] The Gale drone fix is labelled simulated.

### P1-10: Offline demo

**What to build:** The whole 3-minute demo runs from the cache with the network off, on the demo laptop. This is the H18 freeze build. Installing the app as an offline web app is a stretch goal, only if everything else is done.

**Blocked by:** P1-04, P1-05, P1-06, P1-07, P1-08, P1-09.

**Needs to finish:** Every producer's demo cache (due H16).

**Due:** H18 (feature freeze).

**Status:** ready-for-agent

- [ ] A full rehearsal of the 3-minute script runs end to end with Wi-Fi off.
- [ ] The smoke test covers every demo step.
- [ ] If the service crashes, the app still runs the demo from the cache.

### P1-11: Screen recordings and visor mockup

**What to build:** Screen recordings of each demo segment, for the videos (P1-13), and the helmet visor mockup image (shown as a mockup only).

**Blocked by:** P1-10.

**Due:** H21.

**Status:** ready-for-human (an agent can make the visor mockup)

- [ ] One recording per segment of the 2-minute video: planning, walk and fixes, test results, "break it".
- [ ] The visor image is labelled as a mockup.

### P1-12: Slides and live pitch

**What to build:** About 6 slides that tell the same story as the demo, and the live pitch itself: you present, driving the app through the 3-minute script below. Only measured numbers go on the slides, and the simulated parts are marked. An agent can draft the slides from the outline at any time; the numbers go in once the tests are done.

**Blocked by:** None (draft from the outline at any time).

**Needs to finish:** P2-06, P3-03 (the real numbers).

**Due:** Draft H16; final H20; rehearse H20 to H22.

**Status:** ready-for-human (an agent drafts the slides and writes `pitch/numbers.md`)

- [ ] Slides follow the outline below.
- [ ] Every number comes from `pitch/numbers.md`, which a script writes from the results files; none is typed onto a slide.
- [ ] One sentence explains why the drone test is at Jezero and the walk at Gale.
- [ ] At least two full rehearsals of the 3-minute pitch, one with the network off.

### P1-13: Videos

**What to build:** The 2-minute backup video and the 30-second cut, made from the screen recordings, so a broken live demo never sinks the pitch. Judges outside the room see only the 30-second cut and the project page.

**Blocked by:** P1-11, P1-12.

**Due:** Record at H22; done by H23.

**Status:** ready-for-human

- [ ] 2-minute video: hook 15 s, planning 25 s, walk and fixes 30 s, test results 30 s, "break it" 15 s, close 5 s.
- [ ] 30-second cut: hook 5 s, map and route 10 s, one real photo fix 10 s, close 5 s.
- [ ] Both play offline from the demo laptop.

### P1-14: Project page and submit

**What to build:** The Space Apps project page, in English, with the demo, the References field listing every external resource (code, data, images) from the data manifest, and whatever the 2026 guides ask about AI use and work done before the hackathon. An agent drafts the page text and References from H12; only the final pass waits for the videos.

**Blocked by:** None (draft at any time).

**Needs to finish:** P1-13 (the videos).

**Due:** H24, and before pages close on Sun 15 Nov, 23:59 local.

**Status:** ready-for-human (an agent drafts the page text and References)

- [ ] The page follows the 2026 submission guide (in 2025 the demo was a video of up to 30 seconds or up to 7 slides).
- [ ] References list every data set, code library and image used, including Matt Pocock's skills if the guides ask how agents were used.
- [ ] Submitted, with a screenshot of the confirmation.

### P1-15: Guardrails: CI, hooks, branch protection

**What to build:** The checks that make the agent rules hard to break, so main stays green without you reviewing every merge. Most of it is copied from the FitCore repo's setup.

**Blocked by:** P1-01.

**Due:** Tonight if there's time, H2 at the latest.

**Status:** ready-for-agent

- [ ] CI runs on every pull request to main and finishes in under 5 minutes. It runs ruff, pytest, `tsc --noEmit` and the app build; validates every stub, cache and results file against its schema; checks the generated types are up to date; rejects any file over 5 MB; and fails if the changed paths belong to more than one owner, unless it is a contract change.
- [ ] Branch protection on main: pull request and CI required. `contracts/` and the repo root are in CODEOWNERS, so a change to them needs a review.
- [ ] Claude Code hooks in `.claude/settings.json`: the git session guard from FitCore (`.claude/hooks/git-session-guard.sh` and its tests: one agent per checkout, no `git add -A`), an owner guard that blocks edits outside the person's folders (each person sets their number once), and formatting on every edit.
- [ ] A pull request template with the `pr` skill's sections: Summary, Evidence, Merge danger.
- [ ] Each person can merge their own pull request once CI is green.

## 3-minute demo script (what your screens must show)

| Time | Show | Say |
| --- | --- | --- |
| 0:00 to 0:20 | Title screen | "On Mars there's no GPS, no compass, and Earth is up to 24 minutes away. How does an astronaut know where they are?" |
| 0:20 to 0:50 | Planning mode at Gale | Toggle the 5 layers; show the fastest safe route, the science alternative and the cart's route to base camp |
| 0:50 to 1:30 | Walk mode | Play the walk. A real Curiosity photo gives a horizon fix; then a ground fix and a drone fix tighten it, labelled as simulated (the ground fix only if the stage 2 attempt failed) |
| 1:30 to 2:10 | Test lab | A judge picks an Ingenuity photo; show the match and its error, and the results chart next to JPL's benchmark |
| 2:10 to 2:40 | "Break it" buttons | Camera off, radio off, drone grounded: the circle grows, the route moves away from hazards, lost mode switches on |
| 2:40 to 3:00 | Closing slide | What's real and what's simulated, next steps |

## Slides and judging

**Judging criteria:** Influence, Creativity, Validity, Relevance and Presentation ([Judging & Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide)).

**Slide outline**

1. The problem: no GPS, no compass, no help from Earth.
2. The mission and the five layers.
3. Route and safety: limits, margins that grow with uncertainty, lost mode.
4. How RedMark finds you (the position-finding diagram from the project document).
5. Test results: the real measured numbers, split by terrain, with the simulated parts marked.
6. What's next.

## Handoffs

| You give | To | By |
| --- | --- | --- |
| Repo, contracts, stubs, AGENTS.md, tickets as GitHub issues | Everyone | Tonight, first |
| CI, branch protection and hooks | Everyone | H2 |
| Service shell for the route and simulation engines | Person 4 | H3 |
| What the guides say about AI use and pre-work | Everyone | Fri 13 Nov |
| Slides, videos, project page, submission | Team | H20, H23, H24 |

| You get | From | By |
| --- | --- | --- |
| Base map tiles and slope | Person 2 | H4 |
| Layers 2 and 3, science-target list | Person 2 | H6 |
| Real routes | Person 4 | H8 to H10 |
| Conditions file | Person 4 | H8 |
| Layer 5 | Person 3 | H10, final H14 |
| Test results and fix results | Persons 2 and 3 | H12 |
| Walk simulation and break-it runs | Person 4 | H12 to H14 |
| Demo fixes | Person 3 | H14 |
| Gale drone-fix images | Person 2 | H16 |
| Every producer's demo cache | Persons 2, 3 and 4 | H16 |

## If it slips

- Drone fix and Target preview fall back to static images.
- Demo mode reads only the cache, so a broken engine never breaks the demo.
- Keep the build order: Planning, Walk view, Test lab, Simulation controls first; then Photo checkpoint and Lost mode; then Drone fix and Target preview.
- Slides come before the videos; the 30-second cut comes before the 2-minute video if the project page needs it.
