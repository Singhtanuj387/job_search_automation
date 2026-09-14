"""
Unit & Integration Tests for job-skill SKILL.md functionality.
Tests slash commands (/job-skill help, /job-skill status, etc.),
DOCX resume/cover-letter synthesis, ZIP bundle creation, and materials download endpoints.
"""
import io
import os
import zipfile
import pytest
from fastapi.testclient import TestClient

from web.backend.app import app
from web.backend.document_generator import DocumentGenerator, purge_ai_cliches
from web.backend.llm_service import LLMService

client = TestClient(app)


def test_purge_ai_cliches():
    cliche_text = "I spearheaded the team and leveraged cutting-edge synergy with results-driven passion."
    cleaned = purge_ai_cliches(cliche_text)
    assert "spearheaded" not in cleaned.lower()
    assert "cutting-edge" not in cleaned.lower()
    assert "synergy" not in cleaned.lower()
    assert "results-driven" not in cleaned.lower()


def test_document_generator_resume_and_letter():
    profile = {
        "name": "Devil",
        "role": "Software Engineer",
        "location": "Bangalore",
        "email": "devil@example.com",
        "phone": "+91 9876543210",
        "notice_period": "30 Days",
    }
    job = {
        "company": "Razorpay",
        "title": "Backend Engineer",
        "location": "Bangalore",
        "source_job_id": "test_job_001",
        "tailored_bullets": [
            "Engineered scalable payment gateway APIs handling 10k requests per minute.",
            "Wrote comprehensive unit tests and automated CI/CD deployments.",
        ],
        "cover_letter": "I am eager to contribute to Razorpay as a Backend Engineer with scalable Python services.",
    }

    # Generate Resume DOCX
    resume_doc = DocumentGenerator.generate_resume(
        candidate_name="Devil",
        profile=profile,
        job=job,
        tailored_bullets=job["tailored_bullets"],
    )
    assert resume_doc is not None

    # Generate Cover Letter DOCX
    letter_doc = DocumentGenerator.generate_cover_letter(
        candidate_name="Devil",
        profile=profile,
        job=job,
        cover_letter_text=job["cover_letter"],
    )
    assert letter_doc is not None


def test_create_application_package_and_download_endpoints():
    profile = {
        "name": "Devil",
        "role": "Software Engineer",
        "location": "Bangalore",
        "email": "devil@example.com",
    }
    jobs = [
        {
            "company": "Google",
            "title": "SDE-2",
            "location": "Bangalore",
            "source_job_id": "goog_101",
            "tailored_bullets": ["Built backend components."],
        },
        {
            "company": "Razorpay",
            "title": "Backend Engineer",
            "location": "Bangalore",
            "source_job_id": "razor_202",
            "tailored_bullets": ["Designed payment flows."],
        },
    ]

    run_id = "test_run_bundle_999"
    pkg = DocumentGenerator.create_application_package(
        run_id=run_id,
        candidate_name="Devil",
        profile=profile,
        jobs=jobs,
    )

    assert os.path.exists(pkg["zip_path"])
    assert pkg["zip_filename"].endswith(".zip")
    assert len(pkg["files"]) == 2

    # Verify ZIP contents
    with zipfile.ZipFile(pkg["zip_path"], "r") as zf:
        namelist = zf.namelist()
        assert any("Google_Bangalore" in name for name in namelist)
        assert any("Razorpay_Bangalore" in name for name in namelist)
        assert any("Resume" in name for name in namelist)
        assert any("CoverLetter" in name for name in namelist)

    # Test Download Endpoints
    # 1. Download ZIP
    resp_zip = client.get(f"/api/materials/{run_id}/zip")
    assert resp_zip.status_code == 200
    assert resp_zip.headers["content-type"] == "application/zip"

    # 2. Download individual resume
    resp_resume = client.get(f"/api/materials/{run_id}/resume/goog_101")
    assert resp_resume.status_code == 200

    # 3. Download individual cover letter
    resp_letter = client.get(f"/api/materials/{run_id}/cover-letter/goog_101")
    assert resp_letter.status_code == 200


def test_job_skill_slash_commands():
    # 1. /job-skill help
    intent_help = LLMService.classify_intent("/job-skill help")
    assert intent_help["intent"] == "help"

    # 2. /job-skill status
    intent_status = LLMService.classify_intent("/job-skill status")
    assert intent_status["intent"] == "status"

    # 3. /job-skill automate
    intent_auto = LLMService.classify_intent("/job-skill automate")
    assert intent_auto["intent"] == "automate"

    # 4. /job-skill search
    intent_search = LLMService.classify_intent("/job-skill search React Developer in Bangalore")
    assert intent_search["intent"] == "search"
    assert intent_search["role"] == "React Developer"
    assert intent_search["location"] == "Bangalore"


def test_chat_route_job_skill_help_command():
    # Create or get session
    s_resp = client.get("/api/chat/sessions")
    session_id = s_resp.json()[0]["id"]

    resp = client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "/job-skill help"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "/job-skill search" in data["content"]
    assert "Platforms searched" in data["content"]
    assert "Naukri" in data["content"]
    assert "9to5dude" in data["content"]


def test_chat_route_job_skill_status_command():
    s_resp = client.get("/api/chat/sessions")
    session_id = s_resp.json()[0]["id"]

    resp = client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "/job-skill status"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "APPLICATION STATUS UPDATE" in data["content"]
    assert "NEW UPDATES" in data["content"]
    assert "STATS" in data["content"]
