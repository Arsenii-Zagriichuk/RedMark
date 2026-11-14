# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, confloat, constr
from . import common


class Truth(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    position: common.Point
    heading_deg: confloat(ge=0.0, lt=360.0) = Field(
        ..., description="True heading from map north."
    )
    position_error_m: confloat(ge=0.0) = Field(
        ..., description="Error in ground metres, from the shared scorer."
    )
    heading_error_deg: confloat(ge=0.0, le=180.0) = Field(
        ...,
        description="Heading error from the shared scorer; wraps at 360°, so 0 to 180.",
    )


class FixResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    photo_id: constr(min_length=1) = Field(
        ..., description="The photo's id in its archive."
    )
    site: common.SiteId
    method: common.Method
    position: common.Point = Field(..., description="Estimated position.")
    heading_deg: confloat(ge=0.0, lt=360.0) = Field(
        ..., description="Estimated heading from map north."
    )
    uncertainty_m: PositiveFloat = Field(
        ...,
        description="Uncertainty circle radius in ground metres. PROPOSED, confirm at H0: the 95% radius.",
    )
    confidence_pct: confloat(ge=0.0, le=100.0) = Field(
        ...,
        description="PROPOSED, confirm at H0: the share of tested fixes, for this method and terrain type, whose true position fell inside their circle.",
    )
    time_per_fix_s: confloat(ge=0.0) = Field(
        ..., description="Seconds the fix took to compute."
    )
    terrain_type: common.TerrainType
    simulated: bool = Field(
        ...,
        description="True for any result not measured on real photos. Required, no default; the app shows a label whenever it is true.",
    )
    overlay: constr(min_length=1) = Field(
        ...,
        description="Repo-relative path of the overlay image that draws this fix on the base map.",
    )
    truth: Truth | None = Field(
        ...,
        description="Answer-key values for a tested photo; null for a fix on the demo walk.",
    )
    provenance: common.Provenance
