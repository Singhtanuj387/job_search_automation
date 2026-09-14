"""
Unit tests for passwordless Indeed authentication via 'Sign in with a code instead'.
Verifies:
1. Email-only credential saving & retrieval via API and DB.
2. /indeed-login command with email only.
3. Chat OTP answer routing when apply session is waiting for input.
4. IndeedApplyAgent login flow with 'Sign in with a code' and ask_user OTP callback.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from web.backend.app import app
from web.backend.db import AppDatabase
from web.backend.routes.apply import _active_sessions
from web.backend.indeed_apply_agent import IndeedApplyAgent

client = TestClient(app)
db = AppDatabase()


def test_indeed_credentials_email_only_db():
    prev_creds = db.get_indeed_credentials()
    try:
        # Save email only (empty password)
        res = db.save_indeed_credentials("singhtanuj387@gmail.com")
        assert res["saved"] is True
        assert "singhtanuj387" in res["masked_email"] or "••••" in res["masked_email"]

        # Fetch credentials
        creds = db.get_indeed_credentials()
        assert creds is not None
        assert creds["email"] == "singhtanuj387@gmail.com"
        assert creds["password"] == ""

        # Update email
        db.save_indeed_credentials("updated.indeed@gmail.com")
        creds_updated = db.get_indeed_credentials()
        assert creds_updated["email"] == "updated.indeed@gmail.com"
    finally:
        db.delete_indeed_credentials()
        if prev_creds and prev_creds.get("email"):
            db.save_indeed_credentials(prev_creds["email"], prev_creds.get("password", ""))


def test_indeed_credentials_api_email_only():
    prev_creds = db.get_indeed_credentials()
    try:
        # 1. Save with only email key
        res = client.post("/api/apply/indeed/credentials", json={"email": "singhtanuj387@gmail.com"})
        assert res.status_code == 200
        assert res.json()["status"] == "saved"

        # 2. Get credentials
        get_res = client.get("/api/apply/indeed/credentials")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["has_credentials"] is True
        assert data["email"] == "singhtanuj387@gmail.com"
        assert "password" not in data

        # 3. Reject empty email
        bad_res = client.post("/api/apply/indeed/credentials", json={"email": "   "})
        assert bad_res.status_code == 400
    finally:
        db.delete_indeed_credentials()
        if prev_creds and prev_creds.get("email"):
            db.save_indeed_credentials(prev_creds["email"], prev_creds.get("password", ""))


def test_chat_indeed_login_email_only():
    prev_creds = db.get_indeed_credentials()
    try:
        s_resp = client.get("/api/chat/sessions")
        sessions = s_resp.json()
        session_id = sessions[0]["id"] if sessions else client.post("/api/chat/sessions").json()["id"]

        res = client.post(
            f"/api/chat/sessions/{session_id}/message",
            json={"content": "/indeed-login singhtanuj387@gmail.com"}
        )
        assert res.status_code == 200
        reply = res.json().get("content", "")
        assert "Indeed Credentials Saved" in reply
        assert "Sign in with a code" in reply

        creds = db.get_indeed_credentials()
        assert creds is not None
        assert creds["email"] == "singhtanuj387@gmail.com"
    finally:
        db.delete_indeed_credentials()
        if prev_creds and prev_creds.get("email"):
            db.save_indeed_credentials(prev_creds["email"], prev_creds.get("password", ""))


def test_chat_otp_interception_when_session_waiting():
    test_session_id = "test-apply-otp-sess-1"
    answer_holder = {"value": None}
    q_event = asyncio.Event()

    # Register a simulated apply session waiting for OTP
    _active_sessions[test_session_id] = {
        "status": "waiting_for_input",
        "pending_question": {
            "job_title": "Indeed Authentication",
            "field_name": "otp_code",
            "question": "Indeed sent a verification code to user@gmail.com. Please enter the 6-digit code:",
        },
        "answer_holder": answer_holder,
        "question_event": q_event,
        "broadcast": MagicMock(),
        "loop": asyncio.new_event_loop(),
    }

    try:
        s_resp = client.get("/api/chat/sessions")
        sessions = s_resp.json()
        session_id = sessions[0]["id"] if sessions else client.post("/api/chat/sessions").json()["id"]

        # User enters 6-digit OTP in chat
        res = client.post(
            f"/api/chat/sessions/{session_id}/message",
            json={"content": "849201"}
        )
        assert res.status_code == 200
        reply = res.json().get("content", "")
        assert "Verification code Received" in reply or "Received" in reply

        # Check answer was delivered to the apply session
        assert answer_holder["value"] == "849201"
        assert q_event.is_set()
    finally:
        _active_sessions.pop(test_session_id, None)


@pytest.mark.anyio
async def test_indeed_agent_login_flow_with_code_and_ask_user():
    """
    Test that IndeedApplyAgent.login():
    1. Types email.
    2. Clicks 'Sign in with a code instead'.
    3. Triggers ask_user callback to obtain 6-digit OTP.
    4. Enters OTP and completes login.
    """
    mock_page = MagicMock()
    mock_context = MagicMock()
    mock_page.url = "https://secure.indeed.com/auth"
    mock_page.goto = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[{"name": "CTK", "value": "12345"}])
    mock_context.add_cookies = AsyncMock()

    # Email input locator
    mock_email_input = MagicMock()
    mock_email_input.is_visible = AsyncMock(return_value=True)
    mock_email_input.fill = AsyncMock()
    mock_email_input.click = AsyncMock()

    # Continue button locator
    mock_continue_btn = MagicMock()
    mock_continue_btn.is_visible = AsyncMock(return_value=True)
    mock_continue_btn.click = AsyncMock()

    # Code sign-in link
    mock_code_link = MagicMock()
    mock_code_link.is_visible = AsyncMock(return_value=True)
    mock_code_link.click = AsyncMock()

    # OTP code input
    mock_otp_input = MagicMock()
    mock_otp_input.is_visible = AsyncMock(return_value=True)
    mock_otp_input.fill = AsyncMock()
    mock_otp_input.click = AsyncMock()

    # Verify button
    mock_verify_btn = MagicMock()
    mock_verify_btn.is_visible = AsyncMock(return_value=True)
    mock_verify_btn.click = AsyncMock()

    def locator_side_effect(selector):
        loc = MagicMock()
        loc.first = loc
        loc.fill = AsyncMock()
        loc.click = AsyncMock()
        loc.is_visible = AsyncMock(return_value=False)
        loc.all = AsyncMock(return_value=[])
        if "button" in selector and ("submit" in selector or "Continue" in selector):
            mock_continue_btn.first = mock_continue_btn
            return mock_continue_btn
        elif "input" in selector or "email" in selector or "ifl-InputFormField-3" in selector:
            mock_email_input.first = mock_email_input
            return mock_email_input
        elif "Sign in with a code" in selector or "code instead" in selector:
            mock_code_link.first = mock_code_link
            return mock_code_link
        elif "verificationCode" in selector or "autocomplete" in selector or "ifl-InputFormField-6" in selector:
            mock_otp_input.first = mock_otp_input
            return mock_otp_input
        elif "Verify" in selector or "submit" in selector or "Sign in" in selector:
            mock_verify_btn.first = mock_verify_btn
            return mock_verify_btn
        return loc

    mock_page.locator.side_effect = locator_side_effect

    # Set up ask_user callback
    ask_user_called = False
    async def mock_ask_user(job_title, field_name, question):
        nonlocal ask_user_called
        ask_user_called = True
        assert field_name == "otp_code"
        assert "verification code" in question.lower()
        # After ask_user is answered, URL transitions out of auth
        mock_page.url = "https://myjobs.indeed.com"
        return "123456"

    agent = IndeedApplyAgent(
        resume_data={"full_name": "Tanuj Singh", "email": "singhtanuj387@gmail.com"},
        profile={"role": "Software Engineer", "location": "Bangalore"},
        credentials={"email": "singhtanuj387@gmail.com"},
        ask_user_callback=mock_ask_user,
    )
    agent.page = mock_page
    agent.context = mock_context

    async def mock_is_visible(target, timeout=1500):
        target_str = str(target)
        if ("auth-page-google-otp-fallback" in target_str or "#passcode-input" in target_str) and mock_page.url == "https://myjobs.indeed.com":
            return False
        return True

    # Run login with mocked delay
    with patch.object(agent, "_human_delay", new=AsyncMock()), \
         patch.object(agent, "_type_human", new=AsyncMock()), \
         patch.object(agent, "_is_visible", new=mock_is_visible):
        success = await agent.login()

    assert success is True
    assert ask_user_called is True
