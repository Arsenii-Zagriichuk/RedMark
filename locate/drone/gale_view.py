"""The simulated Gale drone photo (P2-07): a top-down view cut from the Gale
photo map, with the crew's suit markers drawn in.

There are no drone photos of Gale, so the drone's photo is cut from the same
25 cm map it is then matched to. It shows the pipeline working, not how
accurate it is: everything made from it is labelled simulated, and no
accuracy numbers come from it.

The photo is drawn at PHOTO_RESOLUTION, about as sharp as Ingenuity's Navcam
from 10 m up, so the suit markers are their real size. The ground in it is the
25 cm map resampled, so it is no sharper than the map. Like a real drone
photo, its up direction is the drone's heading. `DronePhoto.straighten` then
does what `ground.straighten` does for a Navcam frame: draws it north up at
the map's scale, turned by the drone's onboard heading.

Camera frame: metres right of and forward of the nadir, forward being the
drone's heading. Photo pixel centres sit at whole numbers, x to the right and
y down (backwards).
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

from locate.drone.fix import DroneFix, GroundView, MapWindow
from locate.drone.ground import HALF_SIZE_M, footprint_outline, read_map_window
from prep.jezero.pack import stretch_to_8bit

# Ingenuity's Navcam saw about 3.6 cm of ground per pixel from 10 m up; 5 cm
# keeps the photo a whole 5 times sharper than the 25 cm map.
PHOTO_RESOLUTION = 0.05

# Suit markers (project document, Hardware): one on the helmet, one on the
# backpack, in colours the grey Mars ground never has. Seen from above, the
# helmet marker sits ahead of the astronaut's centre and the backpack marker
# behind it, so the pair gives the way the astronaut faces.
HELMET_RGB = (255, 140, 0)
BACKPACK_RGB = (0, 230, 120)
HELMET_RADIUS_M = 0.12
BACKPACK_RADIUS_M = 0.15
MARKER_OFFSET_M = 0.15  # each marker's distance from the astronaut's centre
# A pixel is a marker if its colour spread (brightest minus dimmest channel)
# is at least this; the ground's is 0.
MARKER_CHROMA = 100


@dataclass(frozen=True)
class Astronaut:
    position: tuple[float, float]  # map metres
    heading_deg: float  # the way the astronaut faces, from map north


def _turn(east: np.ndarray, north: np.ndarray, heading_deg: float):
    """Map east and north offsets to the camera's right and forward."""
    h = np.radians(heading_deg)
    return east * np.cos(h) - north * np.sin(h), east * np.sin(h) + north * np.cos(h)


def _unturn(right: np.ndarray, forward: np.ndarray, heading_deg: float):
    """The camera's right and forward to map east and north offsets."""
    h = np.radians(heading_deg)
    return right * np.cos(h) + forward * np.sin(h), -right * np.sin(h) + forward * np.cos(h)


