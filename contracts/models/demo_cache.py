# Generated from contracts/schemas by tools/gen_contracts.py. Do not edit by hand.

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, conint, constr
from typing import Any


class Method(StrEnum):
    GET = "GET"
    POST = "POST"


class Request(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: Method
    path: constr(pattern=r"^/") = Field(..., description="Service path, e.g. /route.")
    body: dict[str, Any] | None = Field(..., description="Request body; null for GET.")


class DemoCacheEntry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    step: constr(min_length=1) = Field(
        ..., description="Demo step id, e.g. planning.route.fastest."
    )
    request: Request = Field(
        ...,
        description="The request that produced the response.",
        title="CachedRequest",
    )
    status: conint(ge=100, le=599)
    contract: str | None = Field(
        ...,
        description="Name of the schema in contracts/schemas the response matches (e.g. route_response); null if none.",
    )
    response: Any = Field(..., description="The saved response body.")
