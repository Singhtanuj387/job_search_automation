"""Unit tests for domain rate limiter and politeness layer."""
import time
from core.politeness import DomainRateLimiter


def test_rate_limiter_interval_and_jitter():
    # 60 requests per minute = 1.0s interval
    limiter = DomainRateLimiter(default_requests_per_minute=60.0, jitter_range=(1.0, 1.0), respect_robots_txt=False)
    domain = "test.domain.com"

    # First request should not wait
    slept1 = limiter.wait_if_needed(domain)
    assert slept1 == 0.0

    # Second immediate request should wait ~1.0s
    start = time.time()
    slept2 = limiter.wait_if_needed(domain)
    duration = time.time() - start
    assert slept2 > 0.8
    assert duration >= 0.8


def test_mark_domain_blocked():
    limiter = DomainRateLimiter()
    domain = "blocked.example.com"
    assert not limiter.is_domain_blocked(domain)

    limiter.mark_domain_blocked(domain)
    assert limiter.is_domain_blocked(domain)
