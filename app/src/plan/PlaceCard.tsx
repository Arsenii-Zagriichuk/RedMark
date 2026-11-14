// A science target's place card. Photos are placeholders until the Target preview (P1-09)
// and Directions arrive with the Planning screen's routes (P1-04).
import type { Point, ScienceTarget } from "@contracts/site";
import { distanceAndBearing, formatBearing, formatDistance } from "../map/geo";
import { PhotoIcon, RouteIcon } from "../ui/icons";

export function PlaceCard({ target, habitat }: { target: ScienceTarget; habitat: Point | null }) {
  const away = habitat && distanceAndBearing(habitat, target.position);
  return (
    <section className="place" aria-label={target.name}>
      <div className="place__photos" aria-hidden="true">
        <div className="placeholder" />
        <div className="placeholder" />
      </div>
      <div>
        <h2 className="place__title">{target.name}</h2>
        <span className="data">Science target</span>
      </div>
      {away && (
        <div className="place__stats">
          <div className="place__stat">
            <span className="label">From habitat</span>
            <span className="place__stat-value">{formatDistance(away.metres)}</span>
          </div>
          <div className="place__stat">
            <span className="label">Bearing</span>
            <span className="place__stat-value">{formatBearing(away.bearing)}</span>
          </div>
        </div>
      )}
      <div className="place__actions">
        <button
          type="button"
          className="button button--primary"
          disabled
          title="Routes arrive with the Planning screen (P1-04)"
        >
          <RouteIcon /> Directions
        </button>
        <button
          type="button"
          className="button button--secondary"
          disabled
          title="Curiosity photos arrive with the Target preview (P1-09)"
        >
          <PhotoIcon /> Photos
        </button>
      </div>
    </section>
  );
}
