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
        async def fake_goto(url, **kwargs):
            mock_page.url = url
            return None
        mock_page.goto = AsyncMock(side_effect=fake_goto)

        mock_loc = MagicMock()
        mock_loc.first = MagicMock()
        async def fake_click(*args, **kwargs):
            mock_page.url = "https://au.seek.com/job/987654/apply"
            return None
        mock_loc.first.click = AsyncMock(side_effect=fake_click)
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


def test_seek_agent_submit_button_avoids_header_stepper():
    """Verify that submit button locator does not get tricked by header stepper tabs and uses JS fallback."""
    async def _run():
        agent = SeekApplyAgent(
            credentials={"email": "candidate@example.com"},
            resume_data={"name": "Alex Smith", "email": "candidate@example.com"},
            profile={"name": "Alex Smith", "email": "candidate@example.com", "phone": "0400123456"},
        )

        mock_page = MagicMock()
        mock_page.url = "https://au.seek.com/job/94603335/apply/review"
        mock_page.goto = AsyncMock()

        # Mock submit button element
        mock_submit = MagicMock()
        # Simulate pointer intercept on standard click
        mock_submit.click = AsyncMock(side_effect=Exception("li intercepts pointer events"))
        mock_submit.evaluate = AsyncMock(return_value=None)
        mock_submit.scroll_into_view_if_needed = AsyncMock()

        submitted = False

        async def fake_evaluate(js):
            nonlocal submitted
            submitted = True
            return None
        mock_submit.evaluate = AsyncMock(side_effect=fake_evaluate)

        async def fake_inner_text():
            if submitted:
                return "Application submitted successfully!"
            return "Review your application"

        mock_input = MagicMock()
        mock_input.input_value = AsyncMock(return_value="0412345678")
        mock_input.click = AsyncMock()

        def fake_locator(selector):
            loc = MagicMock()
            if "submit" in selector.lower():
                loc.last = mock_submit
                loc.first = mock_submit
                loc.count = AsyncMock(return_value=1 if not submitted else 0)
                return loc
            loc.first = mock_input
            loc.last = mock_input
            loc.count = AsyncMock(return_value=0)
            loc.inner_text = fake_inner_text
            return loc

        mock_page.locator = fake_locator

        async def fake_is_visible(target, timeout=None):
            if target is mock_submit:
                return not submitted
            return False

        with patch.object(agent, "_is_visible", side_effect=fake_is_visible), \
             patch.object(agent, "_wait_for_cloudflare", new_callable=AsyncMock), \
             patch.object(agent, "_human_delay", new_callable=AsyncMock):

            agent.page = mock_page
            job = {
                "id": 94603335,
                "company": "Calleo",
                "title": "Data Scientist",
                "apply_url": "https://au.seek.com/job/94603335/apply",
            }
            result = await agent.apply_to_job(job)
            assert result.status == ApplyStatus.APPLIED
            assert "submitted" in result.message.lower()
            # Verify JS click fallback was called when pointer was intercepted
            mock_submit.evaluate.assert_called_with("el => el.click()")

    asyncio.run(_run())


def test_seek_login_detects_bot_challenge_and_aborts_without_false_success():
    """Verify that when login.seek.com triggers recaptcha/turnstile, login() returns False instead of falsely claiming success."""
    async def _run():
        agent = SeekApplyAgent(
            credentials={"email": "candidate@example.com"},
            resume_data={},
            profile={"email": "candidate@example.com"},
        )

        mock_page = MagicMock()
        mock_page.url = "https://login.seek.com/login"
        mock_page.goto = AsyncMock()

        mock_body = MagicMock()
        mock_body.inner_text = AsyncMock(return_value="Please complete the recaptcha. Email me a sign in code")

        mock_email = MagicMock()
        mock_btn = MagicMock()
        mock_btn.click = AsyncMock()

        def fake_locator(selector):
            loc = MagicMock()
            if "body" in selector:
                return mock_body
            if "email" in selector.lower():
                loc.first = mock_email
                return loc
            if "submit" in selector.lower():
                loc.first = mock_btn
                return loc
            loc.first = MagicMock()
            return loc

        mock_page.locator = fake_locator

        async def fake_is_visible(target, timeout=None):
            if target == mock_email:
                return True
            if target == mock_btn:
                return True
            return False

        with patch.object(agent, "_is_visible", side_effect=fake_is_visible), \
             patch.object(agent, "_wait_for_cloudflare", new_callable=AsyncMock), \
             patch.object(agent, "_human_delay", new_callable=AsyncMock), \
             patch.object(agent, "_type_human", new_callable=AsyncMock):

            agent.page = mock_page
            login_result = await agent.login()
            # Must be False, NOT True!
            assert login_result is False

    asyncio.run(_run())


