// The Target preview (P1-09): Curiosity's pictures for a science target. Curiosity never
// reached the off-track targets, so the pictures show the same kind of ground and say so.
// A picture that fails to load is replaced, caption and all, by the static fallback.
import type { ScienceTarget } from "@contracts/site";
import { useState } from "react";
import { Panel } from "../ui/Panel";
import { picturesFor, targetPictures, type TargetPicture } from "./pictures";

function Figure({ picture }: { picture: TargetPicture }) {
  const [failed, setFailed] = useState(false);
  const shown = failed ? targetPictures.fallback : picture;
  return (
    <figure className="target-preview__figure">
      <img src={shown.file} alt={shown.caption} onError={() => setFailed(true)} />
      <figcaption>
        <span>{shown.caption}</span>
        <a className="data" href={shown.source_url} target="_blank" rel="noreferrer">
          Sol {shown.sol} · {shown.camera} · {shown.image_id} · {shown.credit}
        </a>
      </figcaption>
    </figure>
  );
}

export function TargetPreview({ target, onClose }: { target: ScienceTarget; onClose: () => void }) {
  return (
    <Panel title={target.name} label={<span className="data">Target preview</span>} onClose={onClose}>
      <p className="panel__note">{targetPictures.note}</p>
      <div className="target-preview">
        {picturesFor(targetPictures, target.id).map((picture) => (
          <Figure key={picture.image_id} picture={picture} />
        ))}
      </div>
    </Panel>
  );
}
