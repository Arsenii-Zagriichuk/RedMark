// The Walk view (P1-05): the wrist-tablet screen during the walk. It plays a simulated walk
// along the chosen route: the dot with its uncertainty circle and confidence %, the next
// waypoint, time and distance left, the walk-back margin and the conditions strip. Every
// value comes from POST /simulate, the route and the sol file; the walk is labelled simulated.
import type { Conditions } from "@contracts/conditions";
import type { LayerMeta } from "@contracts/layer";
import type { RouteResponse } from "@contracts/route_response";
import type { Point, ScienceTarget, SiteConfig } from "@contracts/site";
import type { SimulateResponse } from "@contracts/simulate_response";
import { useEffect, useMemo, useState } from "react";
import { useApi } from "../api/ApiContext";
import { distanceAndBearing, formatDistance } from "../map/geo";
import { WalkMap, type CrewPosition } from "../map/WalkMap";
import { formatDuration } from "../plan/routes";
import { conditionsAt } from "./conditions";
import { fixEvents, walkStatus } from "./playback";
import { simulateRequest } from "./schedule";

interface Props {
  site: SiteConfig;
  origin: Point;
  baseLayer: LayerMeta | undefined;
  route: RouteResponse;
  step: string;
  target: ScienceTarget;
  conditions: Conditions | null;
  onEnd: () => void;
}

const STEP_MS = 150;
const METHOD_LETTERS = { horizon: "H", ground: "G", drone: "D" } as const;

export function WalkScreen(props: Props) {
  const { site, origin, route, target, conditions } = props;
  const { client } = useApi();
  const [simulation, setSimulation] = useState<SimulateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    let cancelled = false;
    client.simulate(props.step, simulateRequest(route)).then(
      (result) => !cancelled && setSimulation(result),
      (reason: unknown) =>
        !cancelled && setError(reason instanceof Error ? reason.message : String(reason)),
    );
    return () => {
      cancelled = true;
    };
  }, [client, props.step, route]);

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
  const mapRoutes = useMemo(
    () => [{ id: "walk-route", path: route.path, label: "", chosen: true }],
    [route],
  );

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

      {status && (
        <div className="walk__banner">
          <span className="walk__arrow" aria-hidden="true">
            <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" style={{ transform: `rotate(${status.waypointBearing - heading}deg)` }}>
              <path d="M12 20V4M5 11l7-7 7 7" />
            </svg>
          </span>
          <span className="walk__instruction">
            <span>{status.instruction}</span>
            <span className="walk__instruction-distance">{formatDistance(status.waypointDistance_m)}</span>
          </span>
        </div>
      )}

      <div className="walk__top-right">
        {simulation?.simulated && <span className="chip chip--simulated">Simulated walk</span>}
        {(["Camera", "Radio", "Drone"] as const).map((source) => (
          <button key={source} type="button" className="pill" disabled title="Break-it buttons arrive in P1-07">
            {source}
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
                title={event.kind === "fix" ? `${event.method} fix at ${formatDuration(event.t_s)}` : `fix requested at ${formatDuration(event.t_s)}`}
                onClick={() => {
                  setPlaying(false);
                  setIndex(event.index);
                }}
              >
                {event.method ? METHOD_LETTERS[event.method] : "!"}
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
