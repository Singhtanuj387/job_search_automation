"""
Pydantic schemas for normalized job data, raw acquisition results, and query configs.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class NormalizedJob(BaseModel):
    """
    Normalized job posting schema matching Phase 1 specification.
    """
    source: str = Field(description="Platform or ATS name, e.g. 'arbeitnow', 'greenhouse'")
    source_job_id: str = Field(description="Original unique identifier from the source")
    title: str = Field(description="Cleaned job title")
    company: str = Field(description="Company or employer name")
    location: str = Field(description="Cleaned location string or 'Remote'")
    seniority: Optional[Literal["entry", "mid", "senior", "lead", "principal", "staff", "any"]] = Field(
        default=None, description="Inferred or declared seniority level"
    )
    salary_range: Optional[str] = Field(default=None, description="Extracted compensation range if available")
    description: str = Field(default="", description="Full or excerpted job description")
    apply_url: str = Field(description="Direct URL to view or apply for the job")
    posted_date: Optional[str] = Field(
        default=None, description="ISO 8601 date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
    )
    scraped_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp when scraped"
    )
    fetch_method: Literal["api", "rss", "structured_data", "browser"] = Field(
        description="Acquisition mechanism used"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Parse completeness heuristic between 0.0 and 1.0"
    )
    source_channel: Optional[str] = Field(
        default=None, description="Origin platform: 'ashby', 'greenhouse', 'lever', etc."
    )
    skills: List[str] = Field(
        default_factory=list, description="Extracted technology and technical skill keywords"
    )
    match_score: Optional[float] = Field(
        default=None, ge=0.0, le=100.0, description="Resume fit score from 0 to 100"
    )
    fit_verdict: Optional[Literal["Strong Match", "Moderate Match", "Reach", "Unlikely"]] = Field(
        default=None, description="Categorical fit evaluation"
    )
    fit_summary: Optional[str] = Field(
        default=None, description="1-line explanation of fit rationale"
    )
    skill_gaps: List[str] = Field(
        default_factory=list, description="Missing or weak skills compared to resume"
    )
    tailored_resume_path: Optional[str] = Field(
        default=None, description="Path to tailored PDF resume if generated"
    )
    cover_letter: Optional[str] = Field(
        default=None, description="Customized 3-paragraph cover letter if generated"
    )
    fetched_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("title", "company", "location")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return (v or "").strip()


class RawResult(BaseModel):
    """
    Unparsed acquisition payload capturing raw data and network response metadata.
    """
    source: str
    source_job_id: str
    fetch_method: Literal["api", "rss", "structured_data", "browser"]
    payload: Any
    url: str
    status_code: int = 200
    headers: Dict[str, str] = Field(default_factory=dict)
    fetched_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class QueryConfig(BaseModel):
    """
    Search query criteria for an acquisition run.
    """
    role: str = Field(description="Target role or job title keywords, e.g. 'React Developer'")
    location: str = Field(default="any", description="Target city/country or 'remote' / 'any'")
    seniority: Literal["entry", "mid", "senior", "lead", "principal", "staff", "any"] = Field(default="any")
    keywords: List[str] = Field(default_factory=list, description="Additional search or filter terms")
    sources: List[str] = Field(default_factory=list, description="List of adapter names to run")
    companies: List[str] = Field(default_factory=list, description="Optional ATS company slugs to query")


class HealthStatus(BaseModel):
    """
    Health check status for an adapter.
    """
    status: Literal["ok", "degraded", "blocked"]
    evidence: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
