"""From a straightened drone photo and a window of the photo map to a fix.

The photo, straightened to a north-up view of the ground at the map's scale,
is matched to the map window by a matcher (LoFTR or LightGlue). A similarity
(shift, turn and scale) fitted to the matches with RANSAC carries the photo's
nadir onto the map, which is the fix's position, and turns the onboard
heading by the fitted angle, which is its heading. The scale absorbs the
error in the drone's height over the ground.

Pixel convention, shared with the matchers: pixel centres sit at whole
numbers, x to the right (east) and y down (south).
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from contracts.models.common import Method, Point, Provenance, SiteId, TerrainType
from contracts.models.fix_result import FixResult

# The uncertainty circle and confidence can only be measured on the answer key
# (P2-06). Until then every drone fix carries these: the project's 5–10 m
# drone target as the circle, and no claimed confidence.
UNCALIBRATED_UNCERTAINTY_M = 10.0
UNCALIBRATED_CONFIDENCE_PCT = 0.0

# Matches this close to the photo's edge are dropped: the edge against the
# black outside is a strong false feature.
EDGE_PX = 2

# RANSAC: a match agrees with a fit if it lands within this many pixels
# (0.5 m at 25 cm). Fewer agreeing matches than MIN_INLIERS is no fix.
INLIER_PX = 2.0
MIN_INLIERS = 15
RANSAC_ROUNDS = 10_000  # sparse LoFTR inliers among overlapping tile candidates
KEYPOINT_PX = 1.0  # repeated detections of one feature can differ by subpixel amounts
# The view is drawn at the map's scale, so a true fit scales it by about 1:
# the drone's height and the ground's relief are off by a few percent, not by
# a quarter. Fits outside these bounds (such as many points onto one) are refused.
MIN_SCALE, MAX_SCALE = 0.8, 1.25


@dataclass(frozen=True)
class GroundView:
    """A drone photo straightened onto the ground, north up."""

    image: np.ndarray  # uint8, rows x cols
    valid: np.ndarray  # bool, where the photo saw the ground
    resolution: float  # metres per pixel
    nadir_px: np.ndarray  # (x, y) of the point under the camera
    heading_deg: float  # the onboard heading the view was drawn with
    outline_px: np.ndarray = field(default_factory=lambda: np.empty((0, 2)))  # photo's edge


@dataclass(frozen=True)
class MapWindow:
    image: np.ndarray  # uint8, rows x cols, north up
    min_x: float  # west edge, map metres
    max_y: float  # north edge, map metres
    resolution: float

    def to_map(self, px: np.ndarray) -> np.ndarray:
        """Window pixels (x, y) to map metres (x, y)."""
        px = np.atleast_2d(px)
        return np.column_stack(
            [
                self.min_x + (px[:, 0] + 0.5) * self.resolution,
                self.max_y - (px[:, 1] + 0.5) * self.resolution,
            ]
        )

    def to_px(self, xy: np.ndarray) -> np.ndarray:
        """Map metres (x, y) to window pixels (x, y)."""
        xy = np.atleast_2d(xy)
        return np.column_stack(
            [
                (xy[:, 0] - self.min_x) / self.resolution - 0.5,
                (self.max_y - xy[:, 1]) / self.resolution - 0.5,
            ]
        )


@dataclass(frozen=True)
class Matches:
    query_xy: np.ndarray  # N x 2, pixels in the ground view
    reference_xy: np.ndarray  # N x 2, pixels in the map window


# A matcher takes the ground view's and the map window's images and returns
# matches in those images' own pixels.
Matcher = Callable[[np.ndarray, np.ndarray], Matches]


@dataclass(frozen=True)
class DroneFix:
    position: tuple[float, float]  # map metres
    heading_deg: float
    matches: int
    inliers: int
    scale: float  # map pixels per ground-view pixel
    rotation_deg: float  # turn from the onboard heading, clockwise
    outline_xy: np.ndarray  # the photo's edge on the map, map metres
    inlier_xy: np.ndarray  # agreeing matches on the map, map metres
    to_window: tuple[complex, complex]  # (a, b): window pixel = a * view pixel + b, complex


def locate_on_map(ground: GroundView, window: MapWindow, matcher: Matcher) -> DroneFix:
    if not np.isclose(ground.resolution, window.resolution):
        raise ValueError("the ground view and the map window must share one scale")
    found = _match_in_tiles(ground, window, matcher)
    keep = _inside(ground.valid, found.query_xy)
    matches = Matches(found.query_xy[keep], found.reference_xy[keep])
    a, b, inliers = _fit_similarity(matches.query_xy, matches.reference_xy)
    if not MIN_SCALE <= abs(a) <= MAX_SCALE or inliers.sum() < MIN_INLIERS:
        raise ValueError(
            f"no fix: {inliers.sum()} of {len(inliers)} matches agree ({MIN_INLIERS} needed)"
            f" at scale {abs(a):.2f} ({MIN_SCALE} to {MAX_SCALE} allowed)"
        )

    def carry(px: np.ndarray) -> np.ndarray:
        z = a * _complex(px) + b
        return np.column_stack([z.real, z.imag])

    rotation = np.degrees(np.angle(a))
    heading = float((ground.heading_deg + rotation) % 360.0)
    return DroneFix(
        position=tuple(float(v) for v in window.to_map(carry(ground.nadir_px))[0]),
        # A hair below zero wraps to exactly 360.0 in floating point.
        heading_deg=0.0 if heading >= 360.0 else heading,
        matches=len(inliers),
        inliers=int(inliers.sum()),
        scale=float(abs(a)),
        rotation_deg=float(rotation),
        outline_xy=(
            window.to_map(carry(ground.outline_px)) if len(ground.outline_px) else np.empty((0, 2))
        ),
        inlier_xy=window.to_map(matches.reference_xy[inliers]),
        to_window=(a, b),
    )


def _tile_starts(length: int, tile: int) -> list[int]:
    """Tile starts every quarter tile, with the last tile flush with the far edge."""
    if length <= tile:
        return [0]
    starts = list(range(0, length - tile + 1, max(1, tile // 4)))
    return starts if starts[-1] == length - tile else [*starts, length - tile]


def _match_in_tiles(ground: GroundView, window: MapWindow, matcher: Matcher) -> Matches:
    """Match the ground view against overlapping tiles of the window, each the
    view's size, as JPL's pipeline does: the matchers were trained on pairs of
    similar extent, and a far larger window drowns the right matches.

    Keep alternative map matches until the fit can choose between them.
    """
    rows, cols = ground.image.shape
    found = []
    for top in _tile_starts(window.image.shape[0], rows):
        for left in _tile_starts(window.image.shape[1], cols):
            tile = matcher(ground.image, window.image[top : top + rows, left : left + cols])
            found.append(np.column_stack([tile.query_xy, tile.reference_xy + [left, top]]))
    stacked = np.vstack(found) if found else np.empty((0, 4))
    _, first = np.unique(np.round(stacked * 2), axis=0, return_index=True)
    stacked = stacked[np.sort(first)]
    return Matches(query_xy=stacked[:, :2], reference_xy=stacked[:, 2:])


def _inside(valid: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """Which points fall on pixels at least EDGE_PX inside the valid area."""
    core = valid.copy()
    for _ in range(EDGE_PX):
        core[1:, :] &= core[:-1, :].copy()
        core[:-1, :] &= core[1:, :].copy()
        core[:, 1:] &= core[:, :-1].copy()
        core[:, :-1] &= core[:, 1:].copy()
    cols, rows = np.round(xy).astype(int).T
    on_image = (cols >= 0) & (cols < valid.shape[1]) & (rows >= 0) & (rows < valid.shape[0])
    result = np.zeros(len(xy), dtype=bool)
    result[on_image] = core[rows[on_image], cols[on_image]]
    return result


def _complex(px: np.ndarray) -> np.ndarray:
    px = np.atleast_2d(px)
    return px[:, 0] + 1j * px[:, 1]


def _fit_similarity(
    query: np.ndarray, reference: np.ndarray
) -> tuple[complex, complex, np.ndarray]:
    """reference ≈ a * query + b in complex pixels, by RANSAC then least squares.

    A complex a is a turn and a scale with no mirroring, so the fit cannot
    flip the photo. Candidates scaled outside MIN_SCALE to MAX_SCALE are
    skipped. A keypoint in either image can support the final fit only once.
    """
    q, r = _complex(query), _complex(reference)
    best = np.zeros(len(q), dtype=bool)
    if len(q) >= 2:
        # Alternatives are retained across tiles, but each feature can vote
        # only once. The radius test also works across pixel-bin boundaries.
        def consensus(a: complex, b: complex) -> np.ndarray:
            residuals = np.abs(a * q + b - r)
            candidates = np.flatnonzero(residuals < INLIER_PX)
            order = candidates[np.argsort(residuals[candidates], kind="stable")]
            selected = np.zeros(len(q), dtype=bool)
            while len(order):
                index = order[0]
                selected[index] = True
                order = order[
                    (np.abs(q[order] - q[index]) > KEYPOINT_PX)
                    & (np.abs(r[order] - r[index]) > KEYPOINT_PX)
                ]
            return selected

        rng = np.random.default_rng(0)  # the same matches always give the same fix
        best_count = 0
        for _ in range(RANSAC_ROUNDS):
            i, j = rng.choice(len(q), size=2, replace=False)
            if abs(q[j] - q[i]) <= KEYPOINT_PX:
                continue
            a = (r[j] - r[i]) / (q[j] - q[i])
            if not MIN_SCALE <= abs(a) <= MAX_SCALE:
                continue
            b = r[i] - a * q[i]
            if np.count_nonzero(np.abs(a * q + b - r) < INLIER_PX) <= best_count:
                continue
            agree = consensus(a, b)
            count = np.count_nonzero(agree)
            if count > best_count:
                best, best_count = agree, count
        if best_count >= 2:
            qc, rc = q[best] - q[best].mean(), r[best] - r[best].mean()
            a = (rc * qc.conj()).sum() / (np.abs(qc) ** 2).sum()
            b = r[best].mean() - a * q[best].mean()
            return complex(a), complex(b), consensus(a, b)
    return 1 + 0j, 0j, best


def build_fix_result(
    *,
    photo_id: str,
    estimate: DroneFix,
    time_per_fix_s: float,
    terrain_type: TerrainType,
    overlay: str,
    provenance: Provenance,
) -> FixResult:
    """A real (not simulated) drone fix at Jezero, not yet scored."""
    x, y = estimate.position
    return FixResult(
        photo_id=photo_id,
        site=SiteId.jezero,
        method=Method.drone,
        position=Point(x=x, y=y),
        heading_deg=estimate.heading_deg,
        uncertainty_m=UNCALIBRATED_UNCERTAINTY_M,
        confidence_pct=UNCALIBRATED_CONFIDENCE_PCT,
        time_per_fix_s=time_per_fix_s,
        terrain_type=terrain_type,
        simulated=False,
        overlay=overlay,
        truth=None,
        provenance=provenance,
    )
