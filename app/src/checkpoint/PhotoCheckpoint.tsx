// The Photo checkpoint (P1-08): the guided capture at a checkpoint, over the Walk view. Prompts
// ("Face the skyline", "Turn left 90°", capture) fill a progress ring, then the horizon fix:
// the real one Person 3 cached from a Curiosity frame, in ±m with its confidence %, and its
// heading and position each with its error against the answer key. While confidence is low
// the app asks for photos facing other directions, which feed stage 2, the ground fix,
// labelled as Person 3's stage 2 results file says. Every value comes from a results file.
import { useEffect, useState } from "react";
import { useApi } from "../api/ApiContext";
import { FixCard } from "../ui/FixCard";
import { captureStep, roundName, type Round } from "./capture";
import { loadCheckpoint, type Checkpoint } from "./load";
import { fixReadout, stage2Readout, type FixReadout, type Stage2Readout } from "./readout";

type Phase = { kind: "capture"; round: Round; captured: number } | { kind: "result"; stage2: boolean };
type Ready<T> = Extract<T, { status: "ready" }>;

const RING_RADIUS = 52;
const RING_LENGTH = 2 * Math.PI * RING_RADIUS;

interface Props {
  /** The site map's projection, for the fix's latitude and longitude. */
  projection: string;
  onClose: () => void;
}

function Ring({ progress }: { progress: number }) {
  return (
    <svg className="checkpoint__ring" width="160" height="160" viewBox="0 0 120 120" aria-hidden="true">
      <circle className="checkpoint__ring-track" cx="60" cy="60" r={RING_RADIUS} fill="none" strokeWidth="8" />
      <circle
        className="checkpoint__ring-fill"
        cx="60"
        cy="60"
        r={RING_RADIUS}
        fill="none"
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={RING_LENGTH}
        strokeDashoffset={RING_LENGTH * (1 - progress)}
        transform="rotate(-90 60 60)"
      />
      <text className="checkpoint__ring-text" x="60" y="60" textAnchor="middle" dominantBaseline="central">
        {Math.round(progress * 100)}%
      </text>
    </svg>
  );
}

function CaptureView({ round, captured, onCapture }: { round: Round; captured: number; onCapture: () => void }) {
  const step = captureStep(round, captured);
  return (
    <div className="checkpoint__capture">
      <Ring progress={step.progress} />
      <div className="checkpoint__prompt">
        <span className="label">{roundName(round)}</span>
        <span className="checkpoint__instruction">{step.prompt}</span>
        <button type="button" className="button button--primary checkpoint__action" onClick={onCapture}>
          Capture
        </button>
      </div>
    </div>
  );
}

function Reading({ label, value, error }: { label: string; value: string; error: string | null }) {
  return (
    <div className="checkpoint__reading">
      <span className="label">{label}</span>
      <span className="checkpoint__value">{value}</span>
      {error && <span className="checkpoint__error">Error {error} against the answer key</span>}
    </div>
  );
}

function HorizonResult({ fix }: { fix: Ready<FixReadout> }) {
  return (
    <FixCard method={fix.method} simulated={fix.simulated} source={`Curiosity frame · ${fix.photoId}`}>
      <div className="checkpoint__headline">
        <span className="checkpoint__circle">{fix.circle}</span>
        <span className={`checkpoint__confidence${fix.lowConfidence ? " checkpoint__confidence--low" : ""}`}>
          {fix.confidence} confidence
        </span>
      </div>
      <div className="checkpoint__readings">
        <Reading label="Heading" value={fix.heading} error={fix.headingError} />
        <Reading label="Position" value={fix.position} error={fix.positionError} />
      </div>
    </FixCard>
  );
}

function Stage2Result({ stage2, test }: { stage2: Stage2Readout; test: string }) {
  if (stage2.status === "pending") {
    return <p className="empty-note">Ground fix pending: stage 2's results file is still a stub.</p>;
  }
  return (
    <FixCard method="ground" simulated={stage2.simulated} source={`Stage 2 results · ${test}`}>
      <div className="checkpoint__headline">
        <span className="checkpoint__circle">{stage2.medianError}</span>
        <span className="checkpoint__confidence">median error over {stage2.stops} stops</span>
      </div>
    </FixCard>
  );
}

export function PhotoCheckpoint({ projection, onClose }: Props) {
  const { client } = useApi();
  const [checkpoint, setCheckpoint] = useState<Checkpoint | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "capture", round: "skyline", captured: 0 });

  useEffect(() => {
    let cancelled = false;
    loadCheckpoint(client).then(
      (loaded) => !cancelled && setCheckpoint(loaded),
      (reason: unknown) => !cancelled && setError(reason instanceof Error ? reason.message : String(reason)),
    );
    return () => {
      cancelled = true;
    };
  }, [client]);

  const capture = () => {
    if (phase.kind !== "capture") return;
    const captured = phase.captured + 1;
    setPhase(
      captureStep(phase.round, captured).prompt === null
        ? { kind: "result", stage2: phase.round === "other-directions" }
        : { ...phase, captured },
    );
  };

  const horizon = checkpoint && fixReadout(checkpoint.fix, projection);

  return (
    <div className="checkpoint" role="dialog" aria-label="Photo checkpoint">
      <div className="checkpoint__panel">
        <div className="checkpoint__head">
          <span className="checkpoint__title">Photo checkpoint</span>
          <button type="button" className="control" aria-label="Back to the walk" onClick={onClose}>
            ✕
          </button>
        </div>

        {error && <p className="route-refused">Can't load the checkpoint's fix: {error}</p>}
        {phase.kind === "capture" ? (
          <CaptureView round={phase.round} captured={phase.captured} onCapture={capture} />
        ) : error ? null : !checkpoint || !horizon ? (
          <p className="empty-note">Matching the skyline…</p>
        ) : horizon.status === "pending" ? (
          <p className="empty-note">Horizon fix pending: the checkpoint's fix is still a stub.</p>
        ) : (
          <>
            <HorizonResult fix={horizon} />
            {phase.stage2 && <Stage2Result stage2={stage2Readout(checkpoint.stage2)} test={checkpoint.stage2.test} />}
            {horizon.lowConfidence && !phase.stage2 ? (
              <div className="checkpoint__ask">
                <span className="checkpoint__ask-text">Confidence is low. Take photos facing other directions.</span>
                <button
                  type="button"
                  className="button button--primary checkpoint__action"
                  onClick={() => setPhase({ kind: "capture", round: "other-directions", captured: 0 })}
                >
                  Take photos
                </button>
              </div>
            ) : (
              <div className="checkpoint__actions">
                <button type="button" className="button button--secondary checkpoint__action" onClick={onClose}>
                  Back to the walk
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
