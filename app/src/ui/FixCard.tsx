// The one component that shows a fix (AGENTS.md rule 8): its uncertainty circle, heading,
// time per fix and terrain type, with the Simulated label whenever the fix is simulated.
// A simulated fix is not measured, so it shows no confidence.
import type { FixResult } from "@contracts/fix_result";
import { formatBearing } from "../map/geo";

const METHOD_NAMES = { horizon: "Horizon fix", ground: "Ground fix", drone: "Drone fix" } as const;

export function FixCard({ fix }: { fix: FixResult }) {
  return (
    <section className="fix-card" aria-label={METHOD_NAMES[fix.method]}>
      <div className="fix-card__head">
        <span className="fix-card__title">{METHOD_NAMES[fix.method]}</span>
        {fix.simulated && <span className="chip chip--simulated">Simulated</span>}
      </div>
      <dl className="fix-card__values">
        <div>
          <dt className="label">Circle</dt>
          <dd className="data">±{Math.round(fix.uncertainty_m)} m</dd>
        </div>
        <div>
          <dt className="label">Heading</dt>
          <dd className="data">{formatBearing(fix.heading_deg)}</dd>
        </div>
        <div>
          <dt className="label">Confidence</dt>
          <dd className="data">{fix.simulated ? "not measured" : `${Math.round(fix.confidence_pct)}%`}</dd>
        </div>
        <div>
          <dt className="label">Time per fix</dt>
          <dd className="data">{fix.time_per_fix_s.toFixed(1)} s</dd>
        </div>
        <div>
          <dt className="label">Terrain</dt>
          <dd className="data">{fix.terrain_type}</dd>
        </div>
      </dl>
    </section>
  );
}
