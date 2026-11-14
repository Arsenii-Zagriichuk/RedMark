"""Ingenuity's Navcam camera model: CAHVORE, as given in each frame's PDS label.

CAHVORE is JPL's camera model for wide and fisheye lenses: centre C, axis A,
horizontal and vertical vectors H and V, optical axis O, radial terms R, and
entrance terms E with a linearity that blends perspective (1) and fisheye (0).
Ingenuity's labels have zero entrance terms, so the entrance pupil never moves
and a point projects in closed form, with no iteration. The formulas follow
Gennery (2006), "Generalized camera calibration including fish-eye lenses",
as implemented in JPL's cmod_cahvore.
"""

from dataclasses import dataclass

import numpy as np

_LINEARITY_EPS = 1e-15


@dataclass(frozen=True)
class Cahvore:
    """A CAHVORE model with zero entrance terms. Vectors are 3-element arrays."""

    c: np.ndarray
    a: np.ndarray
    h: np.ndarray
    v: np.ndarray
    o: np.ndarray
    r: np.ndarray  # radial terms r0, r1, r2
    linearity: float

    def project(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Image x (sample) and y (line) of N points in the model's frame.

        Points at or behind the camera's plane, or beyond what the lens model
        can image, come back as NaN.
        """
        a = self.a / np.linalg.norm(self.a)
        o = self.o / np.linalg.norm(self.o)
        p_c = np.atleast_2d(points) - self.c
        zeta = p_c @ o
        lam = p_c - zeta[:, None] * o
        lam_mag = np.linalg.norm(lam, axis=1)
        theta = np.arctan2(lam_mag, zeta)

        lin = self.linearity
        with np.errstate(invalid="ignore", divide="ignore"):
            if lin > _LINEARITY_EPS:
                usable = lin * theta < np.pi / 2
                chi = np.tan(lin * theta) / lin
            elif lin < -_LINEARITY_EPS:
                usable = np.abs(lin * theta) <= np.pi / 2
                chi = np.sin(lin * theta) / lin
            else:
                usable = np.ones_like(theta, dtype=bool)
                chi = theta
            chi2 = chi * chi
            chi_dist = chi * (1 + self.r[0] + self.r[1] * chi2 + self.r[2] * chi2 * chi2)
            # The ray as a perspective camera would see it: O plus the
            # distorted tangent along the point's direction from the axis.
            scale = np.where(lam_mag > 1e-12, chi_dist / lam_mag, 0.0)
            ray = o + lam * scale[:, None]
            alpha = ray @ a
            x = (ray @ self.h) / alpha
            y = (ray @ self.v) / alpha
        # A fisheye can see past 90° from its axis, but the ground is always
        # in front of a down-looking camera, so anything at or behind the
        # camera's plane is refused rather than wrapped onto the image.
        bad = ~usable | (alpha <= 1e-12) | (zeta <= 0)
        x[bad] = np.nan
        y[bad] = np.nan
        return x, y