def test_seek_apply_aborts_if_trapped_on_login_portal():
    """Verify that if clicking Quick Apply gets trapped on login portal, agent returns ERROR instead of MANUAL_REQUIRED."""
    async def _run():
        agent = SeekApplyAgent(
            credentials={"email": "candidate@example.com"},
            resume_data={},
            profile={"email": "candidate@example.com"},
        )

        mock_page = MagicMock()
        # Trapped on login portal
        mock_page.url = "https://login.seek.com/login?returnUrl=%2Fjob%2F94847894%2Fapply"
        mock_page.goto = AsyncMock()

        async def fake_is_visible(selector, timeout=None):
            if any(k in selector.lower() for k in ["applied", "company site", "employer site"]):
                return False
            if "quick" in selector.lower():
                return True
            return False

        with patch.object(agent, "_is_visible", side_effect=fake_is_visible), \
             patch.object(agent, "_wait_for_cloudflare", new_callable=AsyncMock), \
             patch.object(agent, "_human_delay", new_callable=AsyncMock), \
             patch.object(agent, "login", new_callable=AsyncMock, return_value=False):

            agent.page = mock_page
            job = {
                "id": 94847894,
                "company": "MVSI OnBoard",
                "title": "Software Developer",
                "apply_url": "https://au.seek.com/job/94847894",
            }
            result = await agent.apply_to_job(job)
            assert result.status == ApplyStatus.ERROR
            assert "authentication" in result.message.lower()

    asyncio.run(_run())


