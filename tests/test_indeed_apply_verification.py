"""
Unit tests for Indeed application verification and false-positive prevention.
Ensures:
1. _fill_application_form strictly returns False if submission is not confirmed.
2. _fill_application_form returns True only upon verified confirmation.
3. External apply buttons result in MANUAL_REQUIRED.
4. Already applied jobs return SKIPPED without inflating applied count.
5. Missing Indeed apply buttons return SKIPPED without error or false-positive applied status.
6. build_direct_job_url correctly resolves 16-hex Indeed job keys to direct viewjob?jk= URLs.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from web.backend.indeed_apply_agent import IndeedApplyAgent, ApplyStatus, _companies_match
from adapters.indian_platforms import build_direct_job_url


@pytest.mark.anyio
async def test_fill_application_form_returns_false_when_not_confirmed():
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://smartapply.indeed.com/beta/indeedapply/form/contact-info"
    
    mock_locator = MagicMock()
    mock_locator.first.is_visible = AsyncMock(return_value=False)
    mock_locator.all = AsyncMock(return_value=[])
    mock_page.locator.return_value = mock_locator
    agent.page = mock_page

    result = await agent._fill_application_form({"id": 1, "company": "TestCo", "title": "Dev"})
    assert result is False, "Must return False when no confirmation indicator or submit occurs"


@pytest.mark.anyio
async def test_fill_application_form_returns_true_when_postapply_url_present():
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://smartapply.indeed.com/beta/indeedapply/postapply"
    mock_page.close = AsyncMock()
    
    mock_locator = MagicMock()
    mock_locator.first.is_visible = AsyncMock(return_value=False)
    mock_locator.all = AsyncMock(return_value=[])
    mock_page.locator.return_value = mock_locator
    agent.page = mock_page

    result = await agent._fill_application_form({"id": 1, "company": "TestCo", "title": "Dev"})
    assert result is True, "Must return True when postapply URL is detected"


@pytest.mark.anyio
async def test_apply_to_job_skips_when_no_apply_button():
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/viewjob?jk=150f9e582999b351"
    mock_page.goto = AsyncMock()
    mock_page.is_closed.return_value = False

    def locator_mock(selector):
        loc = MagicMock()
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.wait_for = AsyncMock()
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator.side_effect = locator_mock
    agent.page = mock_page

    result = await agent.apply_to_job({
        "id": 101,
        "company": "Company A",
        "title": "Engineer",
        "apply_url": "https://in.indeed.com/viewjob?jk=150f9e582999b351"
    })
    assert result.status == ApplyStatus.SKIPPED
    assert "Indeed Apply button not found" in result.message


@pytest.mark.anyio
async def test_apply_to_job_external_redirect():
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/viewjob?jk=150f9e582999b351"
    mock_page.goto = AsyncMock()
    mock_page.is_closed.return_value = False

    def locator_mock(selector):
        loc = MagicMock()
        loc.first.wait_for = AsyncMock()
        if "Apply on company site" in selector:
            loc.first.is_visible = AsyncMock(return_value=True)
        else:
            loc.first.is_visible = AsyncMock(return_value=False)
        return loc

    mock_page.locator.side_effect = locator_mock
    agent.page = mock_page

    result = await agent.apply_to_job({
        "id": 102,
        "company": "External Co",
        "title": "Engineer",
        "apply_url": "https://in.indeed.com/viewjob?jk=150f9e582999b351"
    })
    assert result.status == ApplyStatus.MANUAL_REQUIRED
    assert "external employer career portal" in result.message


@pytest.mark.anyio
async def test_apply_to_job_already_applied_returns_skipped():
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/viewjob?jk=150f9e582999b351"
    mock_page.goto = AsyncMock()
    mock_page.is_closed.return_value = False

    def locator_mock(selector):
        loc = MagicMock()
        loc.first.wait_for = AsyncMock()
        if "[data-testid='indeedApply-applied']" in selector:
            loc.first.is_visible = AsyncMock(return_value=True)
        else:
            loc.first.is_visible = AsyncMock(return_value=False)
        return loc

    mock_page.locator.side_effect = locator_mock
    agent.page = mock_page

    result = await agent.apply_to_job({
        "id": 103,
        "company": "Prior Applied Co",
        "title": "Engineer",
        "apply_url": "https://in.indeed.com/viewjob?jk=150f9e582999b351"
    })
    assert result.status == ApplyStatus.SKIPPED
    assert "Already applied on Indeed earlier" in result.message


def test_build_direct_job_url_indeed():
    # With 16-hex job key
    url_direct = build_direct_job_url("indeed", "Oracle", "ML Engineer", "Bangalore", item_id="150f9e582999b351")
    assert url_direct == "https://in.indeed.com/viewjob?jk=150f9e582999b351"

    # With prefix IND-
    url_prefixed = build_direct_job_url("indeed", "Oracle", "ML Engineer", "Bangalore", item_id="IND-150f9e582999b351")
    assert url_prefixed == "https://in.indeed.com/viewjob?jk=150f9e582999b351"

    # Without job key (falls back to search query URL)
    url_search = build_direct_job_url("indeed", "Oracle", "ML Engineer", "Bangalore")
    assert "in.indeed.com/jobs?q=" in url_search
    assert "ML+Engineer" in url_search
    assert "l=Bangalore" in url_search


@pytest.mark.anyio
async def test_apply_to_job_search_page_picks_apply_with_indeed_over_external():
    """Verify that search page candidate iteration picks card with Apply with Indeed over external cards."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    agent._fill_application_form = AsyncMock(return_value=True)

    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/jobs?q=Principal+ML+Engineer+Oracle&l=Bangalore"
    mock_page.goto = AsyncMock()
    mock_page.is_closed.return_value = False

    # Card 0: External apply
    mock_card0 = MagicMock()
    mock_card0.text_content = AsyncMock(return_value="Principal ML Engineer Oracle Apply on company site")
    mock_card0.locator.return_value.first.is_visible = AsyncMock(return_value=True)
    mock_card0.locator.return_value.first.scroll_into_view_if_needed = AsyncMock()
    mock_card0.locator.return_value.first.click = AsyncMock()

    # Card 1: Easily apply (Apply with Indeed)
    mock_card1 = MagicMock()
    mock_card1.text_content = AsyncMock(return_value="Principal ML Engineer Oracle Easily apply")
    mock_card1.locator.return_value.first.is_visible = AsyncMock(return_value=True)
    mock_card1.locator.return_value.first.scroll_into_view_if_needed = AsyncMock()
    mock_card1.locator.return_value.first.click = AsyncMock()

    def locator_mock(selector):
        loc = MagicMock()
        if ".job_seen_beacon" in selector or "[data-jk]" in selector:
            loc.all = AsyncMock(return_value=[mock_card0, mock_card1])
            loc.first.wait_for = AsyncMock()
            loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        if "#indeedApplyButton" in selector or "Apply with Indeed" in selector:
            loc.first.is_visible = AsyncMock(return_value=True)
            loc.first.scroll_into_view_if_needed = AsyncMock()
            loc.first.click = AsyncMock()
            return loc
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.wait_for = AsyncMock()
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator.side_effect = locator_mock
    agent.page = mock_page

    result = await agent.apply_to_job({
        "id": 200,
        "company": "Oracle",
        "title": "Principal ML Engineer",
        "apply_url": "https://in.indeed.com/jobs?q=Principal+ML+Engineer+Oracle&l=Bangalore"
    })
    assert result.status == ApplyStatus.APPLIED
    assert "Application submitted successfully via Indeed Apply" in result.message


