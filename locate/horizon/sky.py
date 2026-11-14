"""Find the skyline in a photo: in each column, the row where the sky ends.

Martian sky in a Navcam frame is smooth and brightens slowly downward, so the
skyline is the first strong vertical step in brightness below the top of the
frame. The image is first averaged over a short, wide box (horizontal edges
like a hazy crater rim survive, pixel noise does not), and a step counts as
strong when it stands well clear of the steps in the sky at the top of the
frame. A running median along the row then removes single-column misreads
(dead columns, dust specks).
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

BORDER_PX = 4  # real frames have a saturated top row and odd edge columns
BOX_ROWS, BOX_COLS = 5, 21
FINE_BOX_COLS = 3
SEARCH_ROWS = 12  # how far the narrow box looks for the edge, either way
STEP_ROWS = 4
SKY_ROWS = 40
STRONG = 8.0  # times the spread of the sky's steps
MEDIAN_COLS = 31


def skyline_rows(image: np.ndarray) -> np.ndarray:
    """For each column, the row (fractional) where the sky meets the ground;
    NaN where no skyline is found, and in the outer columns the box can't see."""
    image = np.asarray(image, np.float64).copy()
    image[:BORDER_PX] = image[BORDER_PX]
    image[:, :BORDER_PX] = image[:, [BORDER_PX]]
    image[:, -BORDER_PX:] = image[:, [-BORDER_PX - 1]]
    smooth = _box(image, BOX_ROWS, BOX_COLS)
    step = np.abs(smooth[STEP_ROWS:] - smooth[:-STEP_ROWS])  # step[r]: row r to r + STEP_ROWS
    # The sky's steps: their median plus STRONG times their spread, in each
    # column's top rows; taken from the quietest columns, since a ridge can
    # fill the top of some.
    sky = step[BORDER_PX : BORDER_PX + SKY_ROWS]
    middle = np.median(sky, axis=0)
    spread = 1.4826 * np.median(np.abs(sky - middle), axis=0)
    strong = step > np.percentile(middle + STRONG * spread, 20)

    first = strong.argmax(axis=0)
    # The wide box smears a sloping skyline over several rows, so the edge is
    # placed where a narrow box's step peaks, near where the wide step began.
    fine_smooth = _box(image, BOX_ROWS, FINE_BOX_COLS)
    fine = np.abs(fine_smooth[STEP_ROWS:] - fine_smooth[:-STEP_ROWS])
    columns = np.arange(fine.shape[1])
    near = np.clip(first[None, :] + np.arange(-SEARCH_ROWS, SEARCH_ROWS + 1)[:, None], 0, None)
    near = np.minimum(near, fine.shape[0] - 1)
    rows = near[fine[near, columns].argmax(axis=0), columns] + STEP_ROWS / 2
    # An edge right at the top means no sky was seen above it in this column:
    # the skyline is above the frame.
    rows[~strong.any(axis=0) | (rows <= BORDER_PX + BOX_ROWS + STEP_ROWS)] = np.nan

    blind = BORDER_PX + BOX_COLS // 2
    rows[:blind] = rows[-blind:] = np.nan
    return _running_median(rows, MEDIAN_COLS)


def _running_median(values: np.ndarray, width: int) -> np.ndarray:
    """Median of each width-wide window, where most of the window has a value;
    so a few stray hits in a column run with no skyline stay NaN."""
    half = width // 2
    windows = sliding_window_view(np.pad(values, half, constant_values=np.nan), width)
    counts = np.isfinite(windows).sum(axis=1)
    ordered = np.sort(windows, axis=1)  # NaN sorts last
    index = np.arange(len(values))
    low = ordered[index, np.maximum((counts - 1) // 2, 0)]
    high = ordered[index, counts // 2]
    return np.where(counts > half, (low + high) / 2, np.nan)


def _box(image: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Mean over a rows x cols box centred on each pixel (edges repeated)."""
    padded = np.pad(image, ((rows // 2, rows // 2), (cols // 2, cols // 2)), mode="edge")
    total = np.pad(padded.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
    return (
        total[rows:, cols:] - total[:-rows, cols:] - total[rows:, :-cols] + total[:-rows, :-cols]
    ) / (rows * cols)
