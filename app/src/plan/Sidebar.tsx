// The Plan screen's sidebar: search, the science targets with their distance and bearing
// from the habitat, what is on the map, and the replayed sol. Picking a target opens its
// place card instead of the list.
import type { Conditions } from "@contracts/conditions";
import type { Point, ScienceTarget, SiteConfig } from "@contracts/site";
import { useApi } from "../api/ApiContext";
import {
  distanceAndBearing,
  formatBearing,
  formatDistance,
  formatLatLon,
} from "../map/geo";
import { ClockIcon, CloseIcon, FlagIcon, HouseIcon, PinIcon, SearchIcon } from "../ui/icons";
import { PlaceCard } from "./PlaceCard";

interface Props {
  site: SiteConfig | null;
  conditions: Conditions | null;
  query: string;
  onQuery: (query: string) => void;
  selected: ScienceTarget | undefined;
  onSelect: (id: string | null) => void;
  onDirections: () => void;
}

function fromHabitat(habitat: Point | null, target: Point): string | null {
  if (!habitat) return null;
  const { metres, bearing } = distanceAndBearing(habitat, target);
  return `${formatDistance(metres)} · ${formatBearing(bearing)} from habitat`;
}

function ModeSwitch() {
  const { mode, setMode } = useApi();
  return (
    <button
      type="button"
      className={`mode-switch${mode === "demo" ? " mode-switch--demo" : ""}`}
      onClick={() => setMode(mode === "live" ? "demo" : "live")}
      title={mode === "live" ? "Answers come from the service" : "Answers come from the demo cache"}
    >
      {mode === "live" ? "Live" : "Demo · cache"}
    </button>
  );
}

export function Sidebar(props: Props) {
  const { site, conditions, query, onQuery, selected, onSelect } = props;
  const targets = (site?.science_targets ?? []).filter((target) =>
    target.name.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const latLon = (point: Point | null) =>
    point && site ? formatLatLon(point, site.projection) : null;

  return (
    <aside className="sidebar">
      <div className="sidebar__top">
        <div className="brand">
          <span className="brand__dot" />
          RedMark
        </div>
        <label className="search">
          <SearchIcon />
          <input
            type="text"
            placeholder="Where to?"
            aria-label="Where to?"
            value={selected ? selected.name : query}
            onChange={(event) => {
              onSelect(null);
              onQuery(event.target.value);
            }}
          />
          {(selected || query) && (
            <button
              type="button"
              className="search__clear"
              aria-label="Clear"
              onClick={() => {
                onSelect(null);
                onQuery("");
              }}
            >
              <CloseIcon stroke="#9aa6bf" />
            </button>
          )}
        </label>
      </div>
      <div className="rule" />

      <div className="sidebar__scroll">
        {selected && site ? (
          <PlaceCard target={selected} habitat={site.habitat} onDirections={props.onDirections} />
        ) : (
          <>
            <div className="section-head">
              <span className="label">Science targets</span>
              <span className="label">From habitat</span>
            </div>
            {targets.map((target) => (
              <button
                key={target.id}
                type="button"
                className="target-row"
                onClick={() => onSelect(target.id)}
              >
                <span className="target-row__icon" />
                <span className="target-row__text">
                  <span className="target-row__name">{target.name}</span>
                  <span className="data">{fromHabitat(site?.habitat ?? null, target.position)}</span>
                </span>
              </button>
            ))}
            {site && targets.length === 0 && (
              <p className="empty-note">No science target matches “{query}”.</p>
            )}

            <div className="section-head">
              <span className="label">On the map</span>
            </div>
            <div className="legend-row">
              <span className="symbol-habitat" style={{ width: 22, height: 22 }}>
                <HouseIcon size={12} />
              </span>
              <span className="legend-row__name">Habitat</span>
              <span className="data">{latLon(site?.habitat ?? null)}</span>
            </div>
            <div className="legend-row">
              <span className="symbol-camp" style={{ width: 22, height: 22 }}>
                <FlagIcon size={13} />
              </span>
              <span className="legend-row__name">Base camp</span>
              <span className="data">{latLon(site?.base_camp ?? null)}</span>
            </div>
            <div className="legend-row">
              <span className="symbol-checkpoint" style={{ width: 20, height: 20 }}>
                1
              </span>
              <span className="legend-row__name">Checkpoints</span>
              <span className="data">{site?.checkpoints.length ?? ""}</span>
            </div>
          </>
        )}
      </div>

      <div className="rule" />
      <div className="sidebar__footer">
        {selected ? <PinIcon /> : <ClockIcon />}
        <span className="data">
          {selected
            ? latLon(selected.position)
            : conditions && `Sol ${conditions.sol} · sunset ${conditions.sunset_lmst} LMST`}
        </span>
        <ModeSwitch />
      </div>
    </aside>
  );
}
