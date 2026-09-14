"""Unit tests for models and schemas."""
import pytest
from pydantic import ValidationError
from core.models import NormalizedJob, QueryConfig, HealthStatus, RawResult


def test_normalized_job_valid():
    job = NormalizedJob(
        source="test_source",
        source_job_id="12345",
        title="  Software Engineer  ",
        company="  Acme Corp  ",
        location="  Bangalore  ",
        seniority="mid",
        salary_range="$100k - $120k",
        description="Write code and tests.",
        apply_url="https://example.com/apply",
        posted_date="2026-09-01",
        fetch_method="api",
        confidence=0.95,
    )
    assert job.title == "Software Engineer"
    assert job.company == "Acme Corp"
    assert job.location == "Bangalore"
    assert job.seniority == "mid"
    assert job.confidence == 0.95
    assert job.fetch_method == "api"


def test_normalized_job_invalid_confidence():
    with pytest.raises(ValidationError):
        NormalizedJob(
            source="test",
            source_job_id="1",
            title="Dev",
            company="Co",
            location="Remote",
            apply_url="https://example.com",
            fetch_method="api",
            confidence=1.5,  # Exceeds max 1.0
        )


def test_query_config_defaults():
    q = QueryConfig(role="React Developer")
    assert q.role == "React Developer"
    assert q.location == "any"
    assert q.seniority == "any"
    assert q.keywords == []
    assert q.sources == []
