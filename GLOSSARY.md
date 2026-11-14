# RedMark

A layered Mars walk map that finds the crew's position from photos instead of satellites, built in 24 hours for NASA Space Apps 2026. This glossary gives each word one meaning. Matt Pocock's skills read it; add terms with `/grill-with-docs` as they are settled.

## Mission

**Crew**:
The two astronauts on the walk.
_Avoid_: users, walkers (as a noun for the people)

**Habitat**:
The crew's base, whose position is known exactly.
_Avoid_: lander, base

**Cart**:
The robotic cart that carries the drone, spare batteries, tools and samples.
_Avoid_: rover

**Rover**:
Curiosity, whose photos and recorded positions are the test data at Gale.
_Avoid_: using "rover" for the cart

**Drone**:
The Ingenuity-class helicopter that flies from the base camp.
_Avoid_: helicopter, UAV

**Base camp**:
The spot on firm, open ground where the cart parks and the walkers' route starts.

**Site**:
One mapped place with its own config: Gale (the walk) or Jezero (the drone test).

**Walk area**:
The part of a site the walk may use, within 2 km of the habitat.
_Avoid_: walk corridor, area of interest

**Science target**:
A spot the crew samples: a ridge centre or a hollow that Curiosity did not reach.

**Checkpoint**:
A spot on the route where the crew stops to take a fix, on a ridge top or open ground.

**Hollow**:
Sandy low ground between boxwork ridges, where nearby ridges can hide the skyline.

**Replayed sol**:
The one real sol from Curiosity's boxwork campaign whose radiation, weather and sun play as the walk's live conditions.

## Position finding

**Fix**:
One estimate of where a person is and which way they face, from one method at one moment.
_Avoid_: localization, position estimate, match (a match is a step inside a fix)

**Method**:
How a fix was made: horizon, ground or drone.

**Horizon fix**:
Stage 1: a fix from comparing a photo's skyline with skylines calculated from 3D terrain.
_Avoid_: skyline fix

**Ground fix**:
Stage 2: a fix from comparing an overhead view, built from stereo photos, with the photo map.
_Avoid_: precise fix

**Drone fix**:
A fix from comparing a top-down drone photo with the photo map.

**Heading**:
The direction a person or camera faces, measured from map north.
_Avoid_: direction, bearing, orientation

**Uncertainty circle**:
The circle around a fix that the true position should fall inside. [TODO: the team settles tonight how sure "should" is, for example the 95% radius.]
_Avoid_: error circle, accuracy radius

**Confidence**:
The percentage shown with a fix. [TODO: the team settles tonight what it measures. Suggested: how often tested fixes of the same method and terrain type fell inside their uncertainty circle.]

**Error**:
The ground distance between a fix and the true position, or the angle between a fix's heading and the true heading.
_Avoid_: accuracy, offset

**Ground metres**:
Distance measured on the Martian surface, the unit every error and route distance is reported in.

**Map metres**:
The units of a site map's projection, which can differ from ground metres away from the equator.

**Landmark**:
A far feature on the skyline used for heading and lost-mode directions: the upper Mount Sharp peak, Mishe Mokwa, Texoli, the crater rim.

**Terrain type**:
The class every test result is split by: textured (ridges, rock) or plain (sand).
_Avoid_: ridge and sand as class names

## Testing

**Answer key**:
The true positions and headings of tested photos: PLACES rover positions at Gale, hand-matched tie-points at Jezero.
_Avoid_: ground truth, labels

**Tuning pile**:
Photos a matcher may be tuned on.
_Avoid_: training set

**Hidden pile**:
Photos kept apart to test a matcher, which no tuning ever reads.
_Avoid_: test set, holdout

**Test summary**:
The measured results of one test: median error and the share of fixes within 1, 5 and 10 m, by terrain type.

**Error map**:
Measured error by area and terrain type, taken from the test summaries.

**Measured**:
A number that comes from a test on real photos against an answer key.

**Simulated**:
A result made by the simulation, or by matching a picture against the same map it was cut from, rather than measured. Always labelled.
_Avoid_: fake, mock (keep "mock-up" for the visor image and astronaut detection)

**Overlay image**:
A picture that draws a crop, layer, match or route on the base map so a person can check it by eye.

## Layers and routes

**Layer**:
One of the five map layer groups: base, walkability, science, conditions, location quality.

**Location quality**:
Layer 5: how well position finding works at each spot, from landmark visibility and the error map.

**Hard limit**:
A walk rule no route may break: slope, distance from the habitat, walk time, walk-back, daylight, hazard margin.

**Walk-back rule**:
The crew must always have the time and supplies to walk home from any point on the route.

**Hazard margin**:
The distance kept from steep drops, which grows with the uncertainty circle.

**Science alternative**:
The second route, which passes more science targets and shows the extra time it costs.

**Location-aware routing**:
Route planning that prefers ground where location quality is high.

## Walk simulation

**Break-it scenario**:
A simulated failure the demo can switch on: camera off, radio off, drone grounded, or everything at once.

**Lost mode**:
The state when no source can be trusted: the app shows the last known position, a return direction and landmark directions.

**Offline mode**:
The state when the radio link to the habitat is down and the tablet computes alone.

## Build

**Contract**:
One of the agreed file or request formats between two owners' parts.
_Avoid_: interface, format

**Stub**:
A fake file for a contract, so work can start before the real data exists.

**Results file**:
A file a script writes that holds measured or simulated numbers, and which script, commit and inputs wrote it.

**Demo cache**:
The saved response for every step of the 3-minute demo, so the demo runs with the service down and Wi-Fi off.

**Gate**:
An hour when all four people stop, merge and run the smoke test together: H0, H6, H12, H14, H18 and H24.

**Ticket**:
One unit of work with an ID like P3-02, tracked as a GitHub issue.

**Owner**:
The person whose folders a ticket's work lives in.
