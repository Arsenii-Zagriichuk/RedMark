# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, RootModel, constr
from enum import StrEnum


class Common(RootModel[Any]):
    root: Any = Field(
        ...,
        description="Definitions shared by every RedMark contract. All positions are metres in the site map's own projection, the same frame as Curiosity's recorded positions. Errors and distances are ground metres.",
        title="Common",
    )


class Point(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    x: float = Field(..., description="Easting, map metres.")
    y: float = Field(..., description="Northing, map metres.")


class Bounds(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    min_x: float = Field(..., description="West edge.")
    min_y: float = Field(..., description="South edge.")
    max_x: float = Field(..., description="East edge.")
    max_y: float = Field(..., description="North edge.")


class SiteId(StrEnum):
    gale = "gale"
    jezero = "jezero"


class Method(StrEnum):
    horizon = "horizon"
    ground = "ground"
    drone = "drone"


class TerrainType(StrEnum):
    textured = "textured"
    plain = "plain"


class Input(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: str = Field(..., description="Path of the input file.")
    sha256: constr(pattern=r"^[0-9a-f]{64}$") = Field(
        ..., description="SHA-256 of the input file."
    )


class Provenance(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    script: constr(min_length=1) = Field(
        ..., description='Repo path of the script that wrote the file, or "stub".'
    )
    commit: str = Field(..., description="Git commit the script ran at.")
    inputs: list[Input] = Field(..., description="Every input file the script read.")
