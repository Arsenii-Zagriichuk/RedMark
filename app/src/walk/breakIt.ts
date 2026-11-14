// The badges a break-it scenario puts on the Walk view, from the backup table in the
// project document ("Backup and safety design"): "Camera off" when the helmet camera is
// lost, "Offline mode" when the radio link to the habitat is down, and "Lost mode" when no
// source can be trusted. A grounded drone gets no badge: its fixes are greyed out.
import type { SimulateResponse } from "@contracts/simulate_response";

export interface Badge {
  id: "camera-off" | "offline" | "lost";
  label: string;
}

export function walkBadges(simulation: SimulateResponse, index: number): Badge[] {
  const step = simulation.steps[index]!;
  const cameraOff = simulation.steps
    .slice(0, index + 1)
    .some((earlier) => earlier.events.some((event) => event.kind === "camera_off"));
  const badges: Badge[] = [];
  if (cameraOff) badges.push({ id: "camera-off", label: "Camera off" });
  // Lost mode comes with the radio down too (everything at once), so it is offline as well.
  if (step.mode !== "normal") badges.push({ id: "offline", label: "Offline mode" });
  if (step.mode === "lost") badges.push({ id: "lost", label: "Lost mode" });
  return badges;
}
