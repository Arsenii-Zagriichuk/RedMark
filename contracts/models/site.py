# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, conint, constr
from . import common


class ScienceTarget(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: constr(min_length=1) = Field(..., description="Stable id, used in other files.")
    position: common.Point
    name: str = Field(..., description="Display name.")


class Checkpoint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: constr(min_length=1) = Field(..., description="Stable id, used in other files.")
    position: common.Point


class SiteConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    site: common.SiteId
    name: str = Field(..., description="Display name.")
    projection: constr(min_length=1) = Field(
        ...,
        description="The site map's projection as a PROJ string. Jezero is reprojected so map metres are ground metres.",
    )
    bounds: common.Bounds = Field(
        ..., description="Walk area bounds (Gale) or crop bounds (Jezero)."
    )
    habitat: common.Point | None
    base_camp: common.Point | None
    science_targets: list[ScienceTarget] = Field(..., description="Empty at Jezero.")
    checkpoints: list[Checkpoint] = Field(..., description="Empty at Jezero.")
    files: dict[str, constr(min_length=1)] = Field(
        ..., description="Named data files, each a path relative to REDMARK_DATA."
    )
    replayed_sol: conint(ge=0) | None = Field(
        ...,
        description="The real sol whose conditions play during the walk (4600 to 4709 by the team plan); null at Jezero.",
    )
