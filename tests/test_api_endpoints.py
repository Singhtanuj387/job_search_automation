"""Integration tests for FastAPI REST endpoints."""
from fastapi.testclient import TestClient
from web.backend.app import app

client = TestClient(app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_profile_lifecycle():
    # Update profile
    payload = {
        "role": "Frontend Developer",
        "location": "Bangalore",
        "seniority": "mid",
        "resume_text": "Experienced React and TypeScript engineer.",
    }
    resp = client.post("/api/profile", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Get profile
    resp2 = client.get("/api/profile")
    assert resp2.status_code == 200
    prof = resp2.json()["profile"]
    assert prof["role"] == "Frontend Developer"
    assert prof["location"] == "Bangalore"


def test_profile_preferences_and_resume_endpoints():
    # Update profile with full career preferences
    payload = {
        "name": "Tanuj Singh",
        "role": "Senior React Developer",
        "location": "Bangalore",
        "seniority": "senior",
        "company_type": "Product-based",
        "notice_period": "30 Days",
        "expected_ctc_lpa": "24-32 LPA",
        "email": "tanuj@example.com",
        "phone": "+91 9999988888",
        "linkedin_url": "https://linkedin.com/in/tanujsingh",
        "resume_text": "Staff React Developer with 6 years experience in Redux, TypeScript, Next.js, and Jest.",
        "resume_filename": "Tanuj_Singh_Resume.pdf",
        "skills": ["React", "TypeScript", "Redux", "Next.js", "Jest"],
    }
    resp = client.post("/api/profile", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify retrieval
    resp2 = client.get("/api/profile")
    assert resp2.status_code == 200
    p = resp2.json()["profile"]
    assert p["name"] == "Tanuj Singh"
    assert p["role"] == "Senior React Developer"
    assert p["notice_period"] == "30 Days"
    assert p["expected_ctc_lpa"] == "24-32 LPA"
    assert p["company_type"] == "Product-based"
    assert p["seniority"] == "senior"
    assert p["resume_filename"] == "Tanuj_Singh_Resume.pdf"
    assert "React" in p["skills"]

    # Test clear resume
    resp_del = client.delete("/api/profile/resume")
    assert resp_del.status_code == 200
    del_prof = resp_del.json()["profile"]
    assert del_prof["resume_text"] == ""
    assert del_prof["resume_filename"] == ""
    # Verify preferences are preserved when resume is cleared
    assert del_prof["name"] == "Tanuj Singh"
    assert del_prof["role"] == "Senior React Developer"
    assert del_prof["expected_ctc_lpa"] == "24-32 LPA"


def test_settings_providers():
    resp = client.get("/api/settings/providers")
    assert resp.status_code == 200
    providers = resp.json()["providers"]
    provider_ids = [p["id"] for p in providers]
    assert "anthropic" in provider_ids
    assert "gemini" in provider_ids
    assert "openai" in provider_ids
    assert "bedrock" not in provider_ids
    assert providers[0]["id"] == "gemini"


def test_chat_lifecycle():
    # List or create sessions
    resp = client.get("/api/chat/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) > 0
    session_id = sessions[0]["id"]

    # Send a general chat message
    resp2 = client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "Hello Career Navigator"},
    )
    assert resp2.status_code == 200
    msg = resp2.json()
    assert len(msg["content"]) > 10
    assert "career" in msg["content"].lower() or "navigation" in msg["content"].lower() or "assist" in msg["content"].lower()


def test_tracker_lifecycle():
    # Add tracker entry
    payload = {
        "job_id": "job_123",
        "company": "Canonical",
        "title": "Software Engineer",
        "location": "Remote",
        "apply_url": "https://canonical.com/careers",
        "status": "found",
    }
    resp = client.post("/api/tracker", json=payload)
    assert resp.status_code == 200
    entry_id = resp.json()["id"]

    # Update status to applied
    resp2 = client.patch(f"/api/tracker/{entry_id}", json={"status": "applied"})
    assert resp2.status_code == 200
    assert resp2.json()["new_status"] == "applied"


def test_automate_config():
    resp = client.get("/api/automate/config")
    assert resp.status_code == 200
    cfg = resp.json()
    assert "schedule_time" in cfg
