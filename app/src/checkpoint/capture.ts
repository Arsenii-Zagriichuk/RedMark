// The guided capture at a Photo checkpoint (P1-08): the full-circle routine the app walks the
// crew through, one photo per prompt, with a progress ring. The skyline round starts facing
// the skyline for the horizon fix and turns a quarter at a time; when confidence is low, the
// round of photos facing other directions starts half a quarter round, so its four photos
// face between the first four.
export type Round = "skyline" | "other-directions";

export interface CaptureStep {
  /** What to do before the next photo, or null once the round is done. */
  prompt: string | null;
  /** How full the progress ring is, from 0 to 1. */
  progress: number;
}

const QUARTER = "Turn left 90°";
const ROUNDS: Record<Round, { name: string; prompts: string[] }> = {
  skyline: { name: "Horizon fix · the skyline", prompts: ["Face the skyline", QUARTER, QUARTER, QUARTER] },
  "other-directions": {
    name: "Ground fix · photos facing other directions",
    prompts: ["Turn left 45°", QUARTER, QUARTER, QUARTER],
  },
};

/** What the round's photos are for, as the capture screen titles it. */
export const roundName = (round: Round) => ROUNDS[round].name;

export function captureStep(round: Round, captured: number): CaptureStep {
  const { prompts } = ROUNDS[round];
  return { prompt: prompts[captured] ?? null, progress: captured / prompts.length };
}
