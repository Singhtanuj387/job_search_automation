"""Unit tests for adapter parsing and normalization."""
from adapters.arbeitnow import ArbeitnowAdapter
from adapters.greenhouse import GreenhouseAdapter
from adapters.lever import LeverAdapter
from adapters.remotive import RemotiveAdapter
from adapters.jobicy import JobicyAdapter
from adapters.career_page_jsonld import CareerPageJsonLdAdapter
from core.models import RawResult


def test_arbeitnow_parsing():
    adapter = ArbeitnowAdapter()
    raw = RawResult(
        source="arbeitnow",
        source_job_id="ops-manager-1",
        fetch_method="api",
        payload={
            "slug": "ops-manager-1",
            "title": "Operations Manager",
            "company_name": "Acme GmbH",
            "location": "Berlin",
            "remote": False,
            "url": "https://arbeitnow.com/jobs/1",
            "description": "Lead ops.",
            "created_at": 1725450000,
        },
        url="https://arbeitnow.com/jobs/1",
    )
    jobs = adapter.parse(raw)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Operations Manager"
    assert job.company == "Acme GmbH"
    assert job.location == "Berlin"
    assert job.source == "arbeitnow"
    assert job.confidence >= 0.8


def test_greenhouse_parsing():
    adapter = GreenhouseAdapter()
    raw = RawResult(
        source="greenhouse",
        source_job_id="9988",
        fetch_method="api",
        payload={
            "company_slug": "canonical",
            "job": {
                "id": 9988,
                "title": "Senior Cloud Engineer",
                "location": {"name": "Remote, EMEA"},
                "content": "<p>Build cloud systems</p>",
                "absolute_url": "https://boards.greenhouse.io/canonical/jobs/9988",
                "updated_at": "2026-08-15T10:00:00Z",
            },
        },
        url="https://boards.greenhouse.io/canonical/jobs/9988",
    )
    jobs = adapter.parse(raw)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Senior Cloud Engineer"
    assert job.company == "Canonical"
    assert job.location == "Remote, EMEA"
    assert job.seniority == "senior"
    assert "Build cloud systems" in job.description


def test_lever_parsing():
    adapter = LeverAdapter()
    raw = RawResult(
        source="lever",
        source_job_id="lev-123",
        fetch_method="api",
        payload={
            "company_slug": "spotify",
            "job": {
                "id": "lev-123",
                "text": "Data Engineer",
                "categories": {"location": "Stockholm", "team": "Data Platform"},
                "descriptionPlain": "Build spark pipelines",
                "hostedUrl": "https://jobs.lever.co/spotify/lev-123",
                "applyUrl": "https://jobs.lever.co/spotify/lev-123/apply",
                "createdAt": 1725450000000,
            },
        },
        url="https://jobs.lever.co/spotify/lev-123",
    )
    jobs = adapter.parse(raw)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Data Engineer"
    assert job.company == "Spotify"
    assert job.location == "Stockholm"
    assert "Build spark pipelines" in job.description


def test_jobicy_parsing():
    adapter = JobicyAdapter()
    raw = RawResult(
        source="jobicy",
        source_job_id="jobicy-101",
        fetch_method="api",
        payload={
            "id": 101,
            "jobTitle": "Lead Full Stack Developer",
            "companyName": "Tech Corp",
            "jobGeo": "USA, Canada",
            "salaryMin": 120000,
            "salaryMax": 150000,
            "salaryCurrency": "$",
            "jobExcerpt": "Work on modern web tech stack.",
            "pubDate": "2026-09-01T12:00:00Z",
            "url": "https://jobicy.com/job/101",
        },
        url="https://jobicy.com/job/101",
    )
    jobs = adapter.parse(raw)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Lead Full Stack Developer"
    assert job.company == "Tech Corp"
    assert job.salary_range == "$120,000 - $150,000"
    assert job.seniority == "lead"


def test_seek_parsing():
    from adapters.seek import SeekAdapter
    adapter = SeekAdapter()
    raw = RawResult(
        source="seek",
        source_job_id="SEK-78401928",
        fetch_method="api",
        payload={
            "id": "78401928",
            "title": "Senior Cloud Engineer - Cloud Platforms",
            "company": "Atlassian",
            "location": "Sydney NSW",
            "salary": "$170,000 - $200,000 + Equity",
            "description": "Lead scalable cloud distributed systems. Verified via SEEK.",
            "apply_url": "https://www.seek.com.au/job/78401928",
        },
        url="https://www.seek.com.au/job/78401928",
    )
    jobs = adapter.parse(raw)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "seek"
    assert job.source_job_id == "SEK-78401928"
    assert job.title == "Senior Cloud Engineer - Cloud Platforms"
    assert job.company == "Atlassian"
    assert job.location == "Sydney NSW"
    assert job.seniority == "senior"
    assert job.apply_url == "https://au.seek.com/job/78401928"
    assert job.confidence >= 0.9


def test_seek_fetch_and_parse():
    from adapters.seek import SeekAdapter
    from core.models import QueryConfig
    adapter = SeekAdapter()
    query = QueryConfig(role="Data Scientist", location="Sydney")
    raw_list = adapter.fetch(query)
    assert len(raw_list) > 0
    parsed = adapter.parse(raw_list[0])
    assert len(parsed) == 1
    job = parsed[0]
    assert job.source == "seek"
    assert job.source_job_id.startswith("SEK-")
    assert "https://au.seek.com/job/" in job.apply_url
    assert job.company


def test_seek_seniority_levels_and_orchestrator():
    from adapters.seek import SeekAdapter
    from core.models import QueryConfig
    from core.orchestrator import Orchestrator

    adapter = SeekAdapter()
    orch = Orchestrator()

    for sen in ["entry", "mid", "senior", "lead", "any"]:
        query = QueryConfig(role="Data Scientist", location="Sydney", seniority=sen, sources=["seek"])
        raw_list = adapter.fetch(query)
        assert len(raw_list) > 0

        matched_count = 0
        for r in raw_list:
            jobs = adapter.parse(r)
            for j in jobs:
                if orch._matches_query(j, query):
                    matched_count += 1
        assert matched_count > 0, f"Expected matches for seniority={sen}, got 0"


