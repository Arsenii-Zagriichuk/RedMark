"""Build the Jezero pack for Person 4 (P2-04).

    uv run python -m prep.jezero.build_pack

Writes, under $REDMARK_DATA/jezero/:
  source/                 NASA files as downloaded (map, flight paths, Navcam frames)
  pack/crops/flight-NN.tif   photo map around each flight, in the site frame
  pack/frames/*.png       each chosen Navcam frame as an 8-bit image
  pack/overlays/flight-NN.png  NASA's flight path drawn on the crop, to check by eye
  pack/frames.csv         the frame list: flight, sol, file names, height, clock
and, in the repo, sites/jezero.yaml and prep/data-manifest.yaml.

The photo map is read from the local copy when its download is complete, and
otherwise straight from USGS's S3 bucket (only the rows each crop needs).
"""

import csv
import hashlib
import math
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import rasterio
import truststore
import yaml
from PIL import Image, ImageDraw

from contracts.models.site import SiteConfig
from contracts.paths import REPO_ROOT, data_root
from prep.common import USER_AGENT, Bounds, download, manifest_entry, update_manifest
from prep.jezero.crop import RESOLUTION, crop_is_current, crop_to_site_frame
from prep.jezero.flights import flight_bounds, load_flights
from prep.jezero.frames import (
    HELICAM_DATA,
    NavcamFrame,
    NavcamProduct,
    choose_frames,
    navcam_products,
    read_label,
)
from prep.jezero.pack import (
    label_index,
    multipart_part_size,
    s3_multipart_etag,
    site_config,
    stretch_to_8bit,
)
from prep.jezero.site_frame import SITE_LAT_TS

MAP_NAME = "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first.tif"
MAP_URL = (
    f"https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/HiRISE/{MAP_NAME}"
)
MAP_PAGE = (
    "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/"
    "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first"
)
MAP_CREDIT = (
    "Mars 2020 TRN HiRISE orthomosaic of Jezero crater, 25 cm: "
    "USGS Astrogeology Science Center; HiRISE: NASA/JPL-Caltech/University of Arizona"
)
MMGIS = "https://mars.nasa.gov/mmgis-maps/M20/Layers/json"
NASA_JSON = {
    "m20_heli_flight_path.json": "Ingenuity flight paths (NASA Mars 2020 MMGIS)",
    "m20_heli_waypoints.json": "Ingenuity flight waypoints (NASA Mars 2020 MMGIS)",
}
INVENTORY = "collection_data_inventory.csv"
INVENTORY_URL = f"{HELICAM_DATA}/{INVENTORY}"
HELICAM_CREDIT = "Mars 2020 Helicopter Camera bundle, NASA PDS Imaging Node, NASA/JPL-Caltech"
OVERLAY_MAX_PX = 2000
# The ticket's floor: enough candidates that Person 4 can key 20 good frames.
MIN_CANDIDATE_FRAMES = 30


