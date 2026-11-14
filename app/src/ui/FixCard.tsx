// The one component that shows a fix (AGENTS.md rule 8): the method, where the fix came
// from, and its label, printed from the fix's own simulated flag, so a simulated fix can't be
// shown without "Simulated". The numbers go inside.
import type { Method } from "@contracts/fix_result";
import type { ReactNode } from "react";

const METHOD_NAMES = { horizon: "Horizon fix", ground: "Ground fix", drone: "Drone fix" } as const;

interface Props {
  method: Method;
  /** From the results file, never decided by the screen. */
  simulated: boolean;
  /** Where the fix came from, such as the photo it was made from. */
  source: string;
  children: ReactNode;
}

export function FixCard({ method, simulated, source, children }: Props) {
  return (
    <section className="fix-card" aria-label={METHOD_NAMES[method]}>
      <div className="fix-card__head">
        <span className="fix-card__title">{METHOD_NAMES[method]}</span>
        {simulated ? (
          <span className="chip chip--simulated">Simulated</span>
        ) : (
          <span className="chip chip--measured">Measured</span>
        )}
      </div>
      <span className="data">{source}</span>
      {children}
    </section>
  );
}
