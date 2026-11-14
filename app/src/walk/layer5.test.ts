import { describe, expect, it } from "vitest";
import { landmarkDirectionsFor } from "./layer5";

// Person 3's real layer 5 file: this fails if its landmark directions change shape.
describe("landmarkDirectionsFor", () => {
  it("reads Gale's landmarks in landmarks.yaml's order, named as layers/location_quality/landmarks.yaml says", () => {
    const directions = landmarkDirectionsFor("gale");

    expect(directions?.landmarks.map(({ id, in_sentence }) => [id, in_sentence])).toEqual([
      ["mount_sharp_peak", "the upper Mount Sharp peak"],
      ["texoli", "Texoli"],
      ["mishe_mokwa", "Mishe Mokwa"],
      ["crater_rim", "the Gale crater rim"],
    ]);
  });

  it("gives every leg what it sees of each landmark, along a saved route in the demo cache", () => {
    const directions = landmarkDirectionsFor("gale")!;

    expect(directions.path.length).toBeGreaterThan(1);
    expect(directions.legs.length).toBeGreaterThan(0);
    for (const leg of directions.legs) {
      expect(leg.landmarks.map((seen) => seen.id)).toEqual(directions.landmarks.map((landmark) => landmark.id));
      expect(leg.landmarks.every((seen) => seen.share_of_leg_in_view >= 0 && seen.share_of_leg_in_view <= 1)).toBe(true);
    }
  });

  it("has nothing for a site layer 5 doesn't cover", () => {
    expect(landmarkDirectionsFor("jezero")).toBeNull();
  });
});
