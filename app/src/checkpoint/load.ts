// What the Photo checkpoint loads (P1-08), by demo step: the real horizon fix Person 3 cached
// for the checkpoint (P3-04's pick in locate/horizon/demo_fixes.py: ridge top or open ground,
// the smallest circle that holds the true position), and stage 2's results file (P3-08),
// whose own simulated flag labels the ground fix.
import type { FixResult } from "@contracts/fix_result";
import type { TestSummary } from "@contracts/test_summary";
import type { ApiClient } from "../api/client";

const CHECKPOINT_PHOTO = "NLB_784293406ILT_S1110348NCAM00281M1";
const STAGE_2_TEST = "ground-gale";

export interface Checkpoint {
  fix: FixResult;
  stage2: TestSummary;
}

export async function loadCheckpoint(client: ApiClient): Promise<Checkpoint> {
  const [fix, stage2] = await Promise.all([
    client.fix("checkpoint.fix.horizon", "horizon", CHECKPOINT_PHOTO),
    client.summary("checkpoint.summary.ground", "ground", STAGE_2_TEST),
  ]);
  return { fix, stage2 };
}
