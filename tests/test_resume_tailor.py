"""
Tests for Resume Tailor Engine, Keyword Matcher, and Apply Agent Integration.
"""
import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from web.backend.app import app
from web.backend.db import AppDatabase
from web.backend.linkedin_apply_agent import LinkedInApplyAgent
from web.backend.seek_apply_agent import SeekApplyAgent
from web.backend.indeed_apply_agent import IndeedApplyAgent
from web.backend.resume_tailor import KeywordMatcher, ResumeSectionParser, ResumeTailorService


@pytest.fixture
def db():
    return AppDatabase()


@pytest.fixture
def client():
    return TestClient(app)


def test_keyword_matcher_analysis():
    resume_text = """
    Jane Doe - Senior Full Stack Engineer
    Skills: Python, FastAPI, React, TypeScript, PostgreSQL, Docker, Git.
    Experience: Built scalable microservices and REST APIs using Python and FastAPI.
    Integrated React frontend with state management.
    """
    job_description = """
    Senior Backend Engineer at TechCorp.
    Requirements:
    - 4+ years Python, FastAPI or Django
    - PostgreSQL database performance tuning
    - Docker and Kubernetes experience
    - AWS cloud deployment and CI/CD pipelines
    - Redis caching
    """

    analysis = KeywordMatcher.analyze_match(resume_text, job_description)
    assert "match_score" in analysis
    assert analysis["match_score"] > 40
    # Python, FastAPI, PostgreSQL, Docker should be matched
    matched = [k.lower() for k in analysis["matched_keywords"]]
    assert any("python" in k for k in matched)
    assert any("fastapi" in k for k in matched)

    # Kubernetes, AWS, Redis should be identified as missing
    missing = [k.lower() for k in analysis["missing_keywords"]]
    assert any(k in ["kubernetes", "aws", "redis"] for k in missing)


def test_resume_section_parser():
    resume_text = """
    Alex Johnson
    Bangalore, India | alex@example.com | +91 9876543210 | linkedin.com/in/alexj
    
    Professional Summary
    Experienced Software Engineer focused on high throughput distributed systems.
    
    Technical Skills
    Python, Go, Docker, AWS, PostgreSQL, Redis, Kubernetes
    
    Work Experience
    Lead Backend Engineer — Acme Corp | 2021 – Present
    * Architected real-time streaming pipeline processing 50M daily events.
    * Reduced API response latency by 35% through Redis query caching.
    * Led cross-functional squad of 5 engineers to deliver core payment gateway.
    
    Education
    Bachelor of Technology in Computer Science — IIT Madras (2020)
    """

    sections = ResumeSectionParser.parse_sections(resume_text)
    assert sections["name"] == "Alex Johnson"
    assert sections["contact"]["email"] == "alex@example.com"
    assert "Summary" in sections or sections["summary"] != ""
    assert len(sections["skills"]) > 0


def test_tailor_resume_service_and_docx_generation(db):
    session_id = "test_tailor_session_42"
    # Seed a profile
    db.upsert_profile(
        role="Frontend Engineer",
        location="Hyderabad, India",
        seniority="mid",
        name="Priya Sharma",
        email="priya@example.com",
        phone="+91 9123456780",
        resume_text="""
        Priya Sharma - Frontend Engineer
        Skills: React, JavaScript, CSS, HTML5, Redux, Webpack, Tailwind.
        Experience at CloudScale:
        * Developed responsive web applications using React and Tailwind CSS.
        * Improved Lighthouse performance scores from 65 to 94.
        """,
        skills=["React", "JavaScript", "Tailwind", "CSS"],
        session_id=session_id,
    )

    tailor_service = ResumeTailorService(db=db)
    res = tailor_service.tailor_resume(
        job_id="test-job-99",
        job_title="Senior Frontend Developer",
        company="Fintech Co",
        job_description="Looking for Senior Frontend Developer proficient in React, TypeScript, Next.js, and CI/CD pipelines.",
        session_id=session_id,
    )

    assert res["status"] == "ok"
    assert res["company"] == "Fintech Co"
    assert res["title"] == "Senior Frontend Developer"
    assert os.path.exists(res["tailored_docx_path"])
    assert res["download_url"].startswith("/api/resume/tailored/")

    # Keyword analysis metrics
    assert "score_before" in res["keyword_analysis"]
    assert "score_after" in res["keyword_analysis"]
    assert res["keyword_analysis"]["score_after"] >= res["keyword_analysis"]["score_before"]

    # Verify database persistence
    saved_rec = db.get_tailored_resume_for_job(job_id="test-job-99", session_id=session_id)
    assert saved_rec is not None
    assert saved_rec["company"] == "Fintech Co"


def test_api_tailor_and_download(client, db):
    session_id = "api_test_sess_88"
    headers = {"X-Session-ID": session_id}

    db.upsert_profile(
        role="Python Backend Developer",
        location="Remote",
        seniority="senior",
        name="Rohan Verma",
        email="rohan@example.com",
        phone="+91 9988776655",
        resume_text="Python, Django, PostgreSQL, Docker, AWS.",
        skills=["Python", "Django", "PostgreSQL"],
        session_id=session_id,
    )

    # 1. POST /api/resume/tailor
    resp = client.post(
        "/api/resume/tailor",
        headers=headers,
        json={
            "job_id": "api-job-123",
            "job_title": "Backend Python Engineer",
            "company": "DataCorp",
            "job_description": "We need a Python developer experienced with FastAPI, Docker, and Redis.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    record_id = data["id"]
    assert record_id > 0

    # 2. GET /api/resume/tailored/{record_id}/download
    dl_resp = client.get(f"/api/resume/tailored/{record_id}/download", headers=headers)
    assert dl_resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in dl_resp.headers["content-type"]
    assert len(dl_resp.content) > 1000

    # 3. GET /api/resume/tailored/by-job
    check_resp = client.get(f"/api/resume/tailored/by-job?job_id=api-job-123", headers=headers)
    assert check_resp.status_code == 200
    check_data = check_resp.json()
    assert check_data["has_tailored"] is True
    assert check_data["tailored_resume"]["id"] == record_id


def test_apply_agents_use_tailored_resume(db):
    session_id = "agent_tailor_test"
    db.upsert_profile(
        role="Data Engineer",
        location="Remote",
        seniority="mid",
        name="Ananya Sen",
        email="ananya@example.com",
        session_id=session_id,
    )

    # Generate a tailored resume
    tailor_service = ResumeTailorService(db=db)
    tailor_res = tailor_service.tailor_resume(
        job_id="li-job-55",
        job_title="Data Platform Engineer",
        company="StreamingGlobal",
        job_description="Data platform engineering with Spark, Python, and Kafka.",
        session_id=session_id,
    )
    tailored_path = tailor_res["tailored_docx_path"]
    assert os.path.exists(tailored_path)

    job_dict = {
        "id": 555,
        "source_job_id": "li-job-55",
        "company": "StreamingGlobal",
        "title": "Data Platform Engineer",
        "tailored_resume_path": tailored_path,
    }

    # 1. LinkedIn agent
    li_agent = LinkedInApplyAgent(credentials={}, resume_data={}, profile={"name": "Ananya Sen"})
    resolved_li = li_agent._resolve_profile_resume_path(job_dict)
    assert resolved_li == os.path.abspath(tailored_path)

    # 2. SEEK agent
    seek_agent = SeekApplyAgent(credentials={}, resume_data={}, profile={"name": "Ananya Sen"})
    resolved_seek = seek_agent._resolve_profile_resume_path(job_dict)
    assert resolved_seek == os.path.abspath(tailored_path)

