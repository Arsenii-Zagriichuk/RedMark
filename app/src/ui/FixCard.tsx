// The one component that shows a fix (AGENTS.md rule 8): its uncertainty circle, heading,
// confidence, time per fix and terrain type, with the Simulated label whenever the fix is
// simulated. The simulated Gale drone fix is cut from the map it is matched to, so it shows
// the pipeline, not accuracy, and no numbers are reported from it (team plan, Gale drone fix).
// Any other simulated fix shows its numbers with the label (P1-08's simulated ground fix).
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

/** The Gale drone demonstration: simulated, and its numbers mean nothing. */
const isGaleDroneDemo = (fix: FixResult) => fix.simulated && fix.method === "drone" && fix.site === "gale";

export function FixCard({ fix }: { fix: FixResult }) {
  return (
    <section className="fix-card" aria-label={METHOD_NAMES[fix.method]}>
      <div className="fix-card__head">
        <span className="fix-card__title">{METHOD_NAMES[fix.method]}</span>
        {fix.simulated && <span className="chip chip--simulated">Simulated</span>}
      </div>
      {isGaleDroneDemo(fix) ? (
        <p className="fix-card__note">No numbers are reported from the simulated Gale drone fix.</p>
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
