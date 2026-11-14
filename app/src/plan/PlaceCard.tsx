// A science target's place card. Directions opens the Planning screen's routes (P1-04);
// the photos and Photos open the Target preview's Curiosity pictures (P1-09).
import type { Point, ScienceTarget } from "@contracts/site";
import { useState } from "react";
import { distanceAndBearing, formatBearing, formatDistance } from "../map/geo";
import { picturesFor, targetPictures } from "../target/pictures";
import { TargetPreview } from "../target/TargetPreview";
import { PhotoIcon, RouteIcon } from "../ui/icons";
import { WithFallback } from "../ui/WithFallback";

interface Props {
  target: ScienceTarget;
  habitat: Point | null;
  onDirections: () => void;
}

export function PlaceCard({ target, habitat, onDirections }: Props) {
  const away = habitat && distanceAndBearing(habitat, target.position);
  const [previewing, setPreviewing] = useState(false);
  const thumbnails = picturesFor(targetPictures, target.id).slice(0, 2);
  return (
    <section className="place" aria-label={target.name}>
      <button type="button" className="place__photos" title="Curiosity's pictures" onClick={() => setPreviewing(true)}>
        {thumbnails.map((picture) => (
          <WithFallback key={picture.image_id} src={picture.file} fallback={targetPictures.fallback.file} alt="" />
        ))}
      </button>
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
        <button type="button" className="button button--primary" onClick={onDirections}>
          <RouteIcon /> Directions
        </button>
        <button type="button" className="button button--secondary" onClick={() => setPreviewing(true)}>
          <PhotoIcon /> Photos
        </button>
      </div>
      {previewing && <TargetPreview target={target} onClose={() => setPreviewing(false)} />}
    </section>
  );
}