def test_seek_login_fills_seek_custom_verification_input_and_submits():
    """Verify that when SEEK displays custom VerificationInput (#field-0, input[aria-label='verification input']),
    agent asks for OTP, types the 6-digit code, triggers React synthetic events, clicks #submit-OTP,
    and succeeds once redirected to au.seek.com."""
    async def _run():
        emitted_events = []
        def track_progress(ev):
            emitted_events.append(ev)

        ask_called = []
        async def fake_ask(title, field, q):
            ask_called.append((field, q))
            return "244445"

        agent = SeekApplyAgent(
            credentials={"email": "tester@seek.com.au"},
            resume_data={},
            profile={"email": "tester@seek.com.au"},
            ask_user_callback=fake_ask,
            progress_callback=track_progress,
        )

        mock_page = MagicMock()
        mock_page.url = "https://login.seek.com/login"
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()

        # Keyboard typing
        typed_keys = []
        async def fake_type(text, delay=0):
            typed_keys.append(text)
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.type = AsyncMock(side_effect=fake_type)
        mock_page.keyboard.press = AsyncMock()

        # Body text simulation
        body_mock = MagicMock()
        body_mock.inner_text = AsyncMock(return_value="Check your email for a code. We sent a code to tester@seek.com.au")

        mock_email_input = MagicMock()
        mock_email_input.first = mock_email_input
        mock_email_input.click = AsyncMock()
        mock_code_btn = MagicMock()
        mock_code_btn.first = mock_code_btn
        mock_code_btn.click = AsyncMock()

        mock_field_0 = MagicMock()
        mock_field_0.first = mock_field_0
        mock_field_0.click = AsyncMock()

        mock_seek_input = MagicMock()
        mock_seek_input.first = mock_seek_input
        mock_seek_input.count = AsyncMock(return_value=1)
        mock_seek_input.click = AsyncMock()
        mock_seek_input.press_sequentially = AsyncMock()

        # Digit box mocks that return the expected digit via inner_text
        the_code = "244445"
        digit_box_mocks = {}
        for i in range(6):
            box = MagicMock()
            box.first = box
            box.inner_text = AsyncMock(return_value=the_code[i])
            digit_box_mocks[i] = box

        # Error containers mock (empty — no errors)
        mock_err_containers = MagicMock()
        mock_err_containers.count = AsyncMock(return_value=0)
        mock_err_containers.first = mock_err_containers

        mock_submit_otp = MagicMock()
        mock_submit_otp.first = mock_submit_otp
        async def fake_submit_click():
            mock_page.url = "https://au.seek.com/"
        mock_submit_otp.click = AsyncMock(side_effect=fake_submit_click)

        def fake_locator(selector):
            loc = MagicMock()
            loc.click = AsyncMock()
            loc.fill = AsyncMock()
            loc.count = AsyncMock(return_value=0)
            loc.first = loc
            loc.inner_text = AsyncMock(return_value="")
            if "body" in selector:
                return body_mock
            if "email" in selector.lower() and "code" not in selector.lower():
                return mock_email_input
            if "email me a sign in code" in selector.lower():
                return mock_code_btn
            # Digit boxes: #field-N, [data-testid='character-N']
            for i in range(6):
                if f"#field-{i}" in selector or f"character-{i}" in selector:
                    return digit_box_mocks[i]
            if "verification" in selector and "input" in selector:
                return mock_seek_input
            # Error containers selector (check BEFORE broad 'container' match)
            if "client-side-error" in selector or "role='alert'" in selector:
                return mock_err_containers
            if "data-testid='container'" in selector or "#field-0" in selector:
                return mock_field_0
            if "#submit-otp" in selector.lower() or "verification" in selector.lower():
                return mock_submit_otp
            return loc

        mock_page.locator = fake_locator

        async def fake_is_visible(target, timeout=None):
            if target in (mock_email_input, "#emailAddress") or "email" in str(target).lower():
                return True
            if target == mock_code_btn or "email me a sign in code" in str(target).lower():
                return True
            if target == mock_field_0 or target == "#field-0" or "container" in str(target).lower():
                return True
            # Digit boxes are visible
            for i in range(6):
                if target == digit_box_mocks[i]:
                    return True
            if target == mock_submit_otp or "#submit-otp" in str(target).lower():
                return True
            if "profile" in str(target).lower() and mock_page.url == "https://au.seek.com/":
                return True
            return False

        mock_page.evaluate = AsyncMock(return_value=True)

        mock_context = MagicMock()
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "registeredCandidateId", "value": "123456", "domain": "au.seek.com"},
            {"name": "appSession", "value": "xyz", "domain": "au.seek.com"},
        ])
        mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})

        with patch.object(agent, "_is_visible", side_effect=fake_is_visible), \
             patch.object(agent, "_wait_for_cloudflare", new_callable=AsyncMock), \
             patch.object(agent, "_human_delay", new_callable=AsyncMock), \
             patch.object(agent, "_type_human", new_callable=AsyncMock):

            agent.page = mock_page
            agent.context = mock_context
            login_result = await agent.login()
            assert login_result is True
            assert len(ask_called) == 1
            assert ask_called[0][0] == "otp_code"
            mock_seek_input.press_sequentially.assert_called_once()
            mock_submit_otp.click.assert_called_once()
            success_events = [e for e in emitted_events if e.get("type") == "apply_login_success"]
            assert len(success_events) == 1

    asyncio.run(_run())


