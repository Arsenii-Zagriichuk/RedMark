// The conditions strip during the walk, read from the replayed sol's conditions file. The
// walk starts at first light, as the route engine's daylight check does, and the local time
// moves on in Mars hours of 88775.244 s / 24 (route/README.md).
import type { Conditions } from "@contracts/conditions";

const MARS_HOUR_S = 88775.244 / 24;

export interface ConditionsNow {
  lmst: string;
  temperature: string;
  radiation: string;
  dust: string;
  dustSource: Conditions["dust"]["source"];
  sunsetIn: string;
}

const toMinutes = (lmst: string) => {
  const [hours = 0, minutes = 0] = lmst.split(":").map(Number);
  return hours * 60 + minutes;
};

const toLmst = (minutes: number) =>
  `${String(Math.floor(minutes / 60) % 24).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

function hoursAndMinutes(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest} min`;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

export function conditionsAt(conditions: Conditions, walk_s: number): ConditionsNow {
  const firstLight = conditions.steps.find((step) => step.sun_elevation_deg > 0) ?? conditions.steps[0];
  const now = toMinutes(firstLight?.lmst ?? "00:00") + Math.round((walk_s / MARS_HOUR_S) * 60);
  // The hourly step this local time falls in.
  const hour = [...conditions.steps].reverse().find((step) => toMinutes(step.lmst) <= now) ?? firstLight;
  const untilSunset = toMinutes(conditions.sunset_lmst) - now;
  return {
    lmst: toLmst(now),
    temperature: hour ? `${Math.round(hour.temperature_c)} °C` : "",
    radiation: `${Math.round(conditions.radiation_ugy_per_day)} µGy/day`,
    dust: `τ ${conditions.dust.optical_depth}`,
    dustSource: conditions.dust.source,
    sunsetIn: untilSunset > 0 ? hoursAndMinutes(untilSunset) : "after sunset",
  };
}
