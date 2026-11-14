# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, confloat
from . import common


class FixScheduleItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    time_s: confloat(ge=0.0) = Field(..., description="Seconds from the start.")
    method: common.Method


class BreakIt(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    camera_off: bool
    radio_off: bool
    drone_grounded: bool


class SimulateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    site: common.SiteId
    path: list[common.Point] = Field(
        ..., description="Ordered positions along the path.", min_length=2
    )
    fix_schedule: list[FixScheduleItem]
    break_it: BreakIt = Field(
        ...,
        description="Break-it scenario flags; all true is everything at once (lost mode).",
        title="BreakIt",
    )
    seed: int = Field(..., description="The same seed and inputs replay the same walk.")
