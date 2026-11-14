# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, confloat
from . import common


class Mode(StrEnum):
    fastest = "fastest"
    science = "science"
    cart = "cart"


class Limits(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    max_slope_deg: confloat(le=90.0, gt=0.0) = Field(
        ..., description="Steepest slope allowed."
    )
    max_distance_from_habitat_m: PositiveFloat = Field(
        ..., description="Distance from the habitat no point may exceed."
    )
    planning_speed_kmh: PositiveFloat = Field(..., description="Planning walk speed.")
    max_walk_h: PositiveFloat = Field(
        ..., description="Longest walk, exit to re-entry."
    )


class RouteRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    site: common.SiteId
    start: common.Point
    goal: common.Point
    mode: Mode = Field(
        ...,
        description="fastest safe route, science alternative, or the cart's route to base camp.",
        title="RouteMode",
    )
    uncertainty_m: confloat(ge=0.0) = Field(
        ...,
        description="Current uncertainty circle radius in ground metres; the hazard margin grows with it.",
    )
    limits: Limits = Field(
        ...,
        description="The hard limits for this request. Defaults from Artemis planning: 20° slope (15° as an option), 2 km from the habitat, 2 km/h planning speed, about 6 h walk.",
        title="RouteLimits",
    )
