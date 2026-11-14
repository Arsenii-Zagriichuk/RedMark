// The Walk view (P1-05): the wrist-tablet screen during the walk. It plays a simulated walk
// along the chosen route: the dot with its uncertainty circle and confidence %, the next
// waypoint, time and distance left, the walk-back margin and the conditions strip. Every
// value comes from POST /simulate, the route and the sol file; the walk is labelled simulated.
// The break-it buttons (P1-07) re-run the walk with sources switched off; when no source
// can be trusted, Lost mode shows the last known position, the walk back and layer 5's
// landmark directions.
import type { Conditions } from "@contracts/conditions";
import type { LayerMeta } from "@contracts/layer";
import type { RouteRequest } from "@contracts/route_request";
import type { RouteResponse } from "@contracts/route_response";
import type { Point, ScienceTarget, SiteConfig } from "@contracts/site";
import type { SimulateResponse } from "@contracts/simulate_response";
import { useEffect, useMemo, useState } from "react";
import { useApi } from "../api/ApiContext";
import { distanceAndBearing, formatBearing, formatDistance, formatLatLon } from "../map/geo";
import { WalkMap, type CrewPosition, type MapRoute } from "../map/WalkMap";
import { formatDuration, limitRows, refusal } from "../plan/routes";
import { walkBadges } from "./breakIt";
import { conditionsAt } from "./conditions";
import { landmarkDirectionsFor } from "./layer5";
import {
  landmarkDirection,
  lostModeStart,
  returnHeading,
  returnRequest,
  samePoint,
  type LostDirection,
} from "./lost";
import { fixEvents, indexAtTime, walkStatus, type FixEvent } from "./playback";
import { simulateRequest, type Scenario } from "./schedule";

interface Props {
  site: SiteConfig;
  origin: Point;
  baseLayer: LayerMeta | undefined;
  route: RouteResponse;
  /** The request that planned the route; Lost mode plans the walk back from it. */
  request: RouteRequest;
  /** Which walk, in its demo step ids: `<route mode>.<target id>.<slope limit>`. */
  walkKey: string;
  target: ScienceTarget;
  conditions: Conditions | null;
  onEnd: () => void;
}

const STEP_MS = 150;
const METHOD_LETTERS = { horizon: "H", ground: "G", drone: "D" } as const;
const BREAK_IT: { scenario: Scenario; label: string }[] = [
  { scenario: "camera-off", label: "Camera off" },
  { scenario: "radio-off", label: "Radio off" },
  { scenario: "drone-grounded", label: "Drone grounded" },
  { scenario: "everything", label: "Everything" },
];

type WalkBack = { status: "ok"; route: RouteResponse } | { status: "error"; message: string };

function eventTitle(event: FixEvent): string {
  const at = `at ${formatDuration(event.t_s)}`;
  switch (event.kind) {
    case "fix":
      return `${event.method} fix${event.buddy ? " from the buddy's camera" : ""} ${at}`;
    case "fix_unavailable":
      return `${event.method} fix can't reach the crew ${at}`;
    case "lost_mode":
      return `lost mode ${at}`;
    default:
      return `fix requested ${at}`;
  }
}

function eventLetter(event: FixEvent): string {
  if (event.kind === "lost_mode") return "L";
  return event.method ? METHOD_LETTERS[event.method] : "!";
}

function directionText(direction: LostDirection): { text: string; note: string | null } {
  switch (direction.kind) {
    case "landmark":
      return {
        text: direction.text,
        note: `Walking back · in view along leg ${direction.leg + 1} of ${direction.legs}`,
      };
    case "none-in-view":
      return { text: `No landmark in view along leg ${direction.leg + 1} of ${direction.legs}`, note: null };
    case "not-this-route":
      return { text: "Layer 5 has no landmark directions for this route yet", note: null };
  }
}

