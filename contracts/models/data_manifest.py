# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, conint, constr


class File(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: str = Field(..., description="What the file is.")
    path: constr(min_length=1) = Field(
        ..., description="Path relative to REDMARK_DATA."
    )
    size_bytes: conint(ge=0)
    source_url: AnyUrl = Field(..., description="Where it was downloaded from.")
    checksum: constr(min_length=1) = Field(..., description="The checksum value.")
    checksum_algorithm: constr(min_length=1) = Field(
        ..., description="e.g. sha256, or md5-s3-multipart for a USGS S3 ETag."
    )
    credit: str | None = Field(
        None,
        description="Citation or licence for References, if the source asks for one.",
    )


class DataManifest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    files: list[File]
