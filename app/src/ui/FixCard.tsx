// The one component that shows a fix (AGENTS.md rule 8): its uncertainty circle, heading,
// confidence, time per fix and terrain type, with the Simulated label whenever the fix is
// simulated. A simulated fix shows the pipeline, not accuracy, so no numbers are reported
// from it (team plan, Gale drone fix).
import type { FixResult } from "@contracts/fix_result";
import { formatBearing } from "../map/geo";

const METHOD_NAMES = { horizon: "Horizon fix", ground: "Ground fix", drone: "Drone fix" } as const;

function Value({ label, children }: { label: string; children: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="data">{children}</dd>
    </div>
  );
}

export function FixCard({ fix }: { fix: FixResult }) {
  return (
    <section className="fix-card" aria-label={METHOD_NAMES[fix.method]}>
      <div className="fix-card__head">
        <span className="fix-card__title">{METHOD_NAMES[fix.method]}</span>
        {fix.simulated && <span className="chip chip--simulated">Simulated</span>}
      </div>
      {fix.simulated ? (
        <p className="fix-card__note">No numbers are reported from a simulated fix.</p>
      ) : (
        <dl className="fix-card__values">
          <Value label="Circle">{`±${Math.round(fix.uncertainty_m)} m`}</Value>
          <Value label="Heading">{formatBearing(fix.heading_deg)}</Value>
          <Value label="Confidence">{`${Math.round(fix.confidence_pct)}%`}</Value>
          <Value label="Time per fix">{`${fix.time_per_fix_s.toFixed(1)} s`}</Value>
          <Value label="Terrain">{fix.terrain_type}</Value>
        </dl>
      )}
    </section>
  );
}
