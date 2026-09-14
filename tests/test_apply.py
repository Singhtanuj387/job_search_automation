"""
Unit and Integration Tests for LinkedIn Auto-Apply Feature.
Tests cover:
1. Resume field extraction (ResumeExtractor)
2. Database operations for credentials, apply sessions, and status tracking
3. LLM intent classification for /job-skill apply
4. Apply API endpoints (/api/apply/credentials, /api/apply/sessions)
5. Chat route integration for apply intent
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from web.backend.app import app
from web.backend.db import AppDatabase
from web.backend.resume_extractor import ResumeExtractor
from web.backend.llm_service import LLMService

client = TestClient(app)
db = AppDatabase()


# ────────────── 1. Resume Extractor Tests ──────────────

def test_resume_extractor_all_fields():
    sample_resume = """
    Jane Smith
    Email: jane.smith@techcorp.io
    Phone: +1-555-234-5678
    Location: San Francisco, CA
    LinkedIn: https://www.linkedin.com/in/janesmith-dev
    GitHub: https://github.com/janesmith
    Portfolio: https://janesmith.dev

    SUMMARY
    Senior Software Engineer with 7+ years of experience in distributed systems,
    cloud architecture, and full-stack development.

    EXPERIENCE
    Lead Engineer at CloudScale Inc (2020 - Present)
    - Architected scalable microservices using Python, FastAPI, and Go.
    - Led a team of 8 engineers.

    Software Engineer at TechFlow (2017 - 2020)
    - Developed REST APIs and React frontends.

    EDUCATION
    Master of Science in Computer Science
    Stanford University, 2017
    Bachelor of Technology in Information Technology
    MIT, 2015

    SKILLS
    Python, FastAPI, TypeScript, React, Docker, Kubernetes, AWS, PostgreSQL, Redis, CI/CD
    """

    profile = {
        "full_name": "Jane Smith",
        "phone": "+1-555-234-5678",
        "email": "jane.smith@techcorp.io",
        "linkedin_url": "https://www.linkedin.com/in/janesmith-dev",
    }

    extracted = ResumeExtractor.extract_all(sample_resume, profile)

    assert extracted["first_name"] == "Jane"
    assert extracted["last_name"] == "Smith"
    assert extracted["email"] == "jane.smith@techcorp.io"
    assert "555-234-5678" in extracted["phone"]
    assert extracted["experience_years"] >= 7
    assert "Python" in extracted["skills"]
    assert "React" in extracted["skills"]
    assert "Docker" in extracted["skills"]
    assert "janesmith-dev" in extracted["linkedin_url"]
    assert "janesmith" in extracted["github_url"]
    assert len(extracted["education"]) >= 1


def test_resume_extractor_fallback():
    extracted = ResumeExtractor.extract_all("", {})
    assert extracted["first_name"] == ""
    assert extracted["last_name"] == ""
    assert extracted["email"] == ""
    assert extracted["skills"] == []


# ────────────── 2. Database Credentials & Session Tests ──────────────

def test_linkedin_credentials_db():
    prev_creds = db.get_linkedin_credentials()
    try:
        # Save credentials
        save_res = db.save_linkedin_credentials("testuser@linkedin-test.com", "SecretPass123!")
        assert save_res["status"] == "saved"
        assert "•" in save_res["masked_email"] or ".com" in save_res["masked_email"]

        # Get credentials
        creds = db.get_linkedin_credentials()
        assert creds is not None
        assert creds["email"] == "testuser@linkedin-test.com"
        assert creds["password"] == "SecretPass123!"
        assert creds["masked_email"] == save_res["masked_email"]

        # Delete credentials
        deleted = db.delete_linkedin_credentials()
        assert deleted is True

        # Confirm deleted
        assert db.get_linkedin_credentials() is None
    finally:
        if prev_creds and prev_creds.get("email") and prev_creds.get("password"):
            db.save_linkedin_credentials(prev_creds["email"], prev_creds["password"])


def test_apply_sessions_db():
    session_id = f"test_session_{uuid.uuid4().hex[:8]}"

    # Create session
    db.create_apply_session(
        session_id=session_id,
        platform="linkedin",
        max_applies=10,
        total_jobs=5,
    )

    # Fetch session
    sess = db.get_apply_session(session_id)
    assert sess is not None
    assert sess["session_id"] == session_id
    assert sess["platform"] == "linkedin"
    assert sess["status"] == "running"
    assert sess["max_applies"] == 10
    assert sess["total_jobs"] == 5

    # Update session
    db.update_apply_session(
        session_id,
        status="completed",
        applied_count=3,
        skipped_count=1,
        error_count=1,
        pending_question={"question": "What is your notice period?"},
    )

    sess_updated = db.get_apply_session(session_id)
    assert sess_updated["status"] == "completed"
    assert sess_updated["applied_count"] == 3
    assert sess_updated["skipped_count"] == 1
    assert sess_updated["error_count"] == 1
    assert "notice period" in sess_updated["pending_question"]["question"]

    # List sessions
    all_sessions = db.list_apply_sessions(platform="linkedin")
    assert any(s["session_id"] == session_id for s in all_sessions)


def test_get_linkedin_opportunities_for_apply():
    uid = uuid.uuid4().hex[:6]
    test_jobs = [
        {
            "company": f"LinkedIn Co {uid}",
            "title": "Backend Python Dev",
            "location": "Remote",
            "source": "linkedin",
            "apply_url": f"https://www.linkedin.com/jobs/view/{uid}001",
            "fitness_score": 88,
        },
        {
            "company": f"Other Co {uid}",
            "title": "Backend Python Dev",
            "location": "Remote",
            "source": "naukri",
            "apply_url": f"https://www.naukri.com/job/{uid}002",
            "fitness_score": 85,
        }
    ]
    db.upsert_opportunities(test_jobs)

    linkedin_jobs = db.get_linkedin_opportunities_for_apply(max_jobs=10)
    assert len(linkedin_jobs) >= 1
    assert all(j["source"].lower() == "linkedin" for j in linkedin_jobs)


# ────────────── 3. Intent Classification Tests ──────────────

def test_llm_classify_apply_intent():
    r1 = LLMService.classify_intent("/job-skill apply linkedin")
    assert r1.get("intent") == "apply_platform"
    assert r1.get("platform") == "linkedin"

    r2 = LLMService.classify_intent("/job-skill apply")
    assert r2.get("intent") == "apply_platform"
    assert r2.get("platform") == "linkedin"

    r3 = LLMService.classify_intent("apply to all linkedin jobs")
    assert r3.get("intent") == "apply_platform"
    assert r3.get("platform") == "linkedin"


# ────────────── 4. Apply API Endpoints Tests ──────────────

def test_api_apply_credentials_flow():
    # Backup existing credentials if any
    prev_creds = db.get_linkedin_credentials()
    try:
        # Delete first
        client.delete("/api/apply/credentials")

        # Check initially empty
        res = client.get("/api/apply/credentials")
        assert res.status_code == 200
        assert res.json()["has_credentials"] is False

        # Save credentials
        res = client.post(
            "/api/apply/credentials",
            json={"email": "applyuser@example.com", "password": "SecurePassword123"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "saved"
        assert "masked_email" in data

        # Verify saved status (password should NEVER be returned)
        res = client.get("/api/apply/credentials")
        assert res.status_code == 200
        info = res.json()
        assert info["has_credentials"] is True
        assert "password" not in info
        assert "•" in info["masked_email"] or ".com" in info["masked_email"]

        # Delete credentials
        res = client.delete("/api/apply/credentials")
        assert res.status_code == 200
        assert res.json()["deleted"] is True
    finally:
        # Restore previous credentials if any
        if prev_creds and prev_creds.get("email") and prev_creds.get("password"):
            db.save_linkedin_credentials(prev_creds["email"], prev_creds["password"])


def test_api_apply_sessions():
    res = client.get("/api/apply/sessions")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


# ────────────── 5. Chat Route Apply Platform Tests ──────────────

def test_chat_apply_intent_response():
    prev_creds = db.get_linkedin_credentials()
    try:
        # Save a credential first so it doesn't fail at credential check
        db.save_linkedin_credentials("testchat@example.com", "ChatPass123!")

        s_resp = client.get("/api/chat/sessions")
        sessions = s_resp.json()
        if sessions:
            session_id = sessions[0]["id"]
        else:
            c_resp = client.post("/api/chat/sessions")
            session_id = c_resp.json()["id"]

        res = client.post(
            f"/api/chat/sessions/{session_id}/message",
            json={"content": "/job-skill apply linkedin"}
        )
        assert res.status_code == 200
        data = res.json()
        content_text = data.get("content", "").lower()
        assert "linkedin" in content_text or "apply" in content_text
        metadata = data.get("metadata", {})
        assert metadata.get("intent") == "apply_platform"
        assert metadata.get("platform") == "linkedin"
    finally:
        # Clean up or restore
        db.delete_linkedin_credentials()
        if prev_creds and prev_creds.get("email") and prev_creds.get("password"):
            db.save_linkedin_credentials(prev_creds["email"], prev_creds["password"])


# ────────────── 6. Indeed Auto-Apply Feature Tests ──────────────

def test_indeed_credentials_db():
    prev_creds = db.get_indeed_credentials()
    try:
        save_res = db.save_indeed_credentials("indeeduser@example.com", "IndeedPass123!")
        assert save_res["status"] == "saved"
        assert "•" in save_res["masked_email"] or ".com" in save_res["masked_email"]

        creds = db.get_indeed_credentials()
        assert creds is not None
        assert creds["email"] == "indeeduser@example.com"
        assert creds["password"] == "IndeedPass123!"

        deleted = db.delete_indeed_credentials()
        assert deleted is True
        assert db.get_indeed_credentials() is None
    finally:
        if prev_creds and prev_creds.get("email") and prev_creds.get("password"):
            db.save_indeed_credentials(prev_creds["email"], prev_creds["password"])


def test_indeed_opportunities_query():
    # Verify query returns list of opportunities without error
    jobs = db.get_indeed_opportunities_for_apply(max_jobs=10)
    assert isinstance(jobs, list)


def test_api_indeed_credentials_flow():
    prev_creds = db.get_indeed_credentials()
    try:
        # Delete first
        client.delete("/api/apply/indeed/credentials")

        # Check empty
        res = client.get("/api/apply/indeed/credentials")
        assert res.status_code == 200
        assert res.json()["has_credentials"] is False

        # Save credentials
        res = client.post(
            "/api/apply/indeed/credentials",
            json={"email": "indeedtest@example.com", "password": "IndeedSecurePass789!"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "saved"
        assert "masked_email" in data

        # Check saved without leaking password
        res = client.get("/api/apply/indeed/credentials")
        assert res.status_code == 200
        info = res.json()
        assert info["has_credentials"] is True
        assert "password" not in info
        assert "•" in info["masked_email"] or ".com" in info["masked_email"]

        # Delete credentials
        res = client.delete("/api/apply/indeed/credentials")
        assert res.status_code == 200
        assert res.json()["deleted"] is True
    finally:
        if prev_creds and prev_creds.get("email"):
            db.save_indeed_credentials(prev_creds["email"], prev_creds.get("password") or "")


def test_chat_apply_indeed_intent():
    prev_creds = db.get_indeed_credentials()
    try:
        db.save_indeed_credentials("chatindeed@example.com", "ChatIndeedPass123!")

        s_resp = client.get("/api/chat/sessions")
        sessions = s_resp.json()
        if sessions:
            session_id = sessions[0]["id"]
        else:
            c_resp = client.post("/api/chat/sessions")
            session_id = c_resp.json()["id"]

        res = client.post(
            f"/api/chat/sessions/{session_id}/message",
            json={"content": "/job-skill apply indeed"}
        )
        assert res.status_code == 200
        data = res.json()
        content_text = data.get("content", "").lower()
        assert "indeed" in content_text
        metadata = data.get("metadata", {})
        assert metadata.get("intent") == "apply_platform"
        assert metadata.get("platform") == "indeed"
    finally:
        db.delete_indeed_credentials()
        if prev_creds and prev_creds.get("email"):
            db.save_indeed_credentials(prev_creds["email"], prev_creds.get("password") or "")


def test_chat_indeed_login_command():
    prev_creds = db.get_indeed_credentials()
    try:
        s_resp = client.get("/api/chat/sessions")
        sessions = s_resp.json()
        session_id = sessions[0]["id"] if sessions else client.post("/api/chat/sessions").json()["id"]

        res = client.post(
            f"/api/chat/sessions/{session_id}/message",
            json={"content": "/indeed-login myemail@indeedtest.com MySecretPassword123"}
        )
        assert res.status_code == 200
        data = res.json()
        # Verify password is NEVER in the response
        assert "MySecretPassword123" not in data.get("content", "")
        assert "Indeed Credentials Saved" in data.get("content", "")

        # Verify saved in DB
        creds = db.get_indeed_credentials()
        assert creds is not None
        assert creds["email"] == "myemail@indeedtest.com"
        assert creds["password"] == "MySecretPassword123"
    finally:
        db.delete_indeed_credentials()
        if prev_creds and prev_creds.get("email"):
            db.save_indeed_credentials(prev_creds["email"], prev_creds.get("password") or "")


# ────────────── 6. LinkedIn Question Answering Tests ──────────────

def test_linkedin_guess_radio_answer_no_default_rules():
    """Verify that _guess_radio_answer does not make default assumptions
    for experience, domain, previous employment, or application history."""
    from web.backend.linkedin_apply_agent import LinkedInApplyAgent
    agent = LinkedInApplyAgent(credentials={"email": "test@example.com"}, resume_data={}, profile={})

    # Experience / domain questions MUST return None (ask user)
    assert agent._guess_radio_answer("Do you have experience in Product Based Companies ?") is None
    assert agent._guess_radio_answer("Do you have experience with Python and Go?") is None
    assert agent._guess_radio_answer("Do you have prior experience in Healthcare domain?") is None
    assert agent._guess_radio_answer("Do you have knowledge of microservices architecture?") is None

    # Employment & application history questions MUST return None (ask user)
    assert agent._guess_radio_answer("Have you previously applied to this company?") is None
    assert agent._guess_radio_answer("Have you been previously employed by Truemeds?") is None
    assert agent._guess_radio_answer("Are you currently employed?") is None

    # Legal authorization can still return True
    assert agent._guess_radio_answer("Are you legally authorized to work in India?") is True

    # Sponsorship returns None (ask user)
    assert agent._guess_radio_answer("Will you require sponsorship for employment?") is None


@pytest.mark.anyio
async def test_linkedin_fill_fields_asks_user_for_product_based_radio():
    """Verify that when a LinkedIn Easy Apply form has 'Do you have experience in Product Based Companies ?',
    the agent asks the user in chat and clicks the user's selected answer."""
    from unittest.mock import AsyncMock, MagicMock
    from web.backend.linkedin_apply_agent import LinkedInApplyAgent

    mock_ask_user = AsyncMock(return_value="Yes")
    agent = LinkedInApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
        ask_user_callback=mock_ask_user
    )

    events = []
    agent._emit = lambda ev: events.append(ev)

    mock_scope = MagicMock()
    # No inputs, textareas, selects
    mock_inputs = MagicMock()
    mock_inputs.count = AsyncMock(return_value=0)
    mock_textareas = MagicMock()
    mock_textareas.count = AsyncMock(return_value=0)
    mock_selects = MagicMock()
    mock_selects.count = AsyncMock(return_value=0)

    # One fieldset with role="radiogroup" for "Do you have experience in Product Based Companies ?"
    mock_fs = MagicMock()
    mock_legend = MagicMock()
    mock_legend.count = AsyncMock(return_value=0)
    mock_legend.first = mock_legend

    mock_role_radio_q = MagicMock()
    mock_role_radio_q.count = AsyncMock(return_value=1)
    mock_role_radio_q.get_attribute = AsyncMock(return_value="Do you have experience in Product Based Companies ?")
    mock_role_radio_q.first = mock_role_radio_q

    mock_checked = MagicMock()
    mock_checked.count = AsyncMock(return_value=0)

    # Radio option buttons: Yes and No
    opt_yes = MagicMock(name="opt_yes")
    opt_yes.text_content = AsyncMock(return_value="Yes")
    opt_no = MagicMock(name="opt_no")
    opt_no.text_content = AsyncMock(return_value="No")

    mock_options = MagicMock()
    mock_options.count = AsyncMock(return_value=2)
    mock_options.nth = MagicMock(side_effect=lambda idx: opt_yes if idx == 0 else opt_no)

    # Target div clicked
    mock_target_div = MagicMock(name="target_div")
    mock_target_div.count = AsyncMock(return_value=1)
    mock_target_div.click = AsyncMock()
    mock_target_div.first = mock_target_div

    def _fs_locator_side_effect(selector):
        if "legend" in selector:
            return mock_legend
        if 'div[role="radio"][aria-label]' in selector:
            return mock_role_radio_q
        if 'input[type="radio"]:checked' in selector:
            return mock_checked
        if 'div[role="radio"], label' in selector:
            return mock_options
        if 'div[role="radio"]' in selector:
            return mock_target_div
        m = MagicMock()
        m.count = AsyncMock(return_value=0)
        m.first = m
        return m

    mock_fs.locator = MagicMock(side_effect=_fs_locator_side_effect)
    mock_fs.get_attribute = AsyncMock(return_value=None)

    mock_fieldsets = MagicMock()
    mock_fieldsets.count = AsyncMock(return_value=1)
    mock_fieldsets.nth = MagicMock(return_value=mock_fs)

    def _scope_locator(selector):
        if "input" in selector:
            return mock_inputs
        if "textarea" in selector:
            return mock_textareas
        if "select" in selector:
            return mock_selects
        if "fieldset" in selector or "radiogroup" in selector:
            return mock_fieldsets
        m = MagicMock()
        m.count = AsyncMock(return_value=0)
        return m

    mock_scope.locator = MagicMock(side_effect=_scope_locator)

    await agent._fill_visible_fields("Truemeds", "Frontend Engineer", form_modal=mock_scope)

    # Verify ask_user was called for the product based companies question
    mock_ask_user.assert_called_once()
    args = mock_ask_user.call_args[0]
    assert "Do you have experience in Product Based Companies ?" in args[1]

    # Verify target div was clicked
    mock_target_div.click.assert_called_once()

    # Verify needs_input event was emitted
    assert any(e.get("step") == "needs_input" for e in events)


