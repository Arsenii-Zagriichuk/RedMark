from __future__ import annotations

import argparse
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backend_bases import MouseButton
from matplotlib.widgets import Button, CheckButtons, RadioButtons

from contracts.paths import data_root
from route.answer_key import (
    KeyFrame,
    draw_overlay,
    draw_tie_points,
    frames_to_key,
    load_key_frame,
    read_crop,
    read_pack,
    save_answer,
)
from route.tie_points import fit_tie_points


class KeyingWindow:
    def __init__(self, root: Path, frame: KeyFrame, *, hard_mode: bool, simulated: bool):
        self.root, self.frame, self.simulated = root, frame, simulated
        self.photo_points: list[tuple[float, float]] = []
        self.map_points: list[tuple[float, float]] = []
        self.pending: tuple[float, float] | None = None
        self.preview = None
        self.previewed = False
        self.advance = False
        self.saved_path: Path | None = None
        self.marks = []
        self.figure = plt.figure(figsize=(14, 8))
        self.photo_ax = self.figure.add_axes((0.05, 0.27, 0.41, 0.62))
        self.map_ax = self.figure.add_axes((0.54, 0.27, 0.41, 0.62))
        base, extent = read_crop(frame)
        self.photo_ax.imshow(np.ma.masked_where(~frame.valid, frame.image), cmap="gray")
        self.photo_ax.plot(*frame.reference_px, "c+", ms=12)
        self.photo_ax.set_title("1. Click a feature in the rectified photo")
        self.map_ax.imshow(base, extent=extent, cmap="gray")
        self.map_ax.set_title("2. Click the same feature on the photo map")
        self.map_ax.ticklabel_format(useOffset=False, style="plain")
        self.map_ax.set_xlabel("easting, ground metres")
        self.map_ax.set_ylabel("northing, ground metres")
        for ax in (self.photo_ax, self.map_ax):
            ax.set_autoscale_on(False)
        label = "SIMULATED fixture" if simulated else "Human tie-point answer key"
        self.figure.suptitle(
            f"P4-01: {label}\n{frame.source.photo_id}, flight {frame.source.flight}", fontsize=11
        )
        self.terrain = RadioButtons(
            self.figure.add_axes((0.05, 0.065, 0.16, 0.14)),
            ("choose terrain", "textured", "plain"),
        )
        self.checks = CheckButtons(
            self.figure.add_axes((0.24, 0.075, 0.20, 0.12)),
            ("hard mode", "overlay checked"),
            (hard_mode, False),
        )
        self.preview_button = Button(self.figure.add_axes((0.49, 0.12, 0.11, 0.055)), "Preview")
        self.save_button = Button(self.figure.add_axes((0.62, 0.12, 0.11, 0.055)), "Save key")
        self.undo_button = Button(self.figure.add_axes((0.75, 0.12, 0.09, 0.055)), "Undo")
        self.skip_button = Button(self.figure.add_axes((0.86, 0.12, 0.09, 0.055)), "Skip")
        self.status = self.figure.text(
            0.05, 0.025, "Select at least four pairs spread around the photo; no matcher is used."
        )
        self.figure.text(
            0.05,
            0.225,
            "Use the toolbar to zoom and pan; turn its mode off before selecting points. "
            "Preview, choose terrain, check the overlay, then save.",
            fontsize=9,
        )
        self.preview_button.on_clicked(self._preview)
        self.save_button.on_clicked(self._save)
        self.undo_button.on_clicked(self._undo)
        self.skip_button.on_clicked(self._close)
        self.figure.canvas.mpl_connect("button_press_event", self._click)
        self.figure.canvas.mpl_connect("close_event", self._close_preview)

    def _message(self, text: str) -> None:
        self.status.set_text(text)
        self.figure.canvas.draw_idle()

    def _invalidate(self) -> None:
        self.previewed = False
        if self.checks.get_status()[1]:
            self.checks.set_active(1)

    def _click(self, event) -> None:
        toolbar = getattr(self.figure.canvas.manager, "toolbar", None)
        if event.button != MouseButton.LEFT or (toolbar is not None and toolbar.mode):
            return
        if event.inaxes not in (self.photo_ax, self.map_ax):
            return
        point = (event.xdata, event.ydata)
        if event.inaxes == self.photo_ax:
            x, y = point
            height, width = self.frame.image.shape
            if not (0 <= x <= width - 1 and 0 <= y <= height - 1):
                return
            if not self.frame.valid[round(y), round(x)]:
                self._message("That part of the rectified photo has no visible ground.")
                return
            self.pending = point
        elif self.pending is not None:
            self.photo_points.append(self.pending)
            self.map_points.append(point)
            self.pending = None
        else:
            self._message("Click a photo feature first, then its matching map feature.")
            return
        self._invalidate()
        self._redraw()

    def _redraw(self) -> None:
        for mark in self.marks:
            mark.remove()
        self.marks = []
        self.marks = draw_tie_points(
            self.photo_ax, (self.map_ax,), self.photo_points, self.map_points
        )
        if self.pending is not None:
            self.marks.extend(self.photo_ax.plot(*self.pending, "yo", mfc="none", ms=10))
        action = "click its map feature" if self.pending else "select another pair or preview"
        self._message(f"{len(self.photo_points)} complete pairs; {action}.")

    def _undo(self, _event) -> None:
        if self.pending is not None:
            self.pending = None
        elif self.photo_points:
            self.photo_points.pop()
            self.map_points.pop()
        self._invalidate()
        self._redraw()

    def _preview(self, _event) -> None:
        try:
            if len(self.photo_points) < 4 or self.pending is not None:
                raise ValueError("finish at least four photo/map pairs before previewing")
            self._invalidate()
            fit = fit_tie_points(
                self.photo_points,
                self.map_points,
                self.frame.reference_px,
                self.frame.heading_deg,
            )
            if self.preview is None or not plt.fignum_exists(self.preview.number):
                self.preview = plt.figure(figsize=(15, 5), layout="constrained")
            draw_overlay(
                self.preview,
                self.frame,
                np.asarray(self.photo_points),
                np.asarray(self.map_points),
                fit,
                simulated=self.simulated,
            )
            self.preview.canvas.draw_idle()
            self.preview.show()
            self.previewed = True
            self._message(
                f"Inspect alignment in the preview; fit residual {fit.residual_m:.3f} m "
                "is not measured position error. Then check 'overlay checked'."
            )
        except ValueError as error:
            self._message(str(error))

    def _save(self, _event) -> None:
        try:
            if not self.previewed:
                raise ValueError("preview the current point pairs before saving")
            if self.terrain.value_selected == "choose terrain":
                raise ValueError("choose textured or plain terrain")
            hard_mode, reviewed = self.checks.get_status()
            self.saved_path = save_answer(
                self.root,
                self.frame,
                self.photo_points,
                self.map_points,
                terrain_type=self.terrain.value_selected,
                hard_mode=bool(hard_mode),
                reviewed=bool(reviewed),
                simulated=self.simulated,
            )
            self._close(None)
        except (ValueError, OSError) as error:
            self._message(str(error))

    def _close_preview(self, _event) -> None:
        if self.preview is not None:
            plt.close(self.preview)

    def _close(self, _event) -> None:
        self.advance = True
        self._close_preview(None)
        plt.close(self.figure)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hand-key Jezero frames: select at least four photo/map tie points per frame."
    )
    parser.add_argument("--photo-id", help="key only this photo id from frames.csv")
    parser.add_argument(
        "--simulated", action="store_true", help="label synthetic input as simulated"
    )
    args = parser.parse_args()
    if not os.environ.get("REDMARK_DATA"):
        parser.error("set REDMARK_DATA to Person 2's shared data folder; keys never use stub data")
    root = data_root()
    try:
        frames = read_pack(root)
        if args.photo_id:
            frames = [frame for frame in frames if frame.source.photo_id == args.photo_id]
            if not frames:
                raise ValueError(f"photo id {args.photo_id!r} is not in the Jezero pack")
        for frame in frames_to_key(root, frames):
            window = KeyingWindow(
                root, load_key_frame(frame), hard_mode=frame.hard_mode, simulated=args.simulated
            )
            plt.show(block=True)
            if window.saved_path is not None:
                print(f"saved {window.saved_path}")
            if not window.advance:
                break
    except (ValueError, OSError, KeyError) as error:
        parser.error(
            f"{error}. Ask Person 2 for the complete Jezero pack, including its PDS labels"
        )


if __name__ == "__main__":
    main()
