// The layers panel: one colour layer at a time over the base photo map, the points on top,
// and the shown layer's legend, which always states its resolution.
import type { LayerMeta } from "@contracts/layer";
import { CloseIcon } from "../ui/icons";
import { formatResolution } from "./geo";
import type { PointsShown } from "./WalkMap";

interface Props {
  baseLayer: LayerMeta | undefined;
  colourLayers: LayerMeta[];
  colourLayer: string | null;
  onColourLayer: (name: string | null) => void;
  points: PointsShown;
  counts: Record<keyof PointsShown, number>;
  onPoints: (points: PointsShown) => void;
  onClose: () => void;
}

const POINT_NAMES: Record<keyof PointsShown, string> = {
  targets: "Science targets",
  checkpoints: "Checkpoints",
  habitatAndCamp: "Habitat and base camp",
};

function describe(layer: LayerMeta) {
  return `${layer.source[0].name} · ${formatResolution(layer.resolution_m)}`;
}

export function LayersPanel(props: Props) {
  const { baseLayer, colourLayers, colourLayer, points } = props;
  const shown = colourLayers.find((layer) => layer.name === colourLayer) ?? baseLayer;
  const options = [
    { name: null, title: "Base photo map only", layer: baseLayer },
    ...colourLayers.map((layer) => ({ name: layer.name, title: layer.title, layer })),
  ];

  return (
    <aside className="layers" aria-label="Layers">
      <div className="layers__head">
        <h2 className="layers__title">Layers</h2>
        <button type="button" className="control" aria-label="Close layers" onClick={props.onClose}>
          <CloseIcon />
        </button>
      </div>

      <div className="layers__scroll">
        <div className="section-head">
          <span className="label">Colour layer · one at a time</span>
        </div>
        {options.map((option) => {
          const on = option.name === colourLayer;
          return (
            <label key={option.name ?? "base"} className={`layer-option${on ? " layer-option--on" : ""}`}>
              <input
                type="radio"
                name="colour-layer"
                checked={on}
                onChange={() => props.onColourLayer(option.name)}
              />
              <span className="layer-option__text">
                <span className="layer-option__name">{option.title}</span>
                {option.layer && <span className="data">{describe(option.layer)}</span>}
              </span>
            </label>
          );
        })}
        {colourLayers.length === 0 && (
          <p className="empty-note">
            No colour layers yet: slope, walkability and location quality appear here as their
            layer files land.
          </p>
        )}

        <div className="section-head">
          <span className="label">Points on top</span>
        </div>
        {(Object.keys(POINT_NAMES) as (keyof PointsShown)[]).map((key) => (
          <label key={key} className="toggle">
            <input
              type="checkbox"
              checked={points[key]}
              onChange={() => props.onPoints({ ...points, [key]: !points[key] })}
            />
            <span className="toggle__name">{POINT_NAMES[key]}</span>
            <span className="data">{props.counts[key]}</span>
          </label>
        ))}
      </div>

      {shown && (
        <div className="layers__legend">
          <span className="label">
            Legend · {shown.title} · {formatResolution(shown.resolution_m)}
          </span>
          {shown.legend.map((entry) => (
            <span key={entry.label} className="legend-swatch">
              <span className="legend-swatch__colour" style={{ background: entry.color }} />
              <span className="data" style={{ color: "#f2f5fa" }}>
                {entry.label}
              </span>
            </span>
          ))}
        </div>
      )}
    </aside>
  );
}
