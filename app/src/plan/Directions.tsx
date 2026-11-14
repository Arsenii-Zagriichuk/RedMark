// The Planning screen's directions (P1-04): the three route options, the chosen route's
// total time, walk-back margin and every walk limit marked pass, fail or not checked, and
// the slope limit, which re-plans all three routes in place.
import type { RouteMode } from "@contracts/route_request";
import type { RouteResponse } from "@contracts/route_response";
import type { ScienceTarget, SiteConfig } from "@contracts/site";
import { formatDistance } from "../map/geo";
import {
  formatDuration,
  limitRows,
  ROUTE_MODES,
  SLOPE_LIMITS,
  type SlopeLimit,
} from "./routes";

export type RouteState =
  | { status: "loading" }
  | { status: "ok"; route: RouteResponse }
  | { status: "error"; message: string }
  | { status: "none"; message: string };

interface Props {
  site: SiteConfig;
  target: ScienceTarget;
  routes: Record<RouteMode, RouteState>;
  chosen: RouteMode;
  onChoose: (mode: RouteMode) => void;
  slopeLimit: SlopeLimit;
  onSlopeLimit: (limit: SlopeLimit) => void;
  onBack: () => void;
}

const MODE_NAMES: Record<RouteMode, string> = {
  fastest: "Fastest safe",
  science: "Science alternative",
  cart: "Cart to base camp",
};

const CHIP_TEXT = { pass: "Pass", fail: "Fail", "not-checked": "Not checked" } as const;

function optionSummary(mode: RouteMode, state: RouteState): { main: string; note: string } {
  if (state.status === "loading") return { main: "planning…", note: "" };
  if (state.status !== "ok") return { main: "no safe route", note: "" };
  const { route } = state;
  if (mode === "science" && route.extra_time_vs_fastest_s !== null) {
    return {
      main: `+${formatDuration(route.extra_time_vs_fastest_s)}`,
      note: formatDistance(route.total_distance_m),
    };
  }
  return { main: formatDuration(route.total_time_s), note: formatDistance(route.total_distance_m) };
}

export function Directions(props: Props) {
  const { site, target, routes, chosen } = props;
  const state = routes[chosen];
  const from = site.base_camp ? "Base camp" : "Habitat";
  const crumbs = chosen === "cart" ? "Habitat → Base camp" : `${from} → ${target.name}`;

  return (
    <aside className="sidebar directions">
      <div className="directions__head">
        <button type="button" className="control" aria-label="Back to the place card" onClick={props.onBack}>
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f2f5fa" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 6l-6 6 6 6" />
          </svg>
        </button>
        <div>
          <div className="directions__crumbs">{crumbs}</div>
          <h2 className="directions__title">Directions</h2>
        </div>
      </div>
      <div className="rule" />

      <div className="sidebar__scroll">
        <div className="route-options">
          {ROUTE_MODES.map((mode) => {
            const { main, note } = optionSummary(mode, routes[mode]);
            const on = mode === chosen;
            return (
              <button
                key={mode}
                type="button"
                className={`route-option${on ? " route-option--on" : ""}`}
                onClick={() => props.onChoose(mode)}
                aria-pressed={on}
              >
                <span className={`route-option__swatch${on ? " route-option__swatch--on" : ""}`} />
                <span className="route-option__name">{MODE_NAMES[mode]}</span>
                <span className="route-option__time">{main}</span>
                <span className="data">{note}</span>
              </button>
            );
          })}
        </div>
        <div className="rule" />

        {state.status === "ok" && <RouteSummary mode={chosen} route={state.route} />}
        {state.status === "loading" && <p className="empty-note">Planning the route…</p>}
        {(state.status === "error" || state.status === "none") && (
          <p className="route-refused">No safe route: {state.message}</p>
        )}

        <div className="slope-limit">
          <span className="label">Slope limit</span>
          <div className="segmented" role="radiogroup" aria-label="Slope limit">
            {SLOPE_LIMITS.map((limit) => (
              <button
                key={limit}
                type="button"
                role="radio"
                aria-checked={limit === props.slopeLimit}
                className={`segmented__option${limit === props.slopeLimit ? " segmented__option--on" : ""}`}
                onClick={() => props.onSlopeLimit(limit)}
              >
                {limit}°
              </button>
            ))}
          </div>
          <span className="data">re-routes in place</span>
        </div>
      </div>

      <div className="rule" />
      <div className="directions__foot">
        <button
          type="button"
          className="button button--primary"
          disabled
          title="The Walk view arrives in P1-05"
        >
          Start walk
        </button>
        <span className="data">The Walk view arrives in P1-05</span>
      </div>
    </aside>
  );
}

function RouteSummary({ mode, route }: { mode: RouteMode; route: RouteResponse }) {
  const rows = limitRows(route);
  const checked = rows.filter((row) => row.status !== "not-checked");
  const passed = checked.filter((row) => row.status === "pass").length;
  const allPass = passed === checked.length;
  const details = [formatDistance(route.total_distance_m)];
  if (mode !== "cart") details.push(`walk-back margin ${formatDuration(route.walk_back_margin_s)}`);

  return (
    <div className="route-summary">
      <span className="label">Total time</span>
      <div className="route-summary__readout">
        <span className="route-summary__time">{formatDuration(route.total_time_s)}</span>
        <span className={`chip chip--${allPass ? "pass" : "fail"}`}>
          {passed}/{checked.length} limits pass
        </span>
      </div>
      <span className="data">{details.join(" · ")}</span>
      <div className="limit-rows">
        {rows.map((row) => (
          <div key={row.limit} className="limit-row">
            <span className="limit-row__label">{row.label}</span>
            <span className={`data limit-row__value limit-row__value--${row.status}`}>
              {row.text}
            </span>
            <span className={`chip chip--${row.status}`}>{CHIP_TEXT[row.status]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
