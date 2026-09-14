"""Unit tests for block detector anti-bot challenge recognition."""
from core.block_detector import BlockDetector


def test_clean_200_ok():
    is_blocked, b_type, evidence = BlockDetector.evaluate(
        status_code=200,
        content="<html><body><h1>Jobs List</h1><div>Engineer at Stripe</div></body></html>",
        headers={"content-type": "text/html"},
    )
    assert not is_blocked
    assert b_type is None
    assert evidence is None


def test_cloudflare_challenge_200():
    cf_challenge = "<html><head><title>Just a moment...</title></head><body><div id='cf-turnstile'></div></body></html>"
    is_blocked, b_type, evidence = BlockDetector.evaluate(
        status_code=200,
        content=cf_challenge,
    )
    assert is_blocked
    assert b_type == "captcha_challenge"
    assert "Cloudflare Challenge Title" in evidence


def test_recaptcha_challenge():
    content = "<div>Please complete the captcha below: <div class='g-recaptcha'></div></div>"
    is_blocked, b_type, evidence = BlockDetector.evaluate(
        status_code=200,
        content=content,
    )
    assert is_blocked
    assert b_type == "captcha_challenge"
    assert "Google reCAPTCHA" in evidence


def test_rate_limited_429():
    is_blocked, b_type, evidence = BlockDetector.evaluate(
        status_code=429,
        content="Too Many Requests",
        headers={"retry-after": "60"},
    )
    assert is_blocked
    assert b_type == "rate_limited"
    assert "Retry-After: 60" in evidence


def test_http_403_forbidden():
    is_blocked, b_type, evidence = BlockDetector.evaluate(
        status_code=403,
        content="Access Denied",
    )
    assert is_blocked
    assert b_type == "http_forbidden"
