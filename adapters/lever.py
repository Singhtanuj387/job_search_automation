"""
Tier A Adapter for Lever ATS Public Postings API.
Endpoint: https://api.lever.co/v0/postings/{company}?mode=json
"""
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
import httpx

from core.adapter_base import BaseAdapter
from core.block_detector import BlockDetector
from core.models import NormalizedJob, QueryConfig, RawResult
from core.politeness import DomainRateLimiter

DEFAULT_LEVER_COMPANIES = [
    "spotify",
    "deliveroo",
    "twitch",
    "affirm",
]


class LeverAdapter(BaseAdapter):
    name = "lever"
    tier = "A"
    base_url = "https://api.lever.co/v0/postings"

    def __init__(
        self,
        rate_limiter: Optional[DomainRateLimiter] = None,
        companies: Optional[List[str]] = None,
        proxy_url: Optional[str] = None,
    ):
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.companies = companies or DEFAULT_LEVER_COMPANIES
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
        """Probes Lever API with Spotify board."""
        domain = self.get_domain()
        if self.rate_limiter.is_domain_blocked(domain):
            return {"status": "blocked", "evidence": "Domain marked blocked in rate limiter"}

        test_url = f"{self.base_url}/spotify?mode=json"
        try:
            self.rate_limiter.wait_if_needed(domain)
            with httpx.Client(**self.client_kwargs) as client:
                resp = client.get(test_url)
                is_blocked, block_type, evidence = BlockDetector.evaluate(
                    resp.status_code, resp.text, dict(resp.headers)
                )
                if is_blocked:
                    self.rate_limiter.mark_domain_blocked(domain)
                    return {"status": "blocked", "evidence": evidence}

                if resp.status_code == 200:
                    jobs = resp.json()
                    return {
                        "status": "ok",
                        "evidence": f"200 OK, verified public postings endpoint ({len(jobs)} jobs)",
                    }
                else:
                    return {
                        "status": "degraded",
                        "evidence": f"Lever test returned status {resp.status_code}",
                    }
        except Exception as e:
            return {"status": "degraded", "evidence": f"Health check failed: {str(e)}"}

    def fetch(self, query: QueryConfig) -> List[RawResult]:
        domain = self.get_domain()
        if self.rate_limiter.is_domain_blocked(domain):
            return []

        company_list = query.companies if query.companies else self.companies
        raw_results: List[RawResult] = []

        for comp in company_list:
            if self.rate_limiter.is_domain_blocked(domain):
                break
            url = f"{self.base_url}/{comp}?mode=json"
            try:
                self.rate_limiter.wait_if_needed(domain)
                with httpx.Client(**self.client_kwargs) as client:
                    resp = client.get(url)
                    is_blocked, block_type, evidence = BlockDetector.evaluate(
                        resp.status_code, resp.text, dict(resp.headers)
                    )
                    if is_blocked:
                        self.rate_limiter.mark_domain_blocked(domain)
                        break

                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    if isinstance(data, list):
                        for j in data:
                            job_id = str(j.get("id"))
                            raw_results.append(
                                RawResult(
                                    source=self.name,
                                    source_job_id=job_id,
                                    fetch_method="api",
                                    payload={"company_slug": comp, "job": j},
                                    url=j.get("hostedUrl") or url,
                                    status_code=resp.status_code,
                                    headers=dict(resp.headers),
                                )
                            )
            except Exception:
                continue

        return raw_results

    def parse(self, raw: RawResult) -> List[NormalizedJob]:
        payload = raw.payload
        if not isinstance(payload, dict):
            return []

        comp_slug = payload.get("company_slug", "")
        item = payload.get("job", {})
        title = (item.get("text") or "").strip()
        if not title:
            return []

        company = comp_slug.capitalize()
        cats = item.get("categories") or {}
        location = cats.get("location") or "Unspecified"
        if "remote" in title.lower() or "remote" in location.lower():
            location = "Remote"

        description = item.get("descriptionPlain") or item.get("description") or ""

        # Seniority heuristic
        seniority = None
        title_lower = title.lower()
        if any(w in title_lower for w in ["junior", "entry", "intern", "associate"]):
            seniority = "entry"
        elif any(w in title_lower for w in ["lead", "principal", "architect", "staff", "director"]):
            seniority = "lead"
        elif any(w in title_lower for w in ["senior", "sr."]):
            seniority = "senior"
        elif any(w in title_lower for w in ["mid", "intermediate"]) or ("developer" in title_lower or "engineer" in title_lower):
            seniority = "mid"

        # Posted date
        posted_date = None
        created_at = item.get("createdAt")
        if created_at:
            try:
                posted_date = datetime.fromtimestamp(created_at / 1000.0, tz=timezone.utc).date().isoformat()
            except Exception:
                pass

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
            apply_url=item.get("applyUrl") or item.get("hostedUrl") or raw.url,
            posted_date=posted_date,
            scraped_at=datetime.now(timezone.utc).isoformat(),
            fetch_method="api",
            confidence=confidence,
        )
        return [job]
