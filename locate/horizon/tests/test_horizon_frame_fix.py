"""Every frame of a ring gets its own fix result, taken from the ring's fix."""

import pytest

from contracts.models.common import Method, Point, Provenance, SiteId, TerrainType
from contracts.models.fix_result import FixResult
from contracts.scoring import score_fix
from locate.horizon.fix import frame_fix

TRUE_POSITION = Point(x=8144680.0, y=-283230.0)


def _ring_fix(heading_deg: float, label_heading_deg: float) -> FixResult:
    fix = FixResult(
        photo_id="NLB_759345596ILT_S1052222NCAM00275M1",
        site=SiteId.gale,
        method=Method.horizon,
        position=Point(x=8144700.0, y=-283240.0),
        heading_deg=heading_deg,
        uncertainty_m=71.0,
        confidence_pct=0.0,
        time_per_fix_s=3.9,
        terrain_type=TerrainType.plain,
        simulated=False,
        overlay="results/horizon/overlays/p3-03-NLB_759345596ILT_S1052222NCAM00275M1.png",
        truth=None,
        provenance=Provenance(script="locate/horizon/hidden_test.py", commit="abc", inputs=[]),
    )
    return score_fix(fix, TRUE_POSITION, label_heading_deg)


def test_a_frame_keeps_the_ring_fix_and_turns_by_its_own_pointing():
    ring = _ring_fix(heading_deg=35.25, label_heading_deg=35.02)

    frame = frame_fix(ring, "NLB_759345668ILT_S1052222NCAM00275M1", label_heading_deg=125.02)

    assert frame.photo_id == "NLB_759345668ILT_S1052222NCAM00275M1"
    assert frame.heading_deg == pytest.approx(125.25)
    assert frame.truth.heading_deg == pytest.approx(125.02)
    assert frame.truth.heading_error_deg == pytest.approx(0.23)
    assert frame.position == ring.position
    assert frame.uncertainty_m == 71.0
    assert frame.truth.position_error_m == ring.truth.position_error_m
    assert frame.overlay == ring.overlay


def test_a_frame_heading_wraps_past_north():
    ring = _ring_fix(heading_deg=350.0, label_heading_deg=349.0)

    frame = frame_fix(ring, "NRB_2", label_heading_deg=19.0)  # 30° right of the reference

    assert frame.heading_deg == pytest.approx(20.0)
    assert frame.truth.heading_error_deg == pytest.approx(1.0)
