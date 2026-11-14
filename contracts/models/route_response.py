# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, confloat, conint, constr
from . import common


class Mode(StrEnum):
    fastest = "fastest"
    science = "science"
    cart = "cart"


class Leg(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    start_index: conint(ge=0)
    end_index: conint(ge=0)
    distance_m: confloat(ge=0.0) = Field(..., description="Ground metres.")
    time_s: confloat(ge=0.0) = Field(..., description="Walking time.")


class Limit(StrEnum):
    slope = "slope"
    distance_from_habitat = "distance_from_habitat"
    planning_speed = "planning_speed"
    walk_time = "walk_time"
    walk_back = "walk_back"
    daylight = "daylight"
    hazard_margin = "hazard_margin"


class LimitCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Limit
    passed: bool
    value: float = Field(..., description="The route's value for this limit.")
    threshold: float = Field(..., description="The limit it was checked against.")
    units: str = Field(..., description="Units of value and threshold.")


class Checkpoint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: constr(min_length=1) = Field(..., description="Stable id, used in other files.")
    position: common.Point


class RouteResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    site: common.SiteId
    mode: Mode = Field(
        ...,
        description="fastest safe route, science alternative, or the cart's route to base camp.",
        title="RouteMode",
    )
    path: list[common.Point] = Field(
        ..., description="Ordered positions along the path.", min_length=2
    )
    legs: list[Leg] = Field(..., min_length=1)
    total_distance_m: confloat(ge=0.0) = Field(..., description="Ground metres.")
    total_time_s: confloat(ge=0.0) = Field(..., description="Walking time.")
    walk_back_margin_s: float = Field(
        ...,
        description="Spare time under the walk-back rule at the worst point; negative means the rule fails.",
    )
    extra_time_vs_fastest_s: float | None = Field(
        ...,
        description="For the science route: extra time compared with the fastest route. Null for other modes.",
    )
    limit_checks: list[LimitCheck] = Field(
        ..., description="Every hard limit, each pass or fail.", min_length=1
    )
    checkpoints: list[Checkpoint] = Field(
        ..., description="Checkpoints along the route, in walking order."
    )