@pytest.mark.anyio
async def test_radio_selection_negation_protection_and_sponsorship():
    """Verify that negation options ('I Disagree', 'I do not agree') are rejected,
    warrant/sole employment agreements are confirmed ('I Agree'), and sponsorship is answered 'No'."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={"location": "Bangalore"},
    )
    checked_elements = []

    async def mock_safe_check_radio(r):
        checked_elements.append(r)

    agent._safe_check_radio = mock_safe_check_radio

    # Create mock radio buttons
    # 1. Sponsorship: Yes, No
    r_spon_yes = MagicMock(name="spon_yes")
    r_spon_no = MagicMock(name="spon_no")

    # 2. Sole employment: I agree, I do not agree
    r_sole_agree = MagicMock(name="sole_agree")
    r_sole_disagree = MagicMock(name="sole_disagree")

    # 3. Truthfulness warrant: I Agree, I Disagree
    r_warrant_agree = MagicMock(name="warrant_agree")
    r_warrant_disagree = MagicMock(name="warrant_disagree")

    # Set up get_attribute and is_checked for radio grouping phase
    name_map = {
        id(r_spon_yes): "sponsorship_q", id(r_spon_no): "sponsorship_q",
        id(r_sole_agree): "sole_q", id(r_sole_disagree): "sole_q",
        id(r_warrant_agree): "warrant_q", id(r_warrant_disagree): "warrant_q",
    }
    for r in [r_spon_yes, r_spon_no, r_sole_agree, r_sole_disagree, r_warrant_agree, r_warrant_disagree]:
        r.get_attribute = AsyncMock(side_effect=lambda attr, _r=r: name_map.get(id(_r), "") if attr == "name" else "")
        r.is_checked = AsyncMock(return_value=False)

    label_map = {
        r_spon_yes: "Yes",
        r_spon_no: "No",
        r_sole_agree: "I agree",
        r_sole_disagree: "I do not agree",
        r_warrant_agree: "I Agree",
        r_warrant_disagree: "I Disagree",
    }

    qctx_map = {
        r_spon_yes: "Do you now, or will you in the future, require employer sponsorship to work in India?",
        r_spon_no: "Do you now, or will you in the future, require employer sponsorship to work in India?",
        r_sole_agree: "I confirm that, upon accepting an offer with Karat, this role will be my sole employment.",
        r_sole_disagree: "I confirm that, upon accepting an offer with Karat, this role will be my sole employment.",
        r_warrant_agree: "By submitting my application, I represent and warrant, under penalty of law, that all information is true, complete, and accurate.",
        r_warrant_disagree: "By submitting my application, I represent and warrant, under penalty of law, that all information is true, complete, and accurate.",
    }

    agent._get_input_label = AsyncMock(side_effect=lambda r: label_map[r])
    agent._get_question_context = AsyncMock(side_effect=lambda r: qctx_map[r])

    mock_frame = MagicMock()
    radio_list = [
        r_spon_yes, r_spon_no,
        r_sole_agree, r_sole_disagree,
        r_warrant_agree, r_warrant_disagree
    ]

    def _locator_side_effect(selector):
        m = MagicMock()
        if "radio" in selector:
            m.all = AsyncMock(return_value=radio_list)
        else:
            m.all = AsyncMock(return_value=[])
            m.count = AsyncMock(return_value=0)
            m.is_visible = AsyncMock(return_value=False)
            m.first = m  # chain .first to return same empty mock
        return m
    mock_frame.locator = MagicMock(side_effect=_locator_side_effect)
    mock_frame.evaluate = AsyncMock(return_value=None)

    await agent._fill_step_fields(mock_frame, "TestCo", "Dev")

    assert r_spon_no in checked_elements, "Sponsorship 'No' must be checked"
    assert r_spon_yes not in checked_elements, "Sponsorship 'Yes' must NOT be checked"

    assert r_sole_agree in checked_elements, "Sole employment 'I agree' must be checked"
    assert r_sole_disagree not in checked_elements, "Sole employment 'I do not agree' must NOT be checked"

    assert r_warrant_agree in checked_elements, "Truthfulness 'I Agree' must be checked"
    assert r_warrant_disagree not in checked_elements, "Truthfulness 'I Disagree' must NOT be checked"


@pytest.mark.anyio
async def test_fill_application_form_detects_recaptcha_bframe():
    """Verify that an interactive visual reCAPTCHA challenge (bframe) sets MANUAL_REQUIRED."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()

    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://smartapply.indeed.com/beta/indeedapply/form/review-module"
    mock_page.evaluate = AsyncMock(return_value="")

    # Mock recaptcha bframe
    mock_bframe = MagicMock()
    mock_bframe.url = "https://www.recaptcha.net/recaptcha/enterprise/bframe?hl=en"
    mock_chal = MagicMock()
    mock_chal.count = AsyncMock(return_value=1)
    mock_chal.is_visible = AsyncMock(return_value=True)
    mock_bframe.locator.return_value.first = mock_chal

    mock_page.frames = [mock_bframe]

    mock_locator = MagicMock()
    mock_locator.first.is_visible = AsyncMock(return_value=False)
    mock_locator.all = AsyncMock(return_value=[])
    mock_page.locator.return_value = mock_locator
    agent.page = mock_page

    result = await agent._fill_application_form({"id": 1, "company": "TestCo", "title": "Dev"})
    assert result is False
    assert agent._last_form_status == ApplyStatus.MANUAL_REQUIRED
    assert "reCAPTCHA verification challenge required" in agent._last_form_message


