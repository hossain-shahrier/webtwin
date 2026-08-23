"""SPA-oriented observation contracts — optional fields; HTML multipage mode ignores them."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RouteSnapshot(BaseModel):
    url: str
    path: str = "/"
    search: str = ""
    hash: str = ""
    title: str = ""


class ElementIdentity(BaseModel):
    stable_key: str
    role: str | None = None
    name: str | None = None
    testid: str | None = None
    selector_candidates: list[str] = Field(default_factory=list)
    confidence: float = 1.0
