# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, confloat, conint, constr
from typing import Dict
from . import common


class Metrics(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    n: conint(ge=1) = Field(..., description="Number of fixes.")
    median_error_m: confloat(ge=0.0) = Field(
        ..., description="Median position error, ground metres."
    )
    within_1m_pct: confloat(ge=0.0, le=100.0) = Field(
        ..., description="Share of fixes with error ≤ 1 m."
    )
    within_5m_pct: confloat(ge=0.0, le=100.0) = Field(
        ..., description="Share of fixes with error ≤ 5 m."
    )
    within_10m_pct: confloat(ge=0.0, le=100.0) = Field(
        ..., description="Share of fixes with error ≤ 10 m."
    )
    median_heading_error_deg: confloat(ge=0.0, le=180.0) | None = Field(
        ...,
        description="Median heading error; null when the method gives no heading to score.",
    )
    median_time_per_fix_s: confloat(ge=0.0) | None = Field(
        ..., description="Median seconds per fix; null for a simulated error model."
    )


class Groups(BaseModel):
    model_config = ConfigDict(
        extra="allow",
    )
    __annotations__ = {
        "__pydantic_extra__": Dict[str, Metrics],
    }
    textured: Metrics
    plain: Metrics


class TestSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    test: constr(pattern=r"^[a-z0-9-]+$") = Field(
        ..., description="Test id, e.g. drone-jezero or horizon-gale."
    )
    site: common.SiteId
    method: common.Method
    simulated: bool = Field(
        ...,
        description="True for a simulated error model (e.g. stage 2 if the real attempt fails). The Test lab never shows these.",
    )
    overall: Metrics
    groups: Groups = Field(
        ...,
        description="The same numbers split by terrain type (textured, plain), plus any extra split such as hard_mode.",
    )
    provenance: common.Provenance
