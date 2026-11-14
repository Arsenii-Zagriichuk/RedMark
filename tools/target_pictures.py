"""The Target preview's Curiosity pictures (P1-09).

    uv run python -m tools.target_pictures

Downloads the Curiosity raw images picked below from NASA's raw-image archive into
app/public/targets/ and writes:
- app/src/target/curiosity-pictures.json, the list the app shows: each science target's pictures
  with sol, camera, caption, credit, source and sha256, and the fallback picture;
- app/data-manifest.yaml, the same files for the project page's References.

Curiosity never reached the off-track science targets in sites/gale.yaml, so no picture
shows a target itself. Each shows the same kind of ground (a raised boxwork ridge, or a
sand-floored hollow between ridges) in the boxwork Curiosity drove through near the
replayed sol, picked by eye, and its caption says so.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

from contracts.paths import REPO_ROOT

PUBLIC = REPO_ROOT / "app" / "public"
PICTURES = REPO_ROOT / "app" / "src" / "target" / "curiosity-pictures.json"
MANIFEST = REPO_ROOT / "app" / "data-manifest.yaml"
RAW = "https://mars.nasa.gov/msl-raw-images"
CAMERAS = {
    "MAST_LEFT": ("Mastcam left", "NASA/JPL-Caltech/MSSS"),
    "NAV_LEFT_B": ("Navcam left", "NASA/JPL-Caltech"),
}

# (science target id, image id, sol, camera, url, caption)
PICKS = [
    (
        "sw-ridge",
        "4600ML1079530021803220C00_DXXX",
        4600,
        "MAST_LEFT",
        f"{RAW}/msss/04600/mcam/4600ML1079530021803220C00_DXXX.jpg",
        "Raised ridges of harder rock standing above sand, like this target's ridge.",
    ),
    (
        "sw-ridge",
        "4600ML1079530181803236C00_DXXX",
        4600,
        "MAST_LEFT",
        f"{RAW}/msss/04600/mcam/4600ML1079530181803236C00_DXXX.jpg",
        "Close-up of ridge slabs: the rock a ridge sample would come from.",
    ),
    (
        "sw-hollow",
        "NLB_806305401EDR_F1172538NCAM00263M_",
        4605,
        "NAV_LEFT_B",
        f"{RAW}/proj/msl/redops/ods/surface/sol/04605/opgs/edr/ncam/"
        "NLB_806305401EDR_F1172538NCAM00263M_.JPG",
        "A sand-floored hollow under a raised rim, like this target's cell floor.",
    ),
    (
        "sw-hollow",
        "4595ML1079180031803048C00_DXXX",
        4595,
        "MAST_LEFT",
        f"{RAW}/msss/04595/mcam/4595ML1079180031803048C00_DXXX.jpg",
        "Rippled sand between blocks: the loose floor a hollow sample would come from.",
    ),
]
# Shown for a target with no pictures, or when a picture fails to load: a copy of one
# pick's file (Curiosity's wide view of the boxwork), with that pick's source and credit.
FALLBACK_PICK = "NLB_806305401EDR_F1172538NCAM00263M_"
FALLBACK_CAPTION = "Curiosity's view of the boxwork it drove through."
NOTE = (
    "Curiosity never reached this target. These are its pictures of the same kind of "
    "ground in the boxwork it drove through."
)


def _download(url: str, path: Path) -> bytes:
    if not path.is_file():
        request = urllib.request.Request(url, headers={"User-Agent": "redmark-client"})
        with urllib.request.urlopen(request, timeout=60) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


def _picture(image_id: str, sol: int, camera: str, url: str, caption: str, file: str) -> dict:
    data = _download(url, PUBLIC / file.lstrip("/"))
    name, credit = CAMERAS[camera]
    return {
        "image_id": image_id,
        "sol": sol,
        "camera": name,
        "caption": caption,
        "credit": credit,
        "source_url": url,
        "file": file,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _fallback(pick: dict) -> dict:
    """The fallback picture: the pick's own file copied, so the bytes are the same."""
    file = "/fallback/target-preview.jpg"
    shutil.copyfile(PUBLIC / pick["file"].lstrip("/"), PUBLIC / file.lstrip("/"))
    fallback = {key: value for key, value in pick.items() if key != "target"}
    return {**fallback, "caption": FALLBACK_CAPTION, "file": file}


def _commit() -> str:
    """HEAD, after checking it holds this script as it runs, so provenance names the picks."""
    script = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()

    if git("status", "--porcelain", "--", script):
        sys.exit(f"commit {script} first: provenance must name a commit with these picks")
    return git("rev-parse", "HEAD")


def main() -> int:
    commit = _commit()
    site = yaml.safe_load((REPO_ROOT / "sites" / "gale.yaml").read_text(encoding="utf-8"))
    targets = {target["id"] for target in site["science_targets"]}
    unknown = {pick[0] for pick in PICKS} - targets
    unpictured = targets - {pick[0] for pick in PICKS}
    if unknown or unpictured:
        sys.exit(f"picks name unknown targets {unknown} or miss targets {unpictured}")

    (PUBLIC / "targets").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "fallback").mkdir(parents=True, exist_ok=True)
    pictures = [
        {"target": target, **_picture(*rest, file=f"/targets/{rest[0]}.jpg")}
        for target, *rest in PICKS
    ]
    fallback = _fallback(next(p for p in pictures if p["image_id"] == FALLBACK_PICK))
    PICTURES.parent.mkdir(parents=True, exist_ok=True)
    PICTURES.write_text(
        json.dumps(
            {
                "provenance": {"script": "tools/target_pictures.py", "commit": commit},
                "note": NOTE,
                "pictures": pictures,
                "fallback": fallback,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    files = [
        {
            "name": f"Curiosity {picture['camera']}, sol {picture['sol']}, {picture['image_id']}",
            "path": f"app/public{picture['file']}",
            "size_bytes": picture["size_bytes"],
            "source_url": picture["source_url"],
            "checksum": picture["sha256"],
            "checksum_algorithm": "sha256",
            "credit": f"{picture['credit']}; NASA Mars raw images",
        }
        for picture in [*pictures, fallback]
    ]
    header = (
        "# Curiosity raw images for the Target preview (P1-09), downloaded unmodified by\n"
        "# tools/target_pictures.py. Paths are relative to the repo root.\n"
    )
    MANIFEST.write_text(header + yaml.safe_dump({"files": files}, sort_keys=False), "utf-8")
    for written in (PICTURES, MANIFEST):
        print(f"wrote {written.relative_to(REPO_ROOT)}")
    print(f"{len(pictures)} pictures for {len(targets)} science targets, and the fallback")
    return 0


if __name__ == "__main__":
    sys.exit(main())
