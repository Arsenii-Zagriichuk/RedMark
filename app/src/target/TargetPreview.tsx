// The Target preview (P1-09): Curiosity's pictures for a science target. Curiosity never
// reached the off-track targets, so the pictures show the same kind of ground and say so.
import type { ScienceTarget } from "@contracts/site";
import { Panel } from "../ui/Panel";
import { picturesFor, targetPictures } from "./pictures";

export function TargetPreview({ target, onClose }: { target: ScienceTarget; onClose: () => void }) {
  const preview = picturesFor(targetPictures, target.id);
  return (
    <Panel title={target.name} label={<span className="data">Target preview</span>} onClose={onClose}>
      <p className="panel__note">{targetPictures.note}</p>
      <div className="target-preview">
        {preview.pictures.map((picture) => (
          <figure key={picture.image_id} className="target-preview__figure">
            <img src={picture.file} alt={picture.caption} />
            <figcaption>
              <span>{picture.caption}</span>
              <a className="data" href={picture.source_url} target="_blank" rel="noreferrer">
                Sol {picture.sol} · {picture.camera} · {picture.image_id} · {picture.credit}
              </a>
            </figcaption>
          </figure>
        ))}
      </div>
    </Panel>
  );
}