def test_seek_login_handles_invalid_otp_error():
    """Verify that when an invalid OTP is entered and SEEK renders an error message
    in the scoped error container, the agent emits a verification error and returns False."""
    async def _run():
        emitted_events = []
        def track_progress(ev):
            emitted_events.append(ev)

        async def fake_ask(title, field, q):
            return "000000"

        agent = SeekApplyAgent(
            credentials={"email": "tester@seek.com.au"},
            resume_data={},
            profile={"email": "tester@seek.com.au"},
            ask_user_callback=fake_ask,
            progress_callback=track_progress,
        )

        mock_page = MagicMock()
        mock_page.url = "https://login.seek.com/login"
        mock_page.goto = AsyncMock()
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.type = AsyncMock()
        mock_page.keyboard.press = AsyncMock()

        # Body text simulation (harmless static text)
        body_mock = MagicMock()
        body_mock.inner_text = AsyncMock(return_value="Check your email for a code. We sent a code to tester@seek.com.au")

        mock_field_0 = MagicMock()
        mock_field_0.first = mock_field_0
        mock_field_0.click = AsyncMock()

        mock_seek_input = MagicMock()
        mock_seek_input.first = mock_seek_input
        mock_seek_input.count = AsyncMock(return_value=1)
        mock_seek_input.click = AsyncMock()
        mock_seek_input.press_sequentially = AsyncMock()

        mock_submit_otp = MagicMock()
        mock_submit_otp.first = mock_submit_otp
        screen_state = {"submitted": False}
        async def fake_submit():
            screen_state["submitted"] = True
        mock_submit_otp.click = AsyncMock(side_effect=fake_submit)

        # Error container mock — shows "invalid" error after submit
        mock_err_el = MagicMock()
        mock_err_el.first = mock_err_el
        async def fake_err_inner():
            if screen_state["submitted"]:
                return "The code you entered is invalid. Please try again."
            return ""
        mock_err_el.inner_text = AsyncMock(side_effect=fake_err_inner)

        mock_err_containers = MagicMock()
        async def fake_err_count():
            return 1 if screen_state["submitted"] else 0
        mock_err_containers.count = AsyncMock(side_effect=fake_err_count)
        mock_err_containers.first = mock_err_el
        def err_nth(idx):
            return mock_err_el
        mock_err_containers.nth = err_nth

        # Digit box mocks — return the digits so Strategy 1 succeeds and triggers submit
        the_code = "000000"
        digit_box_mocks = {}
        for i in range(6):
            box = MagicMock()
            box.first = box
            box.inner_text = AsyncMock(return_value=the_code[i])
            digit_box_mocks[i] = box

        def fake_locator(selector):
            loc = MagicMock()
            loc.click = AsyncMock()
            loc.fill = AsyncMock()
            loc.count = AsyncMock(return_value=0)
            loc.first = loc
            loc.inner_text = AsyncMock(return_value="")
            if "body" in selector:
                return body_mock
            # Digit boxes
            for i in range(6):
                if f"#field-{i}" in selector or f"character-{i}" in selector:
                    return digit_box_mocks[i]
            if "verification" in selector and "input" in selector:
                return mock_seek_input
            # Error containers selector (check BEFORE broad 'container' match)
            if "client-side-error" in selector or "role='alert'" in selector:
                return mock_err_containers
            if "data-testid='container'" in selector or "#field-0" in selector:
                return mock_field_0
            if "#submit-otp" in selector.lower() or ("verification" in selector.lower() and "submit" not in selector.lower()):
                return mock_submit_otp
            return loc

        mock_page.locator = fake_locator

        async def fake_is_visible(target, timeout=None):
            # Error container element is visible after submit
            if target == mock_err_el and screen_state["submitted"]:
                return True
            if target == mock_err_el:
                return False
            # Digit boxes are visible
            for i in range(6):
                if target == digit_box_mocks[i]:
                    return True
            return True

        mock_page.evaluate = AsyncMock(return_value=True)

        with patch.object(agent, "_is_visible", side_effect=fake_is_visible), \
             patch.object(agent, "_wait_for_cloudflare", new_callable=AsyncMock), \
             patch.object(agent, "_human_delay", new_callable=AsyncMock), \
             patch.object(agent, "_type_human", new_callable=AsyncMock):

            agent.page = mock_page
            login_result = await agent.login()
            assert login_result is False
            err_events = [e for e in emitted_events if e.get("type") == "apply_error"]
            assert any("verification error" in e.get("message", "").lower() for e in err_events)

    asyncio.run(_run())

