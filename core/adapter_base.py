"""
Abstract Base Class for all Job Source Adapters (Tier A, Tier B, etc.).
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from core.models import HealthStatus, NormalizedJob, QueryConfig, RawResult


class BaseAdapter(ABC):
    """
    Uniform adapter interface across all source tiers.
    """
    name: str
    tier: str  # "A" | "B" | "C"
    base_url: str

    @abstractmethod
    def fetch(self, query: QueryConfig) -> List[RawResult]:
        """
        Pulls raw job postings matching the provided query configuration.
        Returns a list of RawResult objects containing raw payloads and metadata.
        """
        pass

    @abstractmethod
    def parse(self, raw: RawResult) -> List[NormalizedJob]:
        """
        Parses a RawResult into one or more NormalizedJob objects conforming
        to the universal job schema.
        """
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Probes the source endpoint to verify operational status.
        Returns:
            {"status": "ok" | "degraded" | "blocked", "evidence": "..."}
        """
        pass

    def get_domain(self) -> str:
        """
        Extracts the host domain for per-domain rate limiting and robots.txt checks.
        """
        from urllib.parse import urlparse
        return urlparse(self.base_url).netloc
