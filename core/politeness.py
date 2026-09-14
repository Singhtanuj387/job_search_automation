"""
Politeness and Anti-Blocking Layer.
Manages domain-specific rate limits, jittered delays, and robots.txt Crawl-delay compliance.
"""
import random
import time
import urllib.robotparser
from typing import Dict, Optional
import httpx


class DomainRateLimiter:
    """
    Tracks and throttles request intervals per origin domain.
    """

    def __init__(
        self,
        default_requests_per_minute: float = 30.0,
        jitter_range: tuple = (0.8, 1.4),
        respect_robots_txt: bool = True,
        proxy_url: Optional[str] = None,
    ):
        self.default_interval = 60.0 / default_requests_per_minute
        self.jitter_range = jitter_range
        self.respect_robots_txt = respect_robots_txt
        self.proxy_url = proxy_url

        self._last_request_time: Dict[str, float] = {}
        self._domain_intervals: Dict[str, float] = {}
        self._robots_parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._blocked_domains: set = set()

    def set_domain_rate(self, domain: str, requests_per_minute: float) -> None:
        """Configures a custom rate limit for a specific domain."""
        self._domain_intervals[domain] = 60.0 / requests_per_minute

    def mark_domain_blocked(self, domain: str) -> None:
        """Marks a domain as blocked to halt subsequent requests."""
        self._blocked_domains.add(domain)

    def is_domain_blocked(self, domain: str) -> bool:
        """Checks if requests to this domain have been suspended."""
        return domain in self._blocked_domains

    def check_and_parse_robots(self, domain: str, scheme: str = "https") -> None:
        """
        Fetches and parses robots.txt for Crawl-delay compliance if not already cached.
        """
        if not self.respect_robots_txt or domain in self._robots_parsers:
            return

        robots_url = f"{scheme}://{domain}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)

        try:
            client_kwargs = {"timeout": 6.0, "follow_redirects": True}
            if self.proxy_url:
                client_kwargs["proxy"] = self.proxy_url
            with httpx.Client(**client_kwargs) as client:
                resp = client.get(
                    robots_url,
                    headers={"User-Agent": "JobSearchEngineBot/1.0 (+https://github.com/morningstar)"}
                )
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                    # Extract crawl delay for standard user agent
                    delay = parser.crawl_delay("*")
                    if delay is not None and delay > 0:
                        self._domain_intervals[domain] = max(
                            self._domain_intervals.get(domain, self.default_interval),
                            float(delay)
                        )
        except Exception:
            # Fall back gracefully to configured domain interval on connection issue
            pass

        self._robots_parsers[domain] = parser

    def wait_if_needed(self, domain: str) -> float:
        """
        Calculates and executes a jittered sleep to respect rate limits and crawl delays.
        Returns the duration slept in seconds.
        """
        base_interval = self._domain_intervals.get(domain, self.default_interval)
        jitter_mult = random.uniform(self.jitter_range[0], self.jitter_range[1])
        target_interval = base_interval * jitter_mult

        now = time.time()
        last_time = self._last_request_time.get(domain, 0.0)
        elapsed = now - last_time

        sleep_duration = 0.0
        if elapsed < target_interval:
            sleep_duration = target_interval - elapsed
            time.sleep(sleep_duration)

        self._last_request_time[domain] = time.time()
        return sleep_duration
