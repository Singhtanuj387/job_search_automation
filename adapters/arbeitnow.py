"""
Tier A Adapter for Arbeitnow Job Board API.
Official Public API documentation: https://www.arbeitnow.com/api/job-board-api
"""
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
import httpx

from core.adapter_base import BaseAdapter
from core.block_detector import BlockDetector
from core.models import NormalizedJob, QueryConfig, RawResult
from core.politeness import DomainRateLimiter


class ArbeitnowAdapter(BaseAdapter):
    name = "arbeitnow"
    tier = "A"
    base_url = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(
        self,
        rate_limiter: Optional[DomainRateLimiter] = None,
        proxy_url: Optional[str] = None,
    ):
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.proxy_url = proxy_url
        self.client_kwargs: Dict[str, Any] = {
            "timeout": 12.0,
            "follow_redirects": True,
            "headers": {
                "User-Agent": "JobSearchEngineBot/1.0 (+https://github.com/morningstar/job_search_automation)",
                "Accept": "application/json",
            },
        }
        if self.proxy_url:
            self.client_kwargs["proxy"] = self.proxy_url

    def health_check(self) -> Dict[str, Any]:
        """Probes the Arbeitnow API endpoint."""
        domain = self.get_domain()
        if self.rate_limiter.is_domain_blocked(domain):
            return {"status": "blocked", "evidence": "Domain marked blocked in rate limiter"}

        try:
            self.rate_limiter.wait_if_needed(domain)
            with httpx.Client(**self.client_kwargs) as client:
                resp = client.get(self.base_url)
                is_blocked, block_type, evidence = BlockDetector.evaluate(
                    resp.status_code, resp.text, dict(resp.headers)
                )
                if is_blocked:
                    self.rate_limiter.mark_domain_blocked(domain)
                    return {"status": "blocked", "evidence": evidence}

                if resp.status_code == 200:
                    data = resp.json()
                    jobs_count = len(data.get("data", []))
                    return {
                        "status": "ok",
                        "evidence": f"200 OK, retrieved {jobs_count} job listings from page 1",
                    }
                else:
                    return {
                        "status": "degraded",
                        "evidence": f"Unexpected HTTP status {resp.status_code}",
                    }
        except Exception as e:
            return {"status": "degraded", "evidence": f"Health check failed with error: {str(e)}"}

    def fetch(self, query: QueryConfig) -> List[RawResult]:
        domain = self.get_domain()
        if self.rate_limiter.is_domain_blocked(domain):
            return []

        raw_results: List[RawResult] = []
        page_url = self.base_url
        pages_to_fetch = 2  # fetch up to 2 pages of active jobs

        for _ in range(pages_to_fetch):
            if not page_url:
                break
            try:
                self.rate_limiter.wait_if_needed(domain)
                with httpx.Client(**self.client_kwargs) as client:
                    resp = client.get(page_url)
                    is_blocked, block_type, evidence = BlockDetector.evaluate(
                        resp.status_code, resp.text, dict(resp.headers)
                    )
                    if is_blocked:
                        self.rate_limiter.mark_domain_blocked(domain)
                        break

                    if resp.status_code != 200:
                        break

                    data = resp.json()
                    items = data.get("data", [])
                    for item in items:
                        job_id = str(item.get("slug") or item.get("id") or "")
                        raw_results.append(
                            RawResult(
                                source=self.name,
                                source_job_id=job_id,
                                fetch_method="api",
                                payload=item,
                                url=item.get("url") or page_url,
                                status_code=resp.status_code,
                                headers=dict(resp.headers),
                            )
                        )
                    # Next page link
                    page_url = data.get("links", {}).get("next")
            except Exception:
                break

        return raw_results

    def parse(self, raw: RawResult) -> List[NormalizedJob]:
        item = raw.payload
        if not isinstance(item, dict):
            return []

        title = item.get("title", "").strip()
        company = item.get("company_name", "").strip()
        if not title or not company:
            return []

        raw_loc = item.get("location") or ""
        remote = item.get("remote", False)
        location = "Remote" if (remote or "remote" in raw_loc.lower()) else (raw_loc.strip() or "Unspecified")

        # Seniority extraction heuristic
        seniority = None
        title_lower = title.lower()
        if any(w in title_lower for w in ["junior", "entry", "intern", "associate", "graduate"]):
            seniority = "entry"
        elif any(w in title_lower for w in ["lead", "principal", "architect", "staff", "head of", "director"]):
            seniority = "lead"
        elif any(w in title_lower for w in ["senior", "sr."]):
            seniority = "senior"
        elif any(w in title_lower for w in ["mid", "intermediate"]) or ("developer" in title_lower or "engineer" in title_lower):
            seniority = "mid"

        # Posted date formatting
        posted_date = None
        created_at = item.get("created_at")
        if created_at:
            try:
                # Can be epoch or ISO
                if isinstance(created_at, (int, float)):
                    posted_date = datetime.fromtimestamp(created_at, tz=timezone.utc).date().isoformat()
                else:
                    posted_date = str(created_at)[:10]
            except Exception:
                pass

        # Calculate confidence heuristic
        description = item.get("description") or ""
        confidence = 0.5
        if title: confidence += 0.15
        if company: confidence += 0.15
        if location: confidence += 0.1
        if description: confidence += 0.1
        confidence = min(round(confidence, 2), 1.0)

        job = NormalizedJob(
            source=self.name,
            source_job_id=raw.source_job_id,
            title=title,
            company=company,
            location=location,
            seniority=seniority,
            salary_range=None,
            description=description,
            apply_url=item.get("url") or raw.url,
            posted_date=posted_date,
            scraped_at=datetime.now(timezone.utc).isoformat(),
            fetch_method="api",
            confidence=confidence,
        )
        return [job]