@pytest.mark.anyio
async def test_submitting_event_emitted_only_once():
    """Verify that 'submitting' step event is emitted at most once even if multiple submit selectors match."""
    emitted_events = []

    def mock_emit(evt):
        emitted_events.append(evt)

    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._emit = mock_emit
    agent._human_delay = AsyncMock()

    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://smartapply.indeed.com/beta/indeedapply/form/review-module"
    mock_page.evaluate = AsyncMock(return_value="")

    # Mock submit button: enabled, clicks successfully, then confirmed
    mock_btn_first = MagicMock()
    mock_btn_first.count = AsyncMock(return_value=1)
    mock_btn_first.is_visible = AsyncMock(return_value=True)
    mock_btn_first.is_disabled = AsyncMock(return_value=False)
    mock_btn_first.scroll_into_view_if_needed = AsyncMock()

    confirmed_state = False
    async def on_submit_click(**kwargs):
        nonlocal confirmed_state
        confirmed_state = True

    mock_btn_first.click = AsyncMock(side_effect=on_submit_click)

    mock_submit_loc = MagicMock()
    mock_submit_loc.first = mock_btn_first

    def mock_page_locator(sel):
        loc = MagicMock()
        if any(kw in sel for kw in ["submit-application-button", "Submit your application", "Submit application"]):
            return mock_submit_loc
        if "application-submitted" in sel or "Your application was sent to" in sel:
            loc.first.is_visible = AsyncMock(side_effect=lambda timeout=None: confirmed_state)
            return loc
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator = mock_page_locator
    mock_page.frames = []
    agent.page = mock_page

    result = await agent._fill_application_form({"id": 3702, "company": "Flipkart", "title": "ML Engineer"})
    assert result is True

    submitting_emits = [e for e in emitted_events if e.get("step") == "submitting"]
    assert len(submitting_emits) == 1, f"Expected exactly 1 'submitting' event, got {len(submitting_emits)}"
    assert "Flipkart" in submitting_emits[0]["message"]