def _remote_size_and_etag(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return int(response.headers["Content-Length"]), response.headers["ETag"].strip('"')


def _map_source(local: Path, size: int, etag: str) -> str:
    """The local map if it is byte-for-byte USGS's current file, else the remote one."""
    if local.exists() and local.stat().st_size == size:
        if "-" in etag:  # multipart upload
            parts = int(etag.rpartition("-")[2])
            local_etag = s3_multipart_etag(local, multipart_part_size(size, parts))
        else:  # single upload: the ETag is the file's MD5
            local_etag = hashlib.md5(local.read_bytes()).hexdigest()
        if local_etag == etag:
            return str(local)
        print(f"warning: {local} does not match USGS's ETag {etag}; reading the remote map")
    return f"/vsicurl/{MAP_URL}"


def _round_out(bounds: Bounds) -> Bounds:
    """Bounds snapped outward to whole metres, so crops sit on the 25 cm grid."""
    min_x, min_y, max_x, max_y = bounds
    return (math.floor(min_x), math.floor(min_y), math.ceil(max_x), math.ceil(max_y))


def _frames_for_flight(
    flight: int, products: list[NavcamProduct], folder: Path
) -> list[NavcamFrame]:
    """Every Navcam frame of `flight`, read from its label (downloaded once)."""

    def fetch(product: NavcamProduct) -> NavcamFrame:
        name = f"{product.file_stem}.xml"
        return read_label(download(f"{product.url_dir}{name}", folder / name).read_text())

    with ThreadPoolExecutor(max_workers=8) as pool:
        frames = list(pool.map(fetch, products))
    return [f for f in frames if f.flight == flight]


def _write_frame_png(img_xml: Path, png: Path) -> None:
    with rasterio.open(img_xml) as src:
        raw = src.read(1)
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(stretch_to_8bit(raw)).save(png)


def _write_overlay(crop: Path, path_xy: list[tuple[float, float]], flight: int, out: Path) -> None:
    """NASA's flight path in red on the crop, with a 50 m scale bar."""
    with rasterio.open(crop) as src:
        scale = max(src.width, src.height) / OVERLAY_MAX_PX
        shape = (
            max(1, round(src.height / max(scale, 1))),
            max(1, round(src.width / max(scale, 1))),
        )
        image = src.read(1, out_shape=shape)
        transform = src.transform @ src.transform.scale(src.width / shape[1], src.height / shape[0])
    canvas = Image.fromarray(image).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    inverse = ~transform
    pixels = [inverse @ (x, y) for x, y in path_xy]
    draw.line(pixels, fill=(255, 40, 40), width=3)
    for (px, py), colour in ((pixels[0], (40, 255, 40)), (pixels[-1], (40, 160, 255))):
        draw.ellipse((px - 7, py - 7, px + 7, py + 7), outline=colour, width=3)
    metre = 1 / transform.a
    x0, y0 = 20, canvas.height - 30
    draw.rectangle((x0, y0, x0 + 50 * metre, y0 + 6), fill=(255, 255, 255))
    draw.text((x0, y0 - 16), "50 m", fill=(255, 255, 255))
    draw.text(
        (10, 10),
        f"Flight {flight}: NASA flight path (red; green take-off, blue landing) "
        f"on the HiRISE {RESOLUTION * 100:g} cm map, site frame eqc lat_ts={SITE_LAT_TS}",
        fill=(255, 255, 0),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def build(root: Path) -> None:
    config = yaml.safe_load((Path(__file__).parent / "pack.yaml").read_text())
    jezero = root / "jezero"
    source, pack = jezero / "source", jezero / "pack"

    for name in NASA_JSON:
        download(f"{MMGIS}/{name}", source / "nasa" / name)
    download(INVENTORY_URL, source / "helicam" / INVENTORY)
    inventory = (source / "helicam" / INVENTORY).read_text().splitlines()
    flights = load_flights(source / "nasa" / "m20_heli_flight_path.json")

    map_size, map_etag = _remote_size_and_etag(MAP_URL)
    map_source = _map_source(source / MAP_NAME, map_size, map_etag)
    map_id = f"{MAP_NAME} etag {map_etag}"
    print(f"photo map: {map_source}")

    rows, crops, manifest, labels_read = [], {}, [], []
    for spec in config["flights"]:
        flight, sol = spec["flight"], flights[spec["flight"]].sol
        products = navcam_products(inventory, sol)
        if not products:
            sys.exit(f"flight {flight}: the Helicam inventory has no Navcam frames for sol {sol}")
        url_dir = products[0].url_dir
        folder = source / "helicam" / f"sol-{sol:05d}"
        frames = _frames_for_flight(flight, products, folder)
        labels_read += [folder / f"{p.file_stem}.xml" for p in products]
        picked = choose_frames(frames, config["frames_per_flight"], config["min_altitude_ratio"])
        print(f"flight {flight} (sol {sol}): {len(frames)} frames, {len(picked)} picked")
        crop = pack / "crops" / f"flight-{flight:02d}.tif"
        for frame in picked:
            img = download(f"{url_dir}{frame.file_stem}.IMG", folder / f"{frame.file_stem}.IMG")
            png = pack / "frames" / f"{frame.file_stem}.png"
            _write_frame_png(folder / f"{frame.file_stem}.xml", png)
            for f in (img, folder / f"{frame.file_stem}.xml"):
                manifest.append(
                    manifest_entry(
                        root,
                        f.relative_to(root).as_posix(),
                        name=f"Ingenuity Navcam frame, flight {flight}",
                        source_url=f"{url_dir}{f.name}",
                        credit=HELICAM_CREDIT,
                    )
                )
            rows.append(
                {
                    "flight": flight,
                    "sol": sol,
                    "frame_png": png.name,
                    "product": f"{frame.file_stem}.IMG",
                    "crop": crop.name,
                    "altitude_m": round(frame.altitude_m, 3),
                    "sclk": frame.sclk,
                    "lines": frame.lines,
                    "samples": frame.samples,
                    "hard_mode": spec["hard_mode"],
                    "ground": spec["ground"],
                }
            )

        path = flights[flight].path
        bounds = _round_out(flight_bounds(path, config["margin_m"]))
        if not crop_is_current(crop, bounds, map_id):
            with rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_CHUNK_SIZE=4 << 20
            ):
                crop_to_site_frame(map_source, bounds, crop, map_id)
        _write_overlay(crop, path, flight, pack / "overlays" / f"flight-{flight:02d}.png")
        crops[flight] = bounds
        print(f"flight {flight}: crop {bounds}")

    if len(rows) < MIN_CANDIDATE_FRAMES:
        sys.exit(
            f"only {len(rows)} candidate frames; Person 4 needs at least "
            f"{MIN_CANDIDATE_FRAMES} to key 20 good ones. Add a flight to pack.yaml."
        )
    with (pack / "frames.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    files = {"frame_list": "jezero/pack/frames.csv"} | {
        f"crop_flight_{n:02d}": f"jezero/pack/crops/flight-{n:02d}.tif" for n in sorted(crops)
    }
    site = site_config(crops, files)
    SiteConfig.model_validate(site)
    header = (
        "# Written by prep/jezero/build_pack.py (P2-04). Do not edit by hand: change\n"
        "# prep/jezero/pack.yaml and rerun. Map metres are ground metres at Jezero.\n"
    )
    (REPO_ROOT / "sites" / "jezero.yaml").write_text(
        header + yaml.safe_dump(site, sort_keys=False, allow_unicode=True)
    )

    manifest.append(
        {
            "name": "Jezero HiRISE photo map, 25 cm",
            "path": f"jezero/source/{MAP_NAME}",
            "size_bytes": map_size,
            "source_url": MAP_PAGE,
            "checksum": map_etag,
            "checksum_algorithm": "md5-s3-multipart",
            "credit": MAP_CREDIT,
        }
    )
    for name, title in NASA_JSON.items():
        manifest.append(
            manifest_entry(
                root,
                f"jezero/source/nasa/{name}",
                name=title,
                source_url=f"{MMGIS}/{name}",
                credit="NASA/JPL-Caltech",
            )
        )
    manifest.append(
        manifest_entry(
            root,
            f"jezero/source/helicam/{INVENTORY}",
            name="Helicam bundle inventory",
            source_url=INVENTORY_URL,
            credit=HELICAM_CREDIT,
        )
    )
    # Every label the frame choice read, checksummed in one index file, so the
    # References stay short but each label's bytes are on record.
    index = source / "helicam" / "labels-index.csv"
    with index.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "size_bytes", "sha256"])
        writer.writeheader()
        writer.writerows(label_index(root, labels_read))
    manifest.append(
        manifest_entry(
            root,
            index.relative_to(root).as_posix(),
            name=f"Index of the {len(labels_read)} Navcam labels read to choose frames "
            "(path, size, SHA-256; each label is in the Helicam bundle under sol/)",
            source_url=f"{HELICAM_DATA}/sol/",
            credit=HELICAM_CREDIT,
        )
    )
    update_manifest(manifest, owned=("jezero/",))
    print(f"pack: {len(rows)} frames from {len(crops)} flights in {pack}")


if __name__ == "__main__":
    if not os.environ.get("REDMARK_DATA"):
        sys.exit("set REDMARK_DATA to the shared data folder; the pack never goes in the stub data")
    # Verify HTTPS with the system's certificates: Python's own bundle rejects
    # the PDS Imaging Node's chain.
    truststore.inject_into_ssl()
    build(data_root())
