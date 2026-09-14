"""
Block and Challenge Detector for HTTP and HTML responses.
Accurately distinguishes legitimate 200 responses from 200 CAPTCHA/challenge walls,
403 Forbidden, 429 Rate Limits, and WAF blocks without attempting to solve them.
"""
import re
from typing import Dict, Optional, Tuple


class BlockDetector:
    """
    Evaluates response status, headers, and text for anti-bot signatures.
    """

    CHALLENGE_PATTERNS = [
        (re.compile(r"<title>Just a moment\.\.\.</title>", re.IGNORECASE), "Cloudflare Challenge Title"),
        (re.compile(r"challenges\.cloudflare\.com|cf-turnstile", re.IGNORECASE), "Cloudflare Turnstile"),
        (re.compile(r"attention required!\s*\|\s*cloudflare", re.IGNORECASE), "Cloudflare Attention Required"),
        (re.compile(r"cf-chl-widget-|cf-challenge-running", re.IGNORECASE), "Cloudflare Challenge Running"),
        (re.compile(r"google\.com/recaptcha/api\.js|class=[\"']g-recaptcha[\"']", re.IGNORECASE), "Google reCAPTCHA"),
        (re.compile(r"hcaptcha\.com/1/api\.js|class=[\"']h-captcha[\"']", re.IGNORECASE), "hCaptcha Challenge"),
        (re.compile(r"perimeterx|_pxhd|px-captcha", re.IGNORECASE), "PerimeterX Bot Challenge"),
        (re.compile(r"geo\.captcha-delivery\.com|datadome", re.IGNORECASE), "DataDome Challenge"),
        (re.compile(r"token\.awswaf\.com|awswaf", re.IGNORECASE), "AWS WAF Challenge"),
        (re.compile(r"please verify you are a human|verify you are a human", re.IGNORECASE), "Human Verification Challenge"),
        (re.compile(r"access denied\s*-\s*security check", re.IGNORECASE), "Security Check Access Denied"),
        (re.compile(r"ip\s*has been (?:blocked|flagged|blacklisted)", re.IGNORECASE), "IP Block Notice"),
    ]

    @classmethod
    def evaluate(
        cls,
        status_code: int,
        content: str,
        headers: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Inspects an HTTP response.
        Returns:
            (is_blocked: bool, block_type: str | None, evidence: str | None)
        """
        headers = headers or {}
        header_keys_lower = {k.lower(): v.lower() for k, v in headers.items()}

        # 1. HTTP 429 Too Many Requests
        if status_code == 429:
            retry_after = header_keys_lower.get("retry-after", "")
            evidence = f"HTTP 429 Rate Limit encountered (Retry-After: {retry_after or 'None'})"
            return True, "rate_limited", evidence

        # 2. HTTP 403 Forbidden
        if status_code == 403:
            # Check if it is a challenge page or raw forbidden
            for pattern, name in cls.CHALLENGE_PATTERNS:
                if pattern.search(content):
                    return True, "captcha_challenge", f"HTTP 403 with anti-bot signature: {name}"
            return True, "http_forbidden", "HTTP 403 Forbidden: access denied by origin server"

        # 3. HTTP 503 Service Unavailable (often Cloudflare anti-DDoS / challenge)
        if status_code == 503:
            for pattern, name in cls.CHALLENGE_PATTERNS:
                if pattern.search(content):
                    return True, "captcha_challenge", f"HTTP 503 Cloudflare challenge: {name}"
            if "cloudflare" in header_keys_lower.get("server", ""):
                return True, "waf_blocked", "HTTP 503 Cloudflare protective mitigation"
            return True, "degraded", "HTTP 503 Service Unavailable"

        # 4. HTTP 200 OK with stealth CAPTCHA / JavaScript challenge page
        if status_code == 200 and content:
            # Check content against known challenge indicators
            for pattern, name in cls.CHALLENGE_PATTERNS:
                if pattern.search(content):
                    return True, "captcha_challenge", f"HTTP 200 disguised challenge page: {name}"

        # Clean response
        return False, None, None