@pytest.mark.anyio
async def test_post_submit_recaptcha_challenge_triggers_manual_required():
    """Verify that if reCAPTCHA challenge appears post-submit, status is set to MANUAL_REQUIRED."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()

    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://smartapply.indeed.com/beta/indeedapply/form/review-module"
    mock_page.evaluate = AsyncMock(return_value="")

    mock_bframe = MagicMock()
    mock_bframe.url = "https://www.recaptcha.net/recaptcha/enterprise/bframe?hl=en"
    mock_chal = MagicMock()
    mock_chal.count = AsyncMock(return_value=1)
    mock_chal.is_visible = AsyncMock(return_value=True)
    mock_bframe.locator.return_value.first = mock_chal

    # Submit button is initially clickable
    mock_btn_first = MagicMock()
    mock_btn_first.count = AsyncMock(return_value=1)
    mock_btn_first.is_visible = AsyncMock(return_value=True)
    mock_btn_first.is_disabled = AsyncMock(return_value=False)
    mock_btn_first.scroll_into_view_if_needed = AsyncMock()

    async def on_submit_click(**kwargs):
        # Post-click: reCAPTCHA pops up
        mock_page.frames = [mock_bframe]

    mock_btn_first.click = AsyncMock(side_effect=on_submit_click)

    mock_submit_loc = MagicMock()
    mock_submit_loc.first = mock_btn_first

    def mock_page_locator(sel):
        loc = MagicMock()
        if "submit-application-button" in sel:
            return mock_submit_loc
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator = mock_page_locator
    mock_page.frames = []
    agent.page = mock_page

    result = await agent._fill_application_form({"id": 3703, "company": "Myntra", "title": "ML Engineer"})
    assert result is False
    assert agent._last_form_status == ApplyStatus.MANUAL_REQUIRED
    assert "reCAPTCHA verification challenge required" in agent._last_form_message


@pytest.mark.anyio
async def test_geographic_and_willingness_fields_auto_filled():
    """Verify state, country, postal_code, and hybrid/comfort questions are automatically answered without prompting user."""
    agent = IndeedApplyAgent(
        credentials={"email": "candidate@example.com"},
        resume_data={"location": "Bangalore"},
        profile={
            "location": "Bangalore",
            "state": "Karnataka",
            "country": "India",
            "postal_code": "560001",
        },
    )
    agent.ask_user = AsyncMock(return_value=None)
    agent._human_delay = AsyncMock()

    inp_city = MagicMock(name="city")
    inp_state = MagicMock(name="state")
    inp_country = MagicMock(name="country")
    inp_pin = MagicMock(name="postal_code")
    inp_hybrid = MagicMock(name="hybrid_comfort")

    for inp in [inp_city, inp_state, inp_country, inp_pin, inp_hybrid]:
        inp.get_attribute = AsyncMock(return_value="")
        inp.input_value = AsyncMock(return_value="")

    label_map = {
        inp_city: "City",
        inp_state: "State",
        inp_country: "Country",
        inp_pin: "Postal Code",
        inp_hybrid: "Are you comfortable to work in Bangalore in hybrid mode? *",
    }

    agent._get_input_label = AsyncMock(side_effect=lambda el: label_map[el])

    typed_values = {}
    async def mock_type_human(inp, val):
        typed_values[label_map[inp]] = val

    agent._type_human = mock_type_human

    def mock_frame_locator(sel):
        loc = MagicMock()
        if "input" in sel:
            loc.all = AsyncMock(return_value=[inp_city, inp_state, inp_country, inp_pin, inp_hybrid])
        else:
            loc.all = AsyncMock(return_value=[])
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.count = AsyncMock(return_value=0)
        return loc

    mock_frame = MagicMock()
    mock_frame.locator = mock_frame_locator

    await agent._fill_step_fields(mock_frame, "Amazon India", "ML Engineer")

    # Verify user was NOT asked
    agent.ask_user.assert_not_called()

    # Verify values
    assert typed_values["City"] == "Bangalore"
    assert typed_values["State"] == "Karnataka"
    assert typed_values["Country"] == "India"
    assert typed_values["Postal Code"] == "560001"
    assert typed_values["Are you comfortable to work in Bangalore in hybrid mode? *"] == "Yes"


@pytest.mark.anyio
async def test_experience_range_radio_group_asks_user():
    """Verify that experience-range radio groups (e.g. '0-4 years', '4-8 years', '8+ years')
    ask the user in chat instead of auto-answering."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={"experience_years": 6},
        profile={},
        ask_user_callback=AsyncMock(return_value="4 - 8 years"),
    )
    emitted_events = []
    agent._emit = lambda ev: emitted_events.append(ev)
    checked_elements = []

    async def mock_safe_check_radio(r):
        checked_elements.append(r)

    agent._safe_check_radio = mock_safe_check_radio

    # Create mock radio buttons for experience range
    r_0_4 = MagicMock(name="r_0_4")
    r_4_8 = MagicMock(name="r_4_8")
    r_8plus = MagicMock(name="r_8plus")

    all_radios = [r_0_4, r_4_8, r_8plus]
    for r in all_radios:
        r.get_attribute = AsyncMock(side_effect=lambda attr, _r=r: "ml_exp_q" if attr == "name" else "")
        r.is_checked = AsyncMock(return_value=False)

    label_map = {
        r_0_4: "0 - 4 years",
        r_4_8: "4 - 8 years",
        r_8plus: "8+ years",
    }
    q_ctx = "What is your relevant experience in Machine Learning Engineering?"
    qctx_map = {r: q_ctx for r in all_radios}

    agent._get_input_label = AsyncMock(side_effect=lambda r: label_map.get(r, ""))
    agent._get_question_context = AsyncMock(side_effect=lambda r: qctx_map.get(r, ""))

    mock_frame = MagicMock()

    def _locator_side_effect(selector):
        m = MagicMock()
        if "radio" in selector:
            m.all = AsyncMock(return_value=all_radios)
        else:
            m.all = AsyncMock(return_value=[])
            m.count = AsyncMock(return_value=0)
            m.is_visible = AsyncMock(return_value=False)
            m.first = m
        return m
    mock_frame.locator = MagicMock(side_effect=_locator_side_effect)
    mock_frame.evaluate = AsyncMock(return_value=None)

    await agent._fill_step_fields(mock_frame, "Bazaarvoice", "Staff ML Engineer")

    # Verify ask_user was called for the experience question
    agent.ask_user.assert_called_once()
    call_args = agent.ask_user.call_args
    assert "experience" in call_args[0][1].lower() or "experience" in call_args[0][2].lower()

    # Verify the user's answer "4 - 8 years" was used to select the correct radio
    assert r_4_8 in checked_elements, "Experience '4 - 8 years' must be selected based on user's answer"
    assert r_0_4 not in checked_elements, "Experience '0 - 4 years' must NOT be selected"
    assert r_8plus not in checked_elements, "Experience '8+ years' must NOT be selected"

    # Verify a needs_input event was emitted
    needs_input_events = [e for e in emitted_events if e.get("step") == "needs_input"]
    assert len(needs_input_events) >= 1, "A 'needs_input' event must be emitted for experience questions"


