# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, confloat, constr
from . import common
from typing import Literal


class Source(StrEnum):
    visual_odometry = "visual_odometry"
    motion_sensor = "motion_sensor"
    step_count = "step_count"
    sun = "sun"
    horizon = "horizon"
    ground = "ground"
    drone = "drone"
    radio = "radio"


class Event(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: constr(min_length=1) = Field(..., description="What happened.")
    method: common.Method | None = None


class Mode(StrEnum):
    normal = "normal"
    offline = "offline"
    lost = "lost"


class Step(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    t_s: confloat(ge=0.0) = Field(..., description="Seconds from the start.")
    true_position: common.Point
    estimated_position: common.Point
    uncertainty_m: PositiveFloat = Field(
        ..., description="Uncertainty circle radius, ground metres."
    )
    confidence_pct: confloat(ge=0.0, le=100.0) = Field(
        ..., description="Confidence shown with the estimate."
    )
    sources: list[Source] = Field(..., description="Sources active at this tick.")
    events: list[Event]
    mode: Mode


class SimulateResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    site: common.SiteId
    simulated: Literal[True] = Field(
        ..., description="A walk simulation is always simulated; the app labels it."
    )
    seed: int
    steps: list[Step] = Field(..., min_length=1)
