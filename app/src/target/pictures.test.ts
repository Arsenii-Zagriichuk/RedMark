import { describe, expect, it } from "vitest";
import { picturesFor, type PictureList, type TargetPicture } from "./pictures";

function picture(target: string, image_id: string): TargetPicture & { target: string } {
  return {
    target,
    image_id,
    sol: 4600,
    camera: "Mastcam left",
    caption: `${image_id} caption`,
    credit: "NASA/JPL-Caltech/MSSS",
    source_url: `https://mars.nasa.gov/msl-raw-images/${image_id}.jpg`,
    file: `/targets/${image_id}.jpg`,
    sha256: "0".repeat(64),
    size_bytes: 1,
  };
}

const list: PictureList = {
  provenance: { script: "tools/target_pictures.py", commit: "abc" },
  note: "Curiosity never reached this target.",
  pictures: [picture("sw-ridge", "ridge-1"), picture("sw-hollow", "hollow-1"), picture("sw-ridge", "ridge-2")],
  fallback: { ...picture("", "wide"), file: "/fallback/target-preview.jpg" },
};

describe("picturesFor", () => {
  it("gives a target its own pictures, in the list's order", () => {
    const preview = picturesFor(list, "sw-ridge");

    expect(preview.pictures.map((p) => p.image_id)).toEqual(["ridge-1", "ridge-2"]);
    expect(preview.isFallback).toBe(false);
  });

  it("gives a target with no pictures the static fallback picture", () => {
    const preview = picturesFor(list, "nowhere");

    expect(preview.pictures.map((p) => p.file)).toEqual(["/fallback/target-preview.jpg"]);
    expect(preview.isFallback).toBe(true);
  });
});