@pytest.mark.anyio
async def test_linkedin_apply_page_company_mismatch_aborts():
    """Verify that if LinkedIn page displays an employer different from the target job company,
    the agent skips applying to prevent applying to the wrong company."""
    from unittest.mock import AsyncMock, MagicMock
    from web.backend.linkedin_apply_agent import LinkedInApplyAgent, ApplyStatus

    agent = LinkedInApplyAgent(
        credentials={"email": "test@example.com", "password": "pass"},
        resume_data={},
        profile={},
    )
    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.url = "https://www.linkedin.com/jobs/view/123456789"
    mock_page.wait_for_selector = AsyncMock()

    # Mock company element on the page returning "Zomato"
    mock_comp_loc = MagicMock()
    mock_comp_loc.count = AsyncMock(return_value=1)
    mock_comp_loc.text_content = AsyncMock(return_value="Zomato")
    mock_comp_loc.first = mock_comp_loc

    def _locator_side_effect(selector):
        if "unified-top-card__company-name" in selector or "topcard__org-name-link" in selector:
            return mock_comp_loc
        m = MagicMock()
        m.count = AsyncMock(return_value=0)
        m.first = m
        return m

    mock_page.locator = MagicMock(side_effect=_locator_side_effect)
    agent.page = mock_page

    job = {
        "id": 101,
        "company": "Swiggy",
        "title": "Backend Engineer",
        "apply_url": "https://www.linkedin.com/jobs/view/123456789",
    }

    res = await agent.apply_to_job(job)
    assert res.status == ApplyStatus.SKIPPED
    assert "does not match" in res.message
    assert "Zomato" in res.message
    assert "Swiggy" in res.message