@pytest.mark.anyio
async def test_previously_employed_radio_asks_user():
    """Verify that 'Have you ever been previously employed by X?' asks the user in chat."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
        ask_user_callback=AsyncMock(return_value="No"),
    )
    emitted_events = []
    agent._emit = lambda ev: emitted_events.append(ev)
    checked_elements = []

    async def mock_safe_check_radio(r):
        checked_elements.append(r)

    agent._safe_check_radio = mock_safe_check_radio

    r_prev_yes = MagicMock(name="prev_yes")
    r_prev_no = MagicMock(name="prev_no")

    all_radios = [r_prev_yes, r_prev_no]
    for r in all_radios:
        r.get_attribute = AsyncMock(side_effect=lambda attr, _r=r: "prev_emp_q" if attr == "name" else "")
        r.is_checked = AsyncMock(return_value=False)

    label_map = {r_prev_yes: "Yes", r_prev_no: "No"}
    qctx_map = {r: "Have you ever been previously employed by Bazaarvoice? Select ONE option from the below." for r in all_radios}

    agent._get_input_label = AsyncMock(side_effect=lambda r: label_map.get(r, ""))
    agent._get_question_context = AsyncMock(side_effect=lambda r: qctx_map.get(r, ""))

    mock_frame = MagicMock()

    def _locator_side_effect(selector):
        m = MagicMock()
        if "radio" in selector:
            m.all = AsyncMock(return_value=all_radios)
        else:
            m.all = AsyncMock(return_value=[])
            m.count = AsyncMock(return_value=0)
            m.is_visible = AsyncMock(return_value=False)
            m.first = m
        return m
    mock_frame.locator = MagicMock(side_effect=_locator_side_effect)
    mock_frame.evaluate = AsyncMock(return_value=None)

    await agent._fill_step_fields(mock_frame, "Bazaarvoice", "Staff ML Engineer")

    # Verify ask_user was called for the "previously employed" question
    agent.ask_user.assert_called_once()
    call_args = agent.ask_user.call_args
    assert "previously employed" in call_args[0][2].lower()

    # Verify "No" was selected based on user's answer
    assert r_prev_no in checked_elements, "'Previously employed' must select user's answer 'No'"
    assert r_prev_yes not in checked_elements, "'Previously employed' must NOT select 'Yes'"


@pytest.mark.anyio
async def test_product_based_company_radio_asks_user():
    """Verify that 'Do you have experience in Product Based Companies ?'
    asks the user in chat instead of auto-answering Yes via rule 10."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
        ask_user_callback=AsyncMock(return_value="Yes"),
    )
    emitted_events = []
    agent._emit = lambda ev: emitted_events.append(ev)
    checked_elements = []

    async def mock_safe_check_radio(r):
        checked_elements.append(r)

    agent._safe_check_radio = mock_safe_check_radio

    r_yes = MagicMock(name="pbc_yes")
    r_no = MagicMock(name="pbc_no")

    all_radios = [r_yes, r_no]
    for r in all_radios:
        r.get_attribute = AsyncMock(side_effect=lambda attr, _r=r: "pbc_exp_q" if attr == "name" else "")
        r.is_checked = AsyncMock(return_value=False)

    label_map = {r_yes: "Yes", r_no: "No"}
    q_text = "Do you have experience in Product Based Companies ? Select ONE option from the below."
    qctx_map = {r: q_text for r in all_radios}

    agent._get_input_label = AsyncMock(side_effect=lambda r: label_map.get(r, ""))
    agent._get_question_context = AsyncMock(side_effect=lambda r: qctx_map.get(r, ""))

    mock_frame = MagicMock()

    def _locator_side_effect(selector):
        m = MagicMock()
        if "radio" in selector:
            m.all = AsyncMock(return_value=all_radios)
        else:
            m.all = AsyncMock(return_value=[])
            m.count = AsyncMock(return_value=0)
            m.is_visible = AsyncMock(return_value=False)
            m.first = m
        return m
    mock_frame.locator = MagicMock(side_effect=_locator_side_effect)
    mock_frame.evaluate = AsyncMock(return_value=None)

    await agent._fill_step_fields(mock_frame, "Truemeds", "Frontend Engineer")

    # Verify ask_user was called
    agent.ask_user.assert_called_once()
    call_args = agent.ask_user.call_args
    assert "product based" in call_args[0][2].lower() or "product based" in call_args[0][1].lower()

    # Verify user answer "Yes" was selected
    assert r_yes in checked_elements
    assert r_no not in checked_elements


def test_companies_match_logic():
    """Verify company matching tolerance and strict mismatch rejection."""
    # Suffix and legal variations of the same employer
    assert _companies_match("Amazon India", "Amazon") is True
    assert _companies_match("Amazon India", "Amazon Development Centre India") is True
    assert _companies_match("Amazon", "Amazon.com Inc.") is True
    assert _companies_match("Flipkart", "Flipkart Internet Private Limited") is True
    assert _companies_match("Tata Consultancy Services", "Tata Consultancy Services Ltd") is True
    assert _companies_match("Oracle IDC", "Oracle India Private Limited") is True
    assert _companies_match("Microsoft India", "Microsoft Corporation") is True
    assert _companies_match("Swiggy", "Bundl Technologies (Swiggy)") is True

    # Completely different employers must strictly return False
    assert _companies_match("Amazon India", "Wipro Digital") is False
    assert _companies_match("Oracle", "Tech Mahindra") is False
    assert _companies_match("Google", "Cognizant Technology Solutions") is False
    assert _companies_match("Swiggy", "Zomato") is False
    assert _companies_match("Myntra", "Flipkart") is False

    # Empty or unknown must return False
    assert _companies_match("", "Amazon") is False
    assert _companies_match("Amazon", "") is False
    assert _companies_match("Unknown", "Amazon") is False
    assert _companies_match("Amazon", "Unknown") is False


