"""Unit tests for LLM intent routing and fit tailoring."""
from core.models import NormalizedJob
from web.backend.llm_service import LLMService


def test_classify_intent():
    # Search intent
    r1 = LLMService.classify_intent("Find me React Developer jobs in Bangalore")
    assert r1["intent"] == "search"
    assert "React" in r1["role"]
    assert r1["location"] == "Bangalore"

    # Automate intent
    r2 = LLMService.classify_intent("Schedule my daily morning search at 8am")
    assert r2["intent"] == "automate"

    # Status intent
    r3 = LLMService.classify_intent("What is the status of my applications?")
    assert r3["intent"] == "status"

    # Apply to URL intent
    r4 = LLMService.classify_intent("Apply to this job: https://boards.greenhouse.io/canonical/jobs/12345")
    assert r4["intent"] == "apply_to_url"
    assert "canonical" in (r4.get("url") or "")

    # Seek platform search intent
    r5 = LLMService.classify_intent("find jobs on seek.com", stored_profile={"role": "React Developer"})
    assert r5["intent"] == "search"
    assert r5.get("sources") == ["seek"]
    assert "React" in r5["role"]

    r6 = LLMService.classify_intent("/job-skill search seek", stored_profile={"role": "Data Scientist"})
    assert r6["intent"] == "search"
    assert r6.get("sources") == ["seek"]
    assert "Data Scientist" in r6["role"]

    r7 = LLMService.classify_intent("find python jobs on seek.com.au")
    assert r7["intent"] == "search"
    assert r7.get("sources") == ["seek"]
    assert "Python" in r7["role"]



def test_tailor_job_qualitative_framing():
    job = NormalizedJob(
        source="greenhouse",
        source_job_id="101",
        title="Senior React Engineer",
        company="Canonical",
        location="Bangalore",
        description="We need a React developer proficient in TypeScript, Redux, and modern web architectures.",
        apply_url="https://example.com",
        fetch_method="api",
    )

    resume = """
    Software Engineer with 4 years experience building React and TypeScript single page applications.
    Strong skills in Redux, RESTful APIs, Git, and automated testing.
    """

    tailored = LLMService.tailor_job(job, resume)
    # Fit framing MUST be qualitative, e.g. "Strong Match" or "Exceptional Fit"
    assert tailored["fit_framing"] in ["Exceptional Fit", "Strong Match", "Worth a Look", "Moderate Alignment"]
    assert tailored["fitness_score"] >= 60
    assert "Canonical" in tailored["match_explanation"]
    assert "Senior React Engineer" in tailored["match_explanation"]


def test_validate_gemini_mock_interactions():
    from unittest.mock import MagicMock, patch

    mock_client = MagicMock()
    mock_interaction = MagicMock()
    mock_interaction.output_text = "AI is machine learning and reasoning."
    mock_client.interactions.create.return_value = mock_interaction

    with patch("google.genai.Client", return_value=mock_client):
        valid, msg = LLMService.validate_api_key(
            provider="gemini",
            api_key="AIzaSyTESTINGKEY12345",
            extra_config={"model_id": "Gemma-4-31B"},
        )
        assert valid is True
        assert "gemma-4-31b-it" in msg
        mock_client.interactions.create.assert_called_once()
        call_kwargs = mock_client.interactions.create.call_args[1]
        assert call_kwargs["model"] == "gemma-4-31b-it"


def test_validate_gemini_invalid_key_error():
    from unittest.mock import MagicMock, patch

    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = Exception("Error code: 400 - API_KEY_INVALID")

    with patch("google.genai.Client", return_value=mock_client):
        valid, msg = LLMService.validate_api_key(
            provider="gemini",
            api_key="AIzaSyBADKEY",
        )
        assert valid is False
        assert "Invalid Google Gemini API key" in msg


def test_invoke_gemini_success():
    from unittest.mock import MagicMock, patch

    mock_client = MagicMock()
    mock_interaction = MagicMock()
    mock_interaction.output_text = "Computers learning from data."
    mock_client.interactions.create.return_value = mock_interaction

    with patch("google.genai.Client", return_value=mock_client):
        output = LLMService.invoke_gemini(
            prompt="Explain how AI works in a few words",
            api_key="AIzaSyTESTKEY",
            model="Gemma-4-31B",
        )
        assert output == "Computers learning from data."
        mock_client.interactions.create.assert_called_once_with(
            model="gemma-4-31b-it",
            input="Explain how AI works in a few words",
        )


def test_invoke_llm_routes_to_gemini():
    from unittest.mock import patch

    with patch.object(LLMService, "invoke_gemini", return_value="Great career advice!") as mock_invoke:
        secret = {
            "provider": "gemini",
            "plaintext": '{"api_key": "AIzaSyTEST", "model_id": "Gemma-4-31B"}',
        }
        res = LLMService.invoke_llm("Help me with my resume", secret=secret)
        assert res == "Great career advice!"
        mock_invoke.assert_called_once_with(
            "Help me with my resume",
            api_key="AIzaSyTEST",
            model="Gemma-4-31B",
            max_tokens=500,
        )

