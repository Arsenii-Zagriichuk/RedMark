# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, PositiveFloat, conint, constr
from . import common


class Tiles(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: constr(pattern=r"\{z\}.*\{x\}.*\{y\}") = Field(
        ...,
        description="Tile path template relative to the layer folder, e.g. tiles/{z}/{x}/{y}.png.",
    )
    tile_size: conint(ge=1) = Field(..., description="Tile width and height in pixels.")
    min_zoom: conint(ge=0)
    max_zoom: conint(ge=0)


class LegendItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: str = Field(..., description="Text shown.")
    color: constr(pattern=r"^#[0-9a-fA-F]{6}$") = Field(..., description="Hex colour.")
    value: float | None = Field(
        None,
        description="The value this colour stands for, if the layer is continuous.",
    )


class SourceItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: str = Field(..., description="Name of the data set.")
    url: AnyUrl = Field(..., description="Where it came from.")


class LayerMeta(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: constr(pattern=r"^[a-z0-9_]+$") = Field(
        ..., description="Same as the layer's folder name."
    )
    title: str = Field(..., description="Display name.")
    group: conint(ge=1, le=5) = Field(
        ...,
        description="Layer group: 1 base, 2 walkability, 3 science, 4 conditions, 5 location quality.",
    )
    units: str = Field(
        ..., description="Units of the values the colours stand for; empty for a photo."
    )
    resolution_m: PositiveFloat = Field(
        ...,
        description="Ground size of one full-resolution pixel, in metres. The app shows it in the legend.",
    )
    bounds: common.Bounds
    tiles: Tiles = Field(
        ...,
        description="Image tiles in map metres. At max_zoom one pixel is resolution_m; each lower zoom halves the resolution. Tile (x, y) counts from the north-west corner of bounds.",
        title="Tiles",
    )
    legend: list[LegendItem] = Field(..., min_length=1)
    source: list[SourceItem] = Field(..., min_length=1)