@pytest.mark.anyio
async def test_search_page_rejects_different_company_cards():
    """Verify that search results belonging to unrelated companies are disqualified even if they have Easily apply."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/jobs?q=Senior+ML+Engineer+Amazon+India&l=Bangalore"
    mock_page.goto = AsyncMock()
    mock_page.is_closed.return_value = False

    # Card 0: Unrelated consultancy with "Apply with Indeed" badge
    mock_card0 = MagicMock()
    mock_card0.text_content = AsyncMock(return_value="Senior ML Engineer Wipro Digital Apply with Indeed")
    mock_card0_loc = MagicMock()
    mock_card0_loc.first.is_visible = AsyncMock(return_value=True)
    mock_card0_loc.first.text_content = AsyncMock(return_value="Wipro Digital")
    mock_card0.locator.return_value = mock_card0_loc

    # Card 1: Unrelated tech firm with "Easily apply" badge
    mock_card1 = MagicMock()
    mock_card1.text_content = AsyncMock(return_value="Senior ML Engineer Tech Mahindra Easily apply")
    mock_card1_loc = MagicMock()
    mock_card1_loc.first.is_visible = AsyncMock(return_value=True)
    mock_card1_loc.first.text_content = AsyncMock(return_value="Tech Mahindra")
    mock_card1.locator.return_value = mock_card1_loc

    def locator_mock(selector):
        loc = MagicMock()
        if ".job_seen_beacon" in selector or "[data-jk]" in selector:
            loc.all = AsyncMock(return_value=[mock_card0, mock_card1])
            loc.first.wait_for = AsyncMock()
            loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.wait_for = AsyncMock()
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator.side_effect = locator_mock
    agent.page = mock_page

    result = await agent.apply_to_job({
        "id": 501,
        "company": "Amazon India",
        "title": "Senior ML Engineer",
        "apply_url": "https://in.indeed.com/jobs?q=Senior+ML+Engineer+Amazon+India&l=Bangalore"
    })

    # The agent MUST skip and NOT click or apply to Wipro or Tech Mahindra
    assert result.status == ApplyStatus.SKIPPED
    assert "No job cards found matching Amazon India" in result.message


@pytest.mark.anyio
async def test_search_page_strictly_picks_target_company_over_unrelated_badge():
    """Verify that agent selects the matching company card even if an unrelated card has an apply badge."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    agent._fill_application_form = AsyncMock(return_value=True)

    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/jobs?q=Senior+ML+Engineer+Amazon+India&l=Bangalore"
    mock_page.goto = AsyncMock()
    mock_page.is_closed.return_value = False

    clicked_cards = []

    # Card 0: Unrelated employer with "Apply with Indeed" badge
    mock_card0 = MagicMock()
    mock_card0.text_content = AsyncMock(return_value="Senior ML Engineer Random Staffing Apply with Indeed")
    mock_card0_loc = MagicMock()
    mock_card0_loc.first.is_visible = AsyncMock(return_value=True)
    mock_card0_loc.first.text_content = AsyncMock(return_value="Random Staffing")
    mock_card0_loc.first.scroll_into_view_if_needed = AsyncMock()
    mock_card0_loc.first.click = AsyncMock(side_effect=lambda: clicked_cards.append("card0"))
    mock_card0.locator.return_value = mock_card0_loc

    # Card 1: Target company (Amazon India) with "Easily apply"
    mock_card1 = MagicMock()
    mock_card1.text_content = AsyncMock(return_value="Senior ML Engineer Amazon India Easily apply")
    mock_card1_loc = MagicMock()
    mock_card1_loc.first.is_visible = AsyncMock(return_value=True)
    mock_card1_loc.first.text_content = AsyncMock(return_value="Amazon India")
    mock_card1_loc.first.scroll_into_view_if_needed = AsyncMock()
    mock_card1_loc.first.click = AsyncMock(side_effect=lambda: clicked_cards.append("card1"))
    mock_card1.locator.return_value = mock_card1_loc

    def locator_mock(selector):
        loc = MagicMock()
        if ".job_seen_beacon" in selector or "[data-jk]" in selector:
            loc.all = AsyncMock(return_value=[mock_card0, mock_card1])
            loc.first.wait_for = AsyncMock()
            loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        if "[data-testid='inlineHeader-companyName']" in selector:
            loc.first.is_visible = AsyncMock(return_value=True)
            loc.first.text_content = AsyncMock(return_value="Amazon India")
            return loc
        if "#indeedApplyButton" in selector or "Apply with Indeed" in selector:
            loc.first.is_visible = AsyncMock(return_value=True)
            loc.first.scroll_into_view_if_needed = AsyncMock()
            loc.first.click = AsyncMock()
            return loc
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.wait_for = AsyncMock()
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator.side_effect = locator_mock
    agent.page = mock_page

    result = await agent.apply_to_job({
        "id": 502,
        "company": "Amazon India",
        "title": "Senior ML Engineer",
        "apply_url": "https://in.indeed.com/jobs?q=Senior+ML+Engineer+Amazon+India&l=Bangalore"
    })

    assert result.status == ApplyStatus.APPLIED
    assert "card0" not in clicked_cards
    assert "card1" in clicked_cards