export function WalkScreen(props: Props) {
  const { site, origin, route, target, conditions } = props;
  const { client } = useApi();
  const [scenario, setScenario] = useState<Scenario>("normal");
  // The walk's time when a break-it button was pressed, so the new run carries on from there.
  const [resumeAt, setResumeAt] = useState(0);
  const [run, setRun] = useState<{ scenario: Scenario; simulation: SimulateResponse } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const simulation = run?.simulation ?? null;

  useEffect(() => {
    let cancelled = false;
    setError(null);
    client.simulate(`walk.simulate.${scenario}.${props.walkKey}`, simulateRequest(route, scenario)).then(
      (result) => {
        if (cancelled) return;
        setRun({ scenario, simulation: result });
        setIndex(indexAtTime(result, resumeAt));
      },
      (reason: unknown) => {
        if (cancelled) return;
        // Never leave the last run on screen under another scenario's button.
        setRun(null);
        setError(reason instanceof Error ? reason.message : String(reason));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [client, props.walkKey, route, scenario, resumeAt]);

  // Play: one simulation step at a time, stopping at the end.
  const last = (simulation?.steps.length ?? 1) - 1;
  useEffect(() => {
    if (!playing) return;
    if (index >= last) {
      setPlaying(false);
      return;
    }
    const timer = setTimeout(() => setIndex((current) => Math.min(current + 1, last)), STEP_MS);
    return () => clearTimeout(timer);
  }, [playing, index, last]);

  const status = simulation && walkStatus(simulation, index, route, target.name);
  const events = useMemo(() => (simulation ? fixEvents(simulation) : []), [simulation]);
  const now = conditions && status ? conditionsAt(conditions, status.t_s) : null;

  // Direction of travel: from the last place the estimate moved from.
  const heading = useMemo(() => {
    if (!simulation) return 0;
    const here = simulation.steps[index]!.estimated_position;
    for (let i = index - 1; i >= 0; i--) {
      const before = simulation.steps[i]!.estimated_position;
      if (Math.hypot(here.x - before.x, here.y - before.y) > 0.5) {
        return distanceAndBearing(before, here).bearing;
      }
    }
    return distanceAndBearing(route.path[0]!, route.path[1] ?? route.path[0]!).bearing;
  }, [simulation, index, route]);

  const crew = useMemo<CrewPosition | null>(
    () =>
      status && {
        position: status.position,
        uncertainty_m: status.uncertainty_m,
        level: status.level,
        chip: `±${Math.round(status.uncertainty_m)} m · ${Math.round(status.confidence_pct)}%`,
        heading,
      },
    // A new crew only when the step changes, so the map doesn't re-follow on other renders.
    [simulation, index, heading],
  );
  // Lost mode: from where it began, the walk back to the start with the circle as its hazard
  // margin, so the route moves further from steep ground than the planned one.
  const lostStart = useMemo(() => (simulation ? lostModeStart(simulation) : null), [simulation]);
  const lastKnown = lostStart && index >= lostStart.index ? lostStart : null;
  const [walkBack, setWalkBack] = useState<WalkBack | null>(null);
  const { request, walkKey } = props;
  const runScenario = run?.scenario;
  useEffect(() => {
    setWalkBack(null);
    if (!lastKnown) return;
    let cancelled = false;
    client.route(`walk.route.back.${runScenario}.${walkKey}`, returnRequest(request, lastKnown)).then(
      (result) => !cancelled && setWalkBack({ status: "ok", route: result }),
      (reason: unknown) => !cancelled && setWalkBack({ status: "error", message: refusal(reason) }),
    );
    return () => {
      cancelled = true;
    };
  }, [client, lastKnown, request, runScenario, walkKey]);

  const back = walkBack?.status === "ok" ? walkBack.route : null;
  const straightBack = lastKnown && distanceAndBearing(lastKnown.position, request.start);
  const backHeading = back ? returnHeading(back.path) : straightBack?.bearing ?? 0;
  const startName = samePoint(request.start, site.base_camp)
    ? "base camp"
    : samePoint(request.start, site.habitat)
      ? "the habitat"
      : "the start";
  const direction = useMemo(
    () =>
      lastKnown &&
      directionText(
        landmarkDirection(landmarkDirectionsFor(site.site), route, lastKnown.position, backHeading),
      ),
    [lastKnown, route, site.site, backHeading],
  );
  const hazardMargin = back && limitRows(back).find((row) => row.limit === "hazard_margin");
  const badges = simulation ? walkBadges(simulation, index) : [];

  const mapRoutes = useMemo<MapRoute[]>(
    () =>
      lastKnown && back
        ? [
            { id: "walk-route", path: route.path, label: "", chosen: false },
            { id: "walk-back", path: back.path, label: `Back · ${formatDuration(back.total_time_s)}`, chosen: true },
          ]
        : [{ id: "walk-route", path: route.path, label: "", chosen: true }],
    [route, lastKnown, back],
  );

  const breakIt = (next: Scenario) => {
    setResumeAt(status?.t_s ?? 0);
    setScenario((current) => (current === next ? "normal" : next));
  };

  return (
    <div className="walk">
      <WalkMap
        site={site}
        origin={origin}
        baseLayer={props.baseLayer}
        colourLayer={undefined}
        points={{ targets: true, checkpoints: true, habitatAndCamp: true }}
        selectedTargetId={target.id}
        onSelectTarget={() => {}}
        layersOpen={false}
        onToggleLayers={() => {}}
        fileUrl={client.fileUrl}
        status={error && `Can't load the walk: ${error}`}
        routes={mapRoutes}
        fitTo={null}
        crew={crew}
      />

      <div className="walk__top-left">
        {status && (
          <div className={`walk__banner${lastKnown ? " walk__banner--lost" : ""}`}>
            <span className="walk__arrow" aria-hidden="true">
              <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" style={{ transform: `rotate(${(lastKnown ? backHeading : status.waypointBearing) - heading}deg)` }}>
                <path d="M12 20V4M5 11l7-7 7 7" />
              </svg>
            </span>
            <span className="walk__instruction">
              <span>
                {lastKnown ? `Head ${formatBearing(backHeading)} back to ${startName}` : status.instruction}
              </span>
              <span className="walk__instruction-distance">
                {formatDistance(
                  lastKnown ? (back?.total_distance_m ?? straightBack!.metres) : status.waypointDistance_m,
                )}
              </span>
            </span>
          </div>
        )}

        {badges.length > 0 && (
          <div className="walk__badges">
            {badges.map((badge) => (
              <span key={badge.id} className={`badge badge--${badge.id}`}>
                {badge.label}
              </span>
            ))}
          </div>
        )}

        {lastKnown && direction && (
          <section className="walk__lost" aria-label="Lost mode">
            <div className="walk__lost-head">
              <span className="walk__lost-title">Lost mode</span>
              <span className="chip chip--simulated">Simulated</span>
            </div>
            <div className="walk__lost-row">
              <span className="label">Last known position</span>
              <span className="walk__value">
                {formatLatLon(lastKnown.position, site.projection) ??
                  `${Math.round(lastKnown.position.x)}, ${Math.round(lastKnown.position.y)} m`}
              </span>
              <span className="walk__lost-note">
                ±{Math.round(lastKnown.uncertainty_m)} m · {formatDuration(lastKnown.t_s)} into the walk
              </span>
            </div>
            <div className="walk__lost-row">
              <span className="label">Walk back · re-planned for the ±{Math.round(lastKnown.uncertainty_m)} m circle</span>
              {back ? (
                <>
                  <span className="walk__value">
                    {formatDistance(back.total_distance_m)} · {formatDuration(back.total_time_s)}
                  </span>
                  {hazardMargin && (
                    <span className="walk__lost-note">Hazard margin {hazardMargin.text}</span>
                  )}
                </>
              ) : walkBack?.status === "error" ? (
                <span className="walk__lost-note walk__lost-note--fail">
                  No safe route back: {walkBack.message}. The arrow points straight at {startName}.
                </span>
              ) : (
                <span className="walk__lost-note">Planning the walk back…</span>
              )}
            </div>
            <div className="walk__lost-row">
              <span className="label">Landmarks · layer 5</span>
              <span className="walk__lost-direction">{direction.text}</span>
              {direction.note && <span className="walk__lost-note">{direction.note}</span>}
            </div>
          </section>
        )}
      </div>

      <div className="walk__top-right">
        {simulation?.simulated && <span className="chip chip--simulated">Simulated walk</span>}
        {BREAK_IT.map(({ scenario: option, label }) => (
          <button
            key={option}
            type="button"
            className={`pill${scenario === option ? " pill--on" : ""}`}
            aria-pressed={scenario === option}
            onClick={() => breakIt(option)}
          >
            {label}
          </button>
        ))}
      </div>

      <section className="walk__sheet" aria-label="Walk">
        <div className="walk__stats">
          <div className="walk__stat">
            <span className="label">Time left</span>
            <span className="walk__readout">{status ? formatDuration(status.timeLeft_s) : "…"}</span>
          </div>
          <div className="walk__stat">
            <span className="label">Distance left</span>
            <span className="walk__readout">{status ? formatDistance(status.distanceLeft_m) : "…"}</span>
          </div>
          <div className="walk__stat">
            <span className="label">Walk-back margin · planned</span>
            <span className="walk__readout walk__readout--ok">{formatDuration(route.walk_back_margin_s)}</span>
          </div>
          <button type="button" className="button button--secondary walk__fix" disabled title="The Photo checkpoint arrives in P1-08">
            Take fix
          </button>
        </div>

        {now && (
          <div className="walk__conditions">
            <span className="walk__condition">
              <span className="label">Local time</span>
              <span className="walk__value">{now.lmst} LMST</span>
            </span>
            <span className="walk__condition">
              <span className="label">Radiation</span>
              <span className="walk__value">{now.radiation}</span>
              <span className="tag" title="Measured by Curiosity's RAD">RAD</span>
            </span>
            <span className="walk__condition">
              <span className="label">Temp</span>
              <span className="walk__value">{now.temperature}</span>
              <span className="tag" title="Measured by Curiosity's REMS">REMS</span>
            </span>
            <span className="walk__condition">
              <span className="label">Dust</span>
              <span className="walk__value">{now.dust}</span>
              <span className={`tag tag--${now.dustSource}`}>{now.dustSource}</span>
            </span>
            <span className="walk__condition">
              <span className="label">Sunset in</span>
              <span className="walk__value">{now.sunsetIn}</span>
            </span>
          </div>
        )}

        <div className="walk__playback">
          <button
            type="button"
            className="control control--large"
            aria-label={playing ? "Pause" : "Play"}
            disabled={!simulation}
            onClick={() => {
              if (index >= last) setIndex(0);
              setPlaying((on) => !on);
            }}
          >
            {playing ? "❚❚" : "▶"}
          </button>
          <div className="timeline">
            <input
              type="range"
              min={0}
              max={last}
              value={index}
              aria-label="Walk timeline"
              onChange={(event) => {
                setPlaying(false);
                setIndex(Number(event.target.value));
              }}
            />
            {events.map((event) => (
              <button
                key={`${event.index}-${event.kind}`}
                type="button"
                className={`timeline__event timeline__event--${event.kind}`}
                style={{ left: `${event.fraction * 100}%` }}
                title={eventTitle(event)}
                onClick={() => {
                  setPlaying(false);
                  setIndex(event.index);
                }}
              >
                {eventLetter(event)}
              </button>
            ))}
          </div>
          <span className="data walk__clock">
            {status ? `${formatDuration(status.t_s)} / ${formatDuration(simulation!.steps[last]!.t_s)}` : ""}
          </span>
          <button type="button" className="button button--secondary walk__end" onClick={props.onEnd}>
            End walk
          </button>
        </div>
      </section>
    </div>
  );
}
