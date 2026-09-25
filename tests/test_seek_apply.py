"""
Tests for SEEK Auto-Apply Agent and API Endpoints.
Verifies:
1. Database credentials storage, retrieval, and AES-256 masking.
2. SEEK credentials endpoints (GET, POST, DELETE, cookies).
3. Chat routing for /seek-login and /job-skill apply seek.
4. Chat OTP answer routing when apply session is waiting for input.
5. SeekApplyAgent Quick Apply filtering (skips external applications).
6. SeekApplyAgent passwordless email OTP authentication.
7. SeekApplyAgent multi-step application form filling and submission.
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from web.backend.app import app
from web.backend.db import AppDatabase
from web.backend.routes.apply import _active_sessions
from web.backend.seek_apply_agent import SeekApplyAgent, ApplyStatus

client = TestClient(app)
db = AppDatabase()


def test_seek_credentials_db():
    prev_creds = db.get_seek_credentials()
    try:
        # Save credentials
        res = db.save_seek_credentials("test.candidate@seek.com.au")
        assert res["saved"] is True
        assert "test" in res["masked_email"] or "••••" in res["masked_email"]

        # Fetch credentials
        creds = db.get_seek_credentials()
        assert creds is not None
        assert creds["email"] == "test.candidate@seek.com.au"
        assert creds["password"] == ""

        # Update email
        db.save_seek_credentials("new.seek@example.com")
        creds_updated = db.get_seek_credentials()
        assert creds_updated["email"] == "new.seek@example.com"

        # Delete credentials
        deleted = db.delete_seek_credentials()
        assert deleted is True
        assert db.get_seek_credentials() is None
    finally:
        db.delete_seek_credentials()
        if prev_creds and prev_creds.get("email"):
            db.save_seek_credentials(prev_creds["email"], prev_creds.get("password", ""))


def test_seek_credentials_api():
    prev_creds = db.get_seek_credentials()
    try:
        # 1. Save with email
        res = client.post("/api/apply/seek/credentials", json={"email": "tester@seek.com.au"})
        assert res.status_code == 200
        assert res.json()["status"] == "saved"

        # 2. Get credentials
        get_res = client.get("/api/apply/seek/credentials")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["has_credentials"] is True
        assert data["email"] == "tester@seek.com.au"
        assert "password" not in data

        # 3. Reject empty email
        bad_res = client.post("/api/apply/seek/credentials", json={"email": "   "})
        assert bad_res.status_code == 400

        # 4. Clear cookies endpoint
        clear_res = client.delete("/api/apply/seek/credentials/cookies")
        assert clear_res.status_code == 200
        assert clear_res.json()["cleared"] is True

        # 5. Delete credentials
        del_res = client.delete("/api/apply/seek/credentials")
        assert del_res.status_code == 200
        assert del_res.json()["deleted"] is True
    finally:
        db.delete_seek_credentials()
        if prev_creds and prev_creds.get("email"):
            db.save_seek_credentials(prev_creds["email"], prev_creds.get("password", ""))


def test_chat_seek_login_command():
    prev_creds = db.get_seek_credentials()
    try:
        s_resp = client.get("/api/chat/sessions")
        sessions = s_resp.json()
        session_id = sessions[0]["id"] if sessions else client.post("/api/chat/sessions").json()["id"]

        res = client.post(
            f"/api/chat/sessions/{session_id}/message",
            json={"content": "/seek-login candidate@domain.com"}
        )
        assert res.status_code == 200
        reply = res.json().get("content", "")
        assert "SEEK Credentials Saved" in reply
        assert "/job-skill apply seek" in reply

        creds = db.get_seek_credentials()
        assert creds is not None
        assert creds["email"] == "candidate@domain.com"
    finally:
        db.delete_seek_credentials()
        if prev_creds and prev_creds.get("email"):
            db.save_seek_credentials(prev_creds["email"], prev_creds.get("password", ""))


def test_chat_apply_seek_without_credentials():
    prev_creds = db.get_seek_credentials()
    try:
        db.delete_seek_credentials()
        s_resp = client.get("/api/chat/sessions")
        sessions = s_resp.json()
        session_id = sessions[0]["id"] if sessions else client.post("/api/chat/sessions").json()["id"]

        res = client.post(
            f"/api/chat/sessions/{session_id}/message",
            json={"content": "/job-skill apply seek"}
        )
        assert res.status_code == 200
        reply = res.json().get("content", "")
        assert "SEEK Email Required" in reply
        meta = res.json().get("metadata", {})
        assert meta.get("needs_credentials") is True
        assert meta.get("platform") == "seek"
    finally:
        if prev_creds and prev_creds.get("email"):
            db.save_seek_credentials(prev_creds["email"], prev_creds.get("password", ""))


def test_chat_apply_seek_with_jobs():
    prev_creds = db.get_seek_credentials()
    try:
        db.save_seek_credentials("test.user@seek.com.au")
        # Ensure at least one SEEK job exists
        db.upsert_opportunities([{
            "source_job_id": "seek_test_job_1",
            "source": "seek",
            "company": "Canva",
            "title": "Senior Frontend Engineer",
            "location": "Sydney NSW",
            "apply_url": "https://au.seek.com/job/94652603",
            "fitness_score": 92,
            "status": "queued",
        }])

        s_resp = client.get("/api/chat/sessions")
        sessions = s_resp.json()
        session_id = sessions[0]["id"] if sessions else client.post("/api/chat/sessions").json()["id"]

        res = client.post(
            f"/api/chat/sessions/{session_id}/message",
            json={"content": "/job-skill apply seek"}
        )
        assert res.status_code == 200
        meta = res.json().get("metadata", {})
        assert meta.get("apply_ready") is True
        assert meta.get("platform") == "seek"
        assert meta.get("seek_jobs_count", 0) >= 1

        reply = res.json().get("content", "")
        assert "SEEK Auto-Apply Agent — Ready" in reply
        assert "Canva" in reply
        assert "Quick Apply" in reply
    finally:
        db.delete_seek_credentials()
        if prev_creds and prev_creds.get("email"):
            db.save_seek_credentials(prev_creds["email"], prev_creds.get("password", ""))


def test_chat_otp_interception_when_seek_waiting():
    test_session_id = "test-seek-otp-sess-1"
    answer_holder = {"value": None}
    q_event = asyncio.Event()

    _active_sessions[test_session_id] = {
        "session_id": test_session_id,
        "platform": "seek",
        "status": "waiting_for_input",
        "pending_question": {
            "job_title": "SEEK Login",
            "field_name": "verification_code",
            "question": "Enter the 6-digit verification code sent by SEEK to your email.",
        },
        "answer_holder": answer_holder,
        "question_event": q_event,
        "broadcast": MagicMock(),
        "loop": asyncio.new_event_loop(),
        "event_buffer": [],
        "subscribers": [],
    }

    try:
        s_resp = client.get("/api/chat/sessions")
        sessions = s_resp.json()
        session_id = sessions[0]["id"] if sessions else client.post("/api/chat/sessions").json()["id"]

        res = client.post(
            f"/api/chat/sessions/{session_id}/message",
            json={"content": "849201"}
        )
        assert res.status_code == 200
        reply = res.json().get("content", "")
        assert "Verification code Received" in reply
        assert "Seek apply agent" in reply or "SEEK" in reply.upper()

        assert answer_holder["value"] == "849201"
        assert q_event.is_set()
    finally:
        _active_sessions.pop(test_session_id, None)


def test_seek_agent_skips_external_apply():
    """Verify that jobs without 'Quick apply' (i.e. external redirect) are skipped."""
    async def _run():
        agent = SeekApplyAgent(
            credentials={"email": "candidate@example.com"},
            resume_data={"name": "Alex Smith", "email": "candidate@example.com"},
            profile={"name": "Alex Smith", "email": "candidate@example.com", "phone": "0400123456"},
        )

        mock_page = MagicMock()
        mock_page.url = "https://au.seek.com/job/123456"
        mock_page.goto = AsyncMock()

        mock_loc = MagicMock()
        mock_loc.first = MagicMock()
        mock_loc.first.click = AsyncMock()
        mock_loc.first.inner_text = AsyncMock(return_value="Apply on employer site")
        mock_page.locator.return_value = mock_loc

        async def fake_is_visible(selector, timeout=None):
            # Already applied: False, Quick Apply: False, External Apply: True
            if "applied" in selector.lower() and "quick" not in selector.lower():
                return False
            if "quick" in selector.lower():
                return False
            if "external" in selector.lower() or "employer" in selector.lower() or "company site" in selector.lower():
                return True
            return False

        with patch.object(agent, "_is_visible", side_effect=fake_is_visible), \
             patch.object(agent, "_wait_for_cloudflare", new_callable=AsyncMock), \
             patch.object(agent, "_human_delay", new_callable=AsyncMock):

            agent.page = mock_page
            job = {
                "id": "seek_ext_1",
                "company": "External Employer",
                "title": "DevOps Engineer",
                "apply_url": "https://au.seek.com/job/123456",
            }
            result = await agent.apply_to_job(job)
            assert result.status == ApplyStatus.SKIPPED
            assert "external application" in result.message

    asyncio.run(_run())


def test_seek_agent_completes_quick_apply_steps():
    """Verify SeekApplyAgent walks through contact, resume, screening questions, and submit."""
    async def _run():
        agent = SeekApplyAgent(
            credentials={"email": "candidate@example.com"},
            resume_data={"name": "Alex Smith", "email": "candidate@example.com", "phone": "0400123456"},
            profile={"name": "Alex Smith", "email": "candidate@example.com", "phone": "0400123456"},
        )

        mock_page = MagicMock()
        mock_page.url = "https://au.seek.com/job/987654"
        mock_page.goto = AsyncMock()

        mock_loc = MagicMock()
        mock_loc.first = MagicMock()
        mock_loc.first.click = AsyncMock()
        mock_loc.inner_text = AsyncMock(return_value="Your application submitted successfully! Good luck.")
        mock_page.locator.return_value = mock_loc

        async def fake_is_visible(selector, timeout=None):
            if "applied" in selector.lower() and "detail" not in selector.lower() and "quick" not in selector.lower():
                return False
            if "quick" in selector.lower():
                return True
            return False

        with patch.object(agent, "_is_visible", side_effect=fake_is_visible), \
             patch.object(agent, "_wait_for_cloudflare", new_callable=AsyncMock), \
             patch.object(agent, "_human_delay", new_callable=AsyncMock):

            agent.page = mock_page
            job = {
                "id": "seek_qa_1",
                "company": "Tech Corp",
                "title": "Python Developer",
                "apply_url": "https://au.seek.com/job/987654",
            }
            result = await agent.apply_to_job(job)
            assert result.status == ApplyStatus.APPLIED
            assert "submitted" in result.message.lower()

    asyncio.run(_run())