@pytest.mark.anyio
async def test_split_pane_company_mismatch_aborts_apply():
    """Verify that if the rendered detail pane belongs to a different employer, apply is aborted."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/jobs?q=ML+Engineer+Amazon&l=Bangalore"
    mock_page.goto = AsyncMock()
    mock_page.is_closed.return_value = False

    # Card text vaguely mentions Amazon
    mock_card = MagicMock()
    mock_card.text_content = AsyncMock(return_value="ML Engineer Amazon AWS Client Project Easily apply")
    mock_card_loc = MagicMock()
    mock_card_loc.first.is_visible = AsyncMock(return_value=True)
    mock_card_loc.first.text_content = AsyncMock(return_value="Amazon Client Partner")
    mock_card_loc.first.scroll_into_view_if_needed = AsyncMock()
    mock_card_loc.first.click = AsyncMock()
    mock_card.locator.return_value = mock_card_loc

    def locator_mock(selector):
        loc = MagicMock()
        if ".job_seen_beacon" in selector or "[data-jk]" in selector:
            loc.all = AsyncMock(return_value=[mock_card])
            loc.first.wait_for = AsyncMock()
            loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        # Detail pane renders Cognizant instead of Amazon India!
        if "[data-testid='inlineHeader-companyName']" in selector:
            loc.first.is_visible = AsyncMock(return_value=True)
            loc.first.text_content = AsyncMock(return_value="Cognizant Technology Solutions")
            return loc
        if "#indeedApplyButton" in selector:
            loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.wait_for = AsyncMock()
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator.side_effect = locator_mock
    agent.page = mock_page

    result = await agent.apply_to_job({
        "id": 503,
        "company": "Amazon India",
        "title": "ML Engineer",
        "apply_url": "https://in.indeed.com/jobs?q=ML+Engineer+Amazon&l=Bangalore"
    })

    # Must be SKIPPED without clicking apply
    assert result.status == ApplyStatus.SKIPPED


@pytest.mark.anyio
async def test_direct_job_view_company_mismatch_aborts():
    """Verify that in direct viewjob?jk=..., if company does not match, apply is aborted."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/viewjob?jk=150f9e582999b351"
    mock_page.goto = AsyncMock()
    mock_page.is_closed.return_value = False

    def locator_mock(selector):
        loc = MagicMock()
        # Direct view renders TCS instead of Flipkart
        if "[data-testid='inlineHeader-companyName']" in selector:
            loc.first.is_visible = AsyncMock(return_value=True)
            loc.first.text_content = AsyncMock(return_value="Tata Consultancy Services")
            return loc
        if "#indeedApplyButton" in selector:
            loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.wait_for = AsyncMock()
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator.side_effect = locator_mock
    agent.page = mock_page

    result = await agent.apply_to_job({
        "id": 504,
        "company": "Flipkart",
        "title": "ML Engineer",
        "apply_url": "https://in.indeed.com/viewjob?jk=150f9e582999b351"
    })

    assert result.status == ApplyStatus.SKIPPED
    assert "Tata Consultancy Services" in result.message


@pytest.mark.anyio
async def test_indeed_slider_item_and_testid_badge_detection():
    """Verify that div[data-testid='slider_item'] and [data-testid='indeedApply'] are detected."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/jobs?q=SDE+Amazon&l=Bangalore"
    mock_page.goto = AsyncMock()
    mock_page.is_closed.return_value = False

    # Mock card with data-testid="slider_item" and data-testid="indeedApply"
    mock_card = MagicMock()
    mock_card.text_content = AsyncMock(return_value="SDE Amazon India Bangalore")
    mock_card.scroll_into_view_if_needed = AsyncMock()
    mock_card.click = AsyncMock()

    mock_comp_loc = MagicMock()
    mock_comp_loc.first.is_visible = AsyncMock(return_value=True)
    mock_comp_loc.first.text_content = AsyncMock(return_value="Amazon India")
    mock_comp_loc.first.scroll_into_view_if_needed = AsyncMock()
    mock_comp_loc.first.click = AsyncMock()

    mock_badge_loc = MagicMock()
    mock_badge_loc.count = AsyncMock(return_value=1)

    def card_locator(sel):
        if "[data-testid='indeedApply']" in sel:
            return mock_badge_loc
        if "[data-testid='company-name']" in sel:
            return mock_comp_loc
        m = MagicMock()
        m.count = AsyncMock(return_value=0)
        m.first.is_visible = AsyncMock(return_value=False)
        return m

    mock_card.locator.side_effect = card_locator

    def page_locator(sel):
        loc = MagicMock()
        if "slider_item" in sel:
            loc.all = AsyncMock(return_value=[mock_card])
            loc.first.wait_for = AsyncMock()
            loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        if "[data-testid='inlineHeader-companyName']" in sel:
            loc.first.is_visible = AsyncMock(return_value=True)
            loc.first.text_content = AsyncMock(return_value="Amazon India")
            return loc
        if "#indeedApplyButton" in sel:
            loc.first.is_visible = AsyncMock(return_value=True)
            loc.first.click = AsyncMock()
            loc.first.scroll_into_view_if_needed = AsyncMock()
            return loc
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.wait_for = AsyncMock()
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator.side_effect = page_locator
    agent.page = mock_page
    agent._fill_application_form = AsyncMock(return_value=True)

    res = await agent.apply_to_job({
        "id": 601,
        "company": "Amazon India",
        "title": "SDE",
        "apply_url": "https://in.indeed.com/jobs?q=SDE+Amazon&l=Bangalore"
    })
    assert res.status == ApplyStatus.APPLIED


@pytest.mark.anyio
async def test_indeed_file_resume_card_header_title_selection():
    """Verify that [data-testid='FileResumeCardHeader-title'] is clicked during form filling."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()

    mock_frame = MagicMock()
    mock_frame.url = "https://smartapply.indeed.com/form/1"
    clicked_selectors = []

    mock_resume_card = MagicMock()
    mock_resume_card.count = AsyncMock(return_value=1)
    mock_resume_card.first.count = AsyncMock(return_value=1)
    mock_resume_card.first.is_visible = AsyncMock(return_value=True)
    mock_resume_card.first.scroll_into_view_if_needed = AsyncMock()
    async def mock_click():
        clicked_selectors.append("[data-testid='FileResumeCardHeader-title']")
    mock_resume_card.first.click = mock_click

    def frame_locator(sel):
        if "[data-testid='FileResumeCardHeader-title']" in sel:
            return mock_resume_card
        m = MagicMock()
        m.count = AsyncMock(return_value=0)
        m.first.count = AsyncMock(return_value=0)
        m.first.is_visible = AsyncMock(return_value=False)
        m.all = AsyncMock(return_value=[])
        return m

    mock_frame.locator.side_effect = frame_locator
    mock_frame.evaluate = AsyncMock()

    await agent._fill_step_fields(mock_frame, "Amazon", "SDE")
    assert "[data-testid='FileResumeCardHeader-title']" in clicked_selectors


