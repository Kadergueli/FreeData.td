from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ObservationCreate(BaseModel):
    sector: Literal["agriculture", "markets", "transport", "education", "environment", "economy"]
    indicator: str = Field(min_length=2, max_length=120)
    value: float
    unit: str = Field(min_length=1, max_length=40)
    reference_date: date
    country_code: str = Field(default="TCD", min_length=3, max_length=3)
    region: str = Field(default="national", max_length=80)
    source: str = Field(min_length=2, max_length=80)
    source_url: str | None = None
    license: str = Field(default="CC BY 4.0", max_length=80)
    notes: str | None = None
    flags: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
