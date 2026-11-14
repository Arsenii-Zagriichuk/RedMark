"""Ingenuity Navcam frames in the PDS Helicam bundle: find, read and pick them."""

import re
from dataclasses import dataclass

HELICAM_DATA = "https://pds-imaging.jpl.nasa.gov/data/mars2020/mars2020_helicam/data"
# A Navcam full-frame product (FDR), e.g.
# urn:nasa:pds:mars2020_helicam:data:hnm_0152_0680432615_348fdr_n0100001heli03026_0000luj::5.0
_NAVCAM_FDR = re.compile(r":data:(hnm_(\d{4})_\d{10}_\d{3}fdr_\w+)::(\d+)\.\d+")


@dataclass(frozen=True)
class NavcamProduct:
    """One Navcam frame as listed in the bundle's inventory."""

    sol: int
    file_stem: str  # the .IMG and .xml share it

    @property
    def url_dir(self) -> str:
        return f"{HELICAM_DATA}/sol/{self.sol:05d}/ids/fdr/heli/"


@dataclass(frozen=True)
class NavcamFrame:
    """What a frame's label says about it."""

    file_stem: str
    flight: int
    altitude_m: float  # the drone's own estimate, height above take-off
    sclk: float  # spacecraft clock at the exposure, seconds
    lines: int
    samples: int


def navcam_products(inventory_lines: list[str], sol: int) -> list[NavcamProduct]:
    """The Navcam full frames of `sol` from collection_data_inventory.csv, in time order."""
    products = []
    for line in inventory_lines:
        match = _NAVCAM_FDR.search(line)
        if match and int(match[2]) == sol:
            stem = f"{match[1].upper()}{int(match[3]):02d}"
            products.append(NavcamProduct(sol=sol, file_stem=stem))
    return sorted(products, key=lambda p: p.file_stem)


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError(f"label has no match for {pattern!r}")
    return match[1]


def read_label(xml: str) -> NavcamFrame:
    """Parse a Navcam frame's PDS4 label.

    The drone's in-flight pose is the HELI_M_FRAME's offset from the
    flight's HELI_G_FRAME (take-off point, z down).
    """
    flight = int(_first(r"<local_identifier>HELI_G_FRAME_(\d+)</local_identifier>", xml))
    m_frame = _first(
        r"<local_identifier>HELI_M_FRAME_\d+_\d+</local_identifier>(.*?)"
        r"</geom:Coordinate_Space_Definition>",
        xml,
    )
    z = float(_first(r"<geom:Vector_Origin_Offset>.*?<geom:z_position[^>]*>([^<]+)<", m_frame))
    return NavcamFrame(
        file_stem=_first(r"<file_name>([^<]+)\.IMG</file_name>", xml),
        flight=flight,
        altitude_m=-z,
        sclk=float(_first(r"<msn:spacecraft_clock_start>([^<]+)<", xml)),
        lines=int(_first(r"<img:lines>(\d+)<", xml)),
        samples=int(_first(r"<img:samples>(\d+)<", xml)),
    )


def choose_frames(
    frames: list[NavcamFrame], count: int, min_altitude_ratio: float
) -> list[NavcamFrame]:
    """`count` frames spread evenly over the cruise part of a flight.

    Cruise frames are those at least `min_altitude_ratio` of the flight's
    highest frame; take-off and landing frames see too little ground.
    """
    if not frames:
        raise ValueError("no Navcam frames for this flight")
    ceiling = max(f.altitude_m for f in frames)
    cruise = sorted(
        (f for f in frames if f.altitude_m >= min_altitude_ratio * ceiling), key=lambda f: f.sclk
    )
    if len(cruise) <= count:
        return cruise
    if count == 1:
        return [cruise[len(cruise) // 2]]
    step = (len(cruise) - 1) / (count - 1)
    return [cruise[round(i * step)] for i in range(count)]
