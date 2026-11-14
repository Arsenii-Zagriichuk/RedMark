// The Target preview's Curiosity pictures (P1-09), as tools/target_pictures.py writes them
// to curiosity-pictures.json. The images sit in app/public/, so they load with the network off.
import pictureList from "./curiosity-pictures.json";

export interface TargetPicture {
  image_id: string;
  sol: number;
  camera: string;
  caption: string;
  credit: string;
  source_url: string;
  /** Path under app/public/. */
  file: string;
  sha256: string;
  size_bytes: number;
}

export interface PictureList {
  provenance: { script: string; commit: string };
  /** Why the pictures don't show the target itself. */
  note: string;
  pictures: (TargetPicture & { target: string })[];
  fallback: TargetPicture;
}

export const targetPictures: PictureList = pictureList;

/** A target's own pictures, in the list's order, or the static fallback if it has none. */
export function picturesFor(list: PictureList, targetId: string): TargetPicture[] {
  const own = list.pictures.filter((picture) => picture.target === targetId);
  return own.length > 0 ? own : [list.fallback];
}