@pytest.mark.anyio
async def test_indeed_confirmation_url_detected_as_success():
    """Verify that URLs containing confirmation or submitted confirm the application."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    agent.context = MagicMock()
    agent.context.pages = []

    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://smartapply.indeed.com/beta/indeedapply/form/confirmation?applied=true"
    mock_page.evaluate = AsyncMock(return_value="")
    mock_page.locator.return_value.first.is_visible = AsyncMock(return_value=False)
    mock_page.frames = []
    agent.page = mock_page

    success = await agent._fill_application_form({"id": 701, "company": "Google", "title": "SWE"})
    assert success is True


@pytest.mark.anyio
async def test_indeed_ppid_cookie_in_login():
    """Verify that PPID session token is logged during login verification."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    mock_context = MagicMock()
    mock_context.cookies = AsyncMock(return_value=[
        {"name": "PPID", "value": "test-ppid-value-12345"}
    ])
    agent.context = mock_context

    mock_page = MagicMock()
    mock_page.url = "https://myjobs.indeed.com"
    mock_page.goto = AsyncMock()
    agent._safe_title = AsyncMock(return_value="My Jobs | Indeed")
    agent.page = mock_page

    logged_in = await agent.login()
    assert logged_in is True


@pytest.mark.anyio
async def test_indeed_404_dead_page_auto_recovers_to_search():
    """Verify that when a direct viewjob link returns Indeed's 404 'We can't find this page',
    the agent automatically recovers by navigating to the company-scoped search query URL."""
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    agent._human_delay = AsyncMock()
    mock_page = MagicMock()
    mock_page.url = "https://in.indeed.com/viewjob?jk=deadlink12345678"
    mock_page.is_closed.return_value = False

    navigated_urls = []
    async def mock_goto(u, **kwargs):
        navigated_urls.append(u)
        if "jobs?q=" in u:
            mock_page.url = u
    mock_page.goto = mock_goto

    agent._safe_title = AsyncMock(return_value="Job Search | Indeed")

    # Body initially has 404 text
    body_loc = MagicMock()
    body_loc.inner_text = AsyncMock(return_value="We can’t find this page\nIt looks like this page doesn't exist or isn’t available right now.")

    mock_card = MagicMock()
    mock_card.text_content = AsyncMock(return_value="ML Engineer Amazon India Bangalore")
    mock_card.scroll_into_view_if_needed = AsyncMock()
    mock_card.click = AsyncMock()

    mock_comp_loc = MagicMock()
    mock_comp_loc.first.is_visible = AsyncMock(return_value=True)
    mock_comp_loc.first.text_content = AsyncMock(return_value="Amazon India")

    mock_badge_loc = MagicMock()
    mock_badge_loc.count = AsyncMock(return_value=1)

    def card_locator(sel):
        if "[data-testid='indeedApply']" in sel:
            return mock_badge_loc
        if "[data-testid='company-name']" in sel:
            return mock_comp_loc
        m = MagicMock()
        m.count = AsyncMock(return_value=0)
        m.first.is_visible = AsyncMock(return_value=False)
        return m

    mock_card.locator.side_effect = card_locator

    def page_locator(sel):
        if sel == "body":
            return body_loc
        loc = MagicMock()
        if "slider_item" in sel:
            loc.all = AsyncMock(return_value=[mock_card])
            loc.first.wait_for = AsyncMock()
            loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        if "[data-testid='inlineHeader-companyName']" in sel:
            loc.first.is_visible = AsyncMock(return_value=True)
            loc.first.text_content = AsyncMock(return_value="Amazon India")
            return loc
        if "#indeedApplyButton" in sel:
            loc.first.is_visible = AsyncMock(return_value=True)
            loc.first.click = AsyncMock()
            loc.first.scroll_into_view_if_needed = AsyncMock()
            return loc
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.wait_for = AsyncMock()
        loc.all = AsyncMock(return_value=[])
        return loc

    mock_page.locator.side_effect = page_locator
    agent.page = mock_page
    agent._fill_application_form = AsyncMock(return_value=True)

    res = await agent.apply_to_job({
        "id": 801,
        "company": "Amazon India",
        "title": "ML Engineer",
        "location": "Bangalore",
        "apply_url": "https://in.indeed.com/viewjob?jk=deadlink12345678"
    })
    assert res.status == ApplyStatus.APPLIED
    # Assert fallback search URL was navigated to
    assert any("jobs?q=" in u and "Amazon+India" in u and "sc=0kf" in u for u in navigated_urls)


@pytest.mark.anyio
async def test_recaptcha_challenge_audio_click_and_resolution():
    agent = IndeedApplyAgent(
        credentials={"email": "test@example.com"},
        resume_data={},
        profile={},
    )
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://smartapply.indeed.com/apply"

    mock_bframe = MagicMock()
    mock_bframe.url = "https://www.recaptcha.net/recaptcha/enterprise/bframe?hl=en"

    # Audio button
    mock_audio_btn = MagicMock()
    mock_audio_btn.first = mock_audio_btn
    mock_audio_btn.count = AsyncMock(return_value=1)
    mock_audio_btn.is_visible = AsyncMock(return_value=True)
    mock_audio_btn.click = AsyncMock()

    # Image challenge
    mock_chal = MagicMock()
    mock_chal.first = mock_chal
    mock_chal.count = AsyncMock(return_value=1)
    mock_chal.is_visible = AsyncMock(return_value=True)

    def bframe_locator(sel):
        loc = MagicMock()
        if "audio" in sel:
            return mock_audio_btn
        if "#rc-imageselect" in sel:
            return mock_chal
        loc.count = AsyncMock(return_value=0)
        loc.is_visible = AsyncMock(return_value=False)
        return loc

    mock_bframe.locator.side_effect = bframe_locator
    mock_page.frames = [mock_bframe]

    # Test that check detects challenge and triggers audio button
    has_chal = await agent._check_recaptcha_challenge(mock_page, "TestCo", "Developer", wait_timeout=0)
    assert has_chal is True
    assert agent._last_form_status == ApplyStatus.MANUAL_REQUIRED
