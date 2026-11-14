"""The two matchers behind one contract: (ground view, map window) -> Matches.

LoFTR with the weights JPL fine-tuned on MARTIAN renders of HiRISE-scale maps
(https://huggingface.co/dpisanti/mbl-mars, V1/finetuned) is the matcher of
record; DISK features with LightGlue is the drop-in fallback. Both need the
`gpu` dependency group and run on CUDA, Apple's MPS or, failing both, the CPU.
"""

from pathlib import Path

import numpy as np

from locate.drone.fix import Matcher, Matches

# Under REDMARK_DATA: weights_loftr.zip from the Hugging Face repo, unzipped.
JPL_LOFTR_WEIGHTS = "weights/mbl-mars/loftr/V1/finetuned/2024_08_23-05_52_53.pt"
# Under REDMARK_DATA: where kornia downloads the DISK and LightGlue weights.
TORCH_HUB = "weights/torch-hub"
LIGHTGLUE_MAX_KEYPOINTS = 2048


def pick_device():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _tensor(image: np.ndarray, multiple: int, device):
    """uint8 image to a (1, 1, H, W) float tensor, padded at the bottom right to
    a multiple of `multiple` so pixel coordinates do not move."""
    import torch

    rows, cols = image.shape
    padded = np.zeros(
        (-(-rows // multiple) * multiple, -(-cols // multiple) * multiple), np.float32
    )
    padded[:rows, :cols] = image / 255.0
    return torch.from_numpy(padded)[None, None].to(device)


def loftr_matcher(weights: Path, device) -> Matcher:
    """LoFTR loaded with JPL's fine-tuned weights, using JPL's own settings
    (dual-softmax coarse matching, the original positional encoding)."""
    import torch
    from kornia.feature import LoFTR
    from kornia.feature.loftr.loftr import default_cfg

    model = LoFTR(pretrained=None, config=default_cfg)
    checkpoint = torch.load(weights, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["models"]["matcher"], strict=True)
    model = model.eval().to(device)

    def match(query: np.ndarray, reference: np.ndarray) -> Matches:
        with torch.inference_mode():
            out = model(
                {"image0": _tensor(query, 8, device), "image1": _tensor(reference, 8, device)}
            )
        return Matches(
            query_xy=out["keypoints0"].cpu().numpy().astype(np.float64),
            reference_xy=out["keypoints1"].cpu().numpy().astype(np.float64),
            confidence=out["confidence"].cpu().numpy().astype(np.float64),
        )

    return match


def lightglue_matcher(hub: Path, device) -> Matcher:
    """DISK keypoints matched with LightGlue, both with their published weights,
    downloaded once into `hub` so they sit with the rest of the data."""
    import torch
    from kornia.feature import DISK, LightGlueMatcher, laf_from_center_scale_ori

    torch.hub.set_dir(hub)
    disk = DISK.from_pretrained("depth").eval().to(device)
    glue = LightGlueMatcher("disk").eval().to(device)

    def features(image: np.ndarray):
        rgb = _tensor(image, 16, device).repeat(1, 3, 1, 1)
        found = disk(rgb, n=LIGHTGLUE_MAX_KEYPOINTS, pad_if_not_divisible=True)[0]
        return found.keypoints, found.descriptors, laf_from_center_scale_ori(found.keypoints[None])

    def match(query: np.ndarray, reference: np.ndarray) -> Matches:
        with torch.inference_mode():
            kq, dq, lq = features(query)
            kr, dr, lr = features(reference)
            scores, pairs = glue(dq, dr, lq, lr, hw1=query.shape, hw2=reference.shape)
        pairs = pairs.cpu().numpy()
        return Matches(
            query_xy=kq.cpu().numpy()[pairs[:, 0]].astype(np.float64),
            reference_xy=kr.cpu().numpy()[pairs[:, 1]].astype(np.float64),
            confidence=scores.cpu().numpy().ravel().astype(np.float64),
        )

    return match