@dataclass(frozen=True)
class DronePhoto:
    """A top-down photo, its up direction the drone's heading."""

    image: np.ndarray  # uint8, rows x cols x RGB
    resolution: float  # metres per pixel
    half_size_m: float  # the photo reaches this far right, left, forward and back

    def _to_camera(self, px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        px = np.atleast_2d(px)
        return (
            (px[:, 0] + 0.5) * self.resolution - self.half_size_m,
            self.half_size_m - (px[:, 1] + 0.5) * self.resolution,
        )

    def _from_camera(self, right: np.ndarray, forward: np.ndarray) -> np.ndarray:
        return np.column_stack(
            [
                (right + self.half_size_m) / self.resolution - 0.5,
                (self.half_size_m - forward) / self.resolution - 0.5,
            ]
        )

    def straighten(self, onboard_heading_deg: float, resolution: float) -> GroundView:
        """The photo north up at `resolution`, turned by the drone's onboard heading.

        Each output pixel averages the photo pixels it covers, so shrinking
        the photo to the map's scale does not alias.
        """
        supersample = round(resolution / self.resolution)
        size = round(2 * self.half_size_m / resolution)
        fine = resolution / supersample
        offsets = (np.arange(size * supersample) + 0.5) * fine - self.half_size_m
        east, north = np.meshgrid(offsets, -offsets)
        right, forward = _turn(east.ravel(), north.ravel(), onboard_heading_deg)
        px = self._from_camera(right, forward)
        gray = self.image.astype(np.float64).mean(axis=2)
        last = np.array(gray.shape[::-1]) - 1
        seen = np.all((px >= 0) & (px <= last), axis=1)
        values = np.full(len(px), np.nan)
        values[seen] = ndimage.map_coordinates(gray, [px[seen, 1], px[seen, 0]], order=1)
        mean = values.reshape(size, supersample, size, supersample).mean(axis=(1, 3))
        valid = np.isfinite(mean)
        image = np.zeros((size, size), dtype=np.uint8)
        image[valid] = stretch_to_8bit(mean[valid])
        return GroundView(
            image=image,
            valid=valid,
            resolution=resolution,
            nadir_px=np.array([size / 2 - 0.5, size / 2 - 0.5]),
            heading_deg=onboard_heading_deg,
            outline_px=footprint_outline(valid),
        )

    def markers_px(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """The astronaut detection mock-up: (helmet, backpack) photo pixels per astronaut.

        Finds the blobs of each marker colour, then pairs each helmet with
        the nearest backpack.
        """
        rgb = self.image.astype(int)
        colourful = rgb.max(axis=2) - rgb.min(axis=2) >= MARKER_CHROMA
        strongest = rgb.argmax(axis=2)

        def blobs(channel: int) -> np.ndarray:
            mask = colourful & (strongest == channel)
            labels, count = ndimage.label(mask)
            if not count:
                return np.empty((0, 2))
            rows_cols = np.array(ndimage.center_of_mass(mask, labels, range(1, count + 1)))
            return rows_cols[:, ::-1]

        helmets, backpacks = blobs(0), blobs(1)
        pairs = []
        for helmet in helmets:
            if len(backpacks):
                pairs.append((helmet, backpacks[np.argmin(np.hypot(*(backpacks - helmet).T))]))
        return pairs

    def astronauts_on_map(
        self, ground: GroundView, fix: DroneFix, window: MapWindow
    ) -> list[Astronaut]:
        """Each detected astronaut on the map, carried there by the fix.

        A photo pixel goes to the straightened view by the onboard heading
        `ground` was drawn with, then onto the map window by the fit.
        """
        a, b = fix.to_window
        found = []
        for helmet, backpack in self.markers_px():
            right, forward = self._to_camera(np.array([helmet, backpack]))
            east, north = _unturn(right, forward, ground.heading_deg)
            view = ground.nadir_px + np.column_stack([east, -north]) / ground.resolution
            on_window = a * (view[:, 0] + 1j * view[:, 1]) + b
            (hx, hy), (bx, by) = window.to_map(np.column_stack([on_window.real, on_window.imag]))
            heading = float(np.degrees(np.arctan2(hx - bx, hy - by)) % 360.0)
            found.append(
                Astronaut(
                    position=((hx + bx) / 2, (hy + by) / 2),
                    heading_deg=0.0 if heading >= 360.0 else heading,
                )
            )
        return found


def take_photo(
    photo_map: Path,
    nadir: tuple[float, float],
    heading_deg: float,
    crew: list[Astronaut],
    half_size_m: float = HALF_SIZE_M,
) -> DronePhoto:
    """The photo a drone over `nadir`, facing `heading_deg`, would take of the
    map, with the suit markers of each astronaut in `crew` drawn in."""
    # The photo's corners reach the half size times the square root of 2.
    window: MapWindow = read_map_window(photo_map, nadir, half_size_m * np.sqrt(2) + 1.0)
    size = round(2 * half_size_m / PHOTO_RESOLUTION)
    photo = DronePhoto(
        image=np.zeros((size, size, 3), dtype=np.uint8),
        resolution=PHOTO_RESOLUTION,
        half_size_m=half_size_m,
    )
    rows, cols = np.mgrid[0:size, 0:size]
    right, forward = photo._to_camera(np.column_stack([cols.ravel(), rows.ravel()]))
    east, north = _unturn(right, forward, heading_deg)
    map_px = window.to_px(np.column_stack([nadir[0] + east, nadir[1] + north]))
    ground = ndimage.map_coordinates(
        window.image.astype(np.float64), [map_px[:, 1], map_px[:, 0]], order=1
    )
    image = np.repeat(np.round(ground).astype(np.uint8).reshape(size, size)[..., None], 3, axis=2)

    for astronaut in crew:
        e, n = astronaut.position[0] - nadir[0], astronaut.position[1] - nadir[1]
        r, f = _turn(np.array([e]), np.array([n]), heading_deg)
        facing = np.radians(astronaut.heading_deg - heading_deg)
        ahead = np.array([np.sin(facing), np.cos(facing)])  # camera right, forward
        for sign, radius, rgb in (
            (1, HELMET_RADIUS_M, HELMET_RGB),
            (-1, BACKPACK_RADIUS_M, BACKPACK_RGB),
        ):
            centre = photo._from_camera(
                r + sign * MARKER_OFFSET_M * ahead[0], f + sign * MARKER_OFFSET_M * ahead[1]
            )[0]
            disc = np.hypot(cols - centre[0], rows - centre[1]) <= radius / PHOTO_RESOLUTION
            image[disc] = rgb
    return DronePhoto(image=image, resolution=PHOTO_RESOLUTION, half_size_m=half_size_m)
