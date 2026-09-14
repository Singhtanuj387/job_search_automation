"""Unit tests for fuzzy deduplication."""
from core.dedup import (
    are_jobs_duplicate,
    deduplicate_jobs,
    normalize_company,
    normalize_location,
    normalize_title,
)
from core.models import NormalizedJob


def test_normalization():
    assert normalize_company("Stripe, Inc.") == "stripe"
    assert normalize_company("Canonical Group Ltd") == "canonical"
    assert normalize_location("Bengaluru, India") == "bangalore india"
    assert normalize_location("Remote - Worldwide") == "remote"
    assert normalize_title("Senior React Developer (m/f/d)") == "senior react developer"


def test_are_jobs_duplicate():
    job1 = NormalizedJob(
        source="greenhouse",
        source_job_id="1",
        title="Senior React Developer",
        company="Canonical Group Ltd",
        location="Bengaluru, Karnataka",
        apply_url="https://greenhouse.io/job1",
        fetch_method="api",
        confidence=0.8,
    )
    job2 = NormalizedJob(
        source="jobicy",
        source_job_id="2",
        title="Sr. React Developer",
        company="Canonical",
        location="Bangalore",
        apply_url="https://jobicy.com/job2",
        fetch_method="api",
        confidence=0.9,
    )
    assert are_jobs_duplicate(job1, job2)


def test_deduplicate_jobs_reduction():
    job1 = NormalizedJob(
        source="greenhouse",
        source_job_id="1",
        title="Senior React Developer",
        company="Canonical Group Ltd",
        location="Bangalore",
        apply_url="https://greenhouse.io/job1",
        fetch_method="api",
        confidence=0.7,
        description="Short description",
    )
    job2 = NormalizedJob(
        source="lever",
        source_job_id="2",
        title="Senior React Developer",
        company="Canonical",
        location="Bangalore",
        apply_url="https://lever.co/job2",
        fetch_method="api",
        confidence=0.9,
        description="Long detailed description with responsibilities",
    )
    job3 = NormalizedJob(
        source="arbeitnow",
        source_job_id="3",
        title="Go Backend Engineer",
        company="Docker",
        location="Berlin",
        apply_url="https://arbeitnow.com/job3",
        fetch_method="api",
        confidence=0.8,
    )

    unique_jobs, metrics = deduplicate_jobs([job1, job2, job3])
    assert len(unique_jobs) == 2
    assert metrics["duplicates_pruned"] == 1
    assert metrics["reduction_rate"] == 33.33
    # The winner of the cluster should be job2 because of higher confidence
    winner = [j for j in unique_jobs if "canonical" in j.company.lower()][0]
    assert winner.source == "lever"
    assert winner.confidence == 0.9
