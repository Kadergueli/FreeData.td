from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ObservationCreate(BaseModel):
    sector: Literal["agriculture", "markets", "transport", "education", "environment", "economy", "health", "energy"]
    indicator: str = Field(min_length=2, max_length=120)
    value: float
    unit: str = Field(min_length=1, max_length=40)
    reference_date: date
    country_code: str = Field(default="TCD", min_length=3, max_length=3)
    region: str = Field(default="national", max_length=80)
    source: str = Field(min_length=2, max_length=80)
    source_url: str | None = Field(default=None, max_length=500)
    license: str = Field(default="CC BY 4.0", max_length=80)
    notes: str | None = None
    flags: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, v: float) -> float:
        # NaN/Infinity break strict JSON parsers (json.dumps emits the literal
        # tokens NaN/Infinity, which are invalid per the JSON spec) - this would
        # silently corrupt the public CSV/JSON exports researchers rely on.
        if v != v or v in (float("inf"), float("-inf")):  # v != v is the classic NaN check
            raise ValueError("value must be a finite number (NaN/Infinity are not allowed)")
        return v

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_http(cls, v: str | None) -> str | None:
        # Not rendered as a clickable link anywhere today, but validating now
        # prevents a javascript:/data: URI from becoming exploitable the day
        # someone adds a "view source" link without re-checking this field.
        if v is None or v == "":
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            return None
        return v


class CollectionResult(BaseModel):
    agent: str
    source: str
    received: int
    accepted: int
    rejected: int
    stored: int
    started_at: datetime
    completed_at: datetime
    errors: list[str] = []


class StudyResult(BaseModel):
    id: int | None = None
    sector: str | None = None
    model: str
    observations_used: int
    report: str
