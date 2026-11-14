# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, confloat, conint, constr
from . import common


class Source(StrEnum):
    measured = "measured"
    estimated = "estimated"


class Dust(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    optical_depth: confloat(ge=0.0) = Field(
        ..., description="Atmospheric optical depth (tau)."
    )
    source: Source


class Step(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lmst: constr(pattern=r"^[0-2][0-9]:[0-5][0-9]$") = Field(
        ..., description="Local mean solar time, HH:MM."
    )
    temperature_c: float = Field(..., description="Air temperature from REMS.")
    pressure_pa: confloat(ge=0.0) = Field(..., description="Pressure from REMS.")
    sun_azimuth_deg: confloat(ge=0.0, lt=360.0) = Field(
        ..., description="Sun direction from map north."
    )
    sun_elevation_deg: confloat(ge=-90.0, le=90.0) = Field(
        ..., description="Sun elevation."
    )


class Conditions(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    site: common.SiteId
    sol: conint(ge=0)
    radiation_ugy_per_day: confloat(ge=0.0) = Field(
        ..., description="Daily radiation dose from RAD, µGy/day."
    )
    dust: Dust = Field(
        ...,
        description="Dust optical depth, labelled measured or estimated.",
        title="Dust",
    )
    sunset_lmst: constr(pattern=r"^[0-2][0-9]:[0-5][0-9]$") = Field(
        ..., description="Sunset, local mean solar time, HH:MM."
    )
    steps: list[Step] = Field(..., min_length=1)
    provenance: common.Provenance
