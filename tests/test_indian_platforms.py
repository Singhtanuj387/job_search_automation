"""
Unit tests for the 12 Indian & Global platforms adapters and full results support.
"""
from adapters import ALL_ADAPTERS
from adapters.indian_platforms import (
    NaukriAdapter,
    LinkedInAdapter,
    InstahyreAdapter,
    CutshortAdapter,
    HiristAdapter,
    IndeedIndiaAdapter,
    FounditAdapter,
    ShineAdapter,
    TimesJobsAdapter,
    GlassdoorAdapter,
    WellfoundAdapter,
    WeWorkRemotelyAdapter,
)
from core.models import QueryConfig, NormalizedJob


def test_all_18_adapters_registered():
    expected_sources = [
        "naukri", "linkedin", "instahyre", "cutshort", "hirist",
        "indeed", "foundit", "shine", "timesjobs", "glassdoor",
        "wellfound", "weworkremotely", "greenhouse", "lever",
        "arbeitnow", "jobicy", "remotive", "seek", "career_jsonld"
    ]
    for src in expected_sources:
        assert src in ALL_ADAPTERS, f"Adapter {src} not found in ALL_ADAPTERS"
    assert len(ALL_ADAPTERS) >= 19


def test_indian_adapters_fetch_and_parse():
    query = QueryConfig(role="Frontend Developer", location="Bangalore")

    adapters_to_test = [
        NaukriAdapter(),
        CutshortAdapter(),
        HiristAdapter(),
        IndeedIndiaAdapter(),
        FounditAdapter(),
        ShineAdapter(),
        TimesJobsAdapter(),
        GlassdoorAdapter(),
        WellfoundAdapter(),
    ]

    for adapter in adapters_to_test:
        raw_list = adapter.fetch(query)
        assert len(raw_list) > 0, f"{adapter.name} returned 0 raw results"

        parsed = adapter.parse(raw_list[0])
        assert len(parsed) == 1
        job = parsed[0]
        assert isinstance(job, NormalizedJob)
        assert job.source == adapter.name
        assert job.source_job_id.startswith(adapter.prefix)
        assert "Developer" in job.title or "Engineer" in job.title or job.title
        assert job.company
        assert "Bangalore" in job.location or "Bengaluru" in job.location or "India" in job.location
        assert job.apply_url
        assert "foundit.com/job" not in job.apply_url
        assert "hirist.com/job" not in job.apply_url
        assert "timesjobs.com/job/" not in job.apply_url


def test_wwr_and_instahyre_schemas():
    query = QueryConfig(role="Frontend Developer", location="Bangalore")

    ins = InstahyreAdapter()
    ins_raw = ins.fetch(query)
    assert len(ins_raw) > 0
    ins_job = ins.parse(ins_raw[0])[0]
    assert ins_job.source == "instahyre"
    assert ins_job.apply_url

    wwr = WeWorkRemotelyAdapter()
    wwr_raw = wwr.fetch(query)
    assert len(wwr_raw) > 0
    wwr_job = wwr.parse(wwr_raw[0])[0]
    assert wwr_job.source == "weworkremotely"
    assert wwr_job.location == "Remote"


def test_build_direct_job_url():
    from adapters.indian_platforms import build_direct_job_url

    url_fnd = build_direct_job_url("foundit", "Dell Technologies", "Senior AI engineer", "Bangalore")
    assert "foundit.in/srp/results" in url_fnd
    assert "locations=Bangalore" in url_fnd
    assert "query=Senior+AI+engineer" in url_fnd

    # Verify duplicate 'Senior Senior' stutter is eliminated and company is not polluting Foundit skills query
    url_dup = build_direct_job_url("foundit", "Dell Technologies", "Senior Senior React Developer", "Bangalore")
    assert "Senior+Senior" not in url_dup
    assert "query=Senior+React+Developer" in url_dup

    url_hir = build_direct_job_url("hirist", "Zomato", "Senior AI engineer", "Bangalore")
    assert "hirist.tech/search" in url_hir

    url_tj = build_direct_job_url("timesjobs", "ICICI Lombard", "Senior AI engineer", "Bangalore")
    assert "timesjobs.com/candidate/job-search" in url_tj

    url_gls = build_direct_job_url("glassdoor", "Intuit India", "Staff AI engineer", "Bangalore")
    assert "glassdoor.co.in/Job/jobs" in url_gls

    url_ind = build_direct_job_url("indeed", "Indium Software", "Data Scientist", "Bangalore")
    assert "in.indeed.com/jobs" in url_ind
    assert "sc=0kf%3Aattr%285QWDV%29%3B" in url_ind

    url_wf = build_direct_job_url("wellfound", "BrowserStack", "Senior AI engineer", "Bangalore")
    assert "wellfound.com/jobs" in url_wf

    url_nk = build_direct_job_url("naukri", "Infosys FinTech", "Senior AI engineer", "Bangalore")
    assert "naukri.com/jobs-in-india" in url_nk

    url_seek = build_direct_job_url(
        "seek",
        "Macquarie Group",
        "Data Scientist - Financial Data Architecture",
        "Sydney NSW",
        item_id="94652603",
    )
    assert url_seek == "https://au.seek.com/job/94652603"


def test_indeed_authentic_postings_not_hardcoded_dummies():
    adapter = IndeedIndiaAdapter()
    query = QueryConfig(role="Data Scientist", location="Bangalore")
    results = adapter.fetch(query)
    assert len(results) > 0

    parsed = adapter.parse(results[0])
    assert len(parsed) == 1
    job = parsed[0]
    # Verify no fake dummy catalog artifacts
    assert job.company not in ["Oracle IDC", "Amazon India"]
    assert "IND-" in job.source_job_id
    assert "viewjob?jk=" in job.apply_url or "in.indeed.com/jobs?" in job.apply_url

