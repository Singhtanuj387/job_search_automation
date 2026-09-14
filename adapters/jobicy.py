"""
Tier A Adapter for Jobicy Public Remote Jobs API.
Endpoint: https://jobicy.com/api/v2/remote-jobs
"""
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
import httpx

from core.adapter_base import BaseAdapter
from core.block_detector import BlockDetector
from core.models import NormalizedJob, QueryConfig, RawResult
from core.politeness import DomainRateLimiter


class JobicyAdapter(BaseAdapter):
    name = "jobicy"
    tier = "A"
    base_url = "https://jobicy.com/api/v2/remote-jobs"

    def __init__(
        self,
        rate_limiter: Optional[DomainRateLimiter] = None,
        proxy_url: Optional[str] = None,
    ):
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.proxy_url = proxy_url
        self.client_kwargs: Dict[str, Any] = {
            "timeout": 14.0,
            "follow_redirects": True,
            "headers": {
                "User-Agent": "JobSearchEngineBot/1.0 (+https://github.com/morningstar/job_search_automation)",
                "Accept": "application/json",
            },
        }
        if self.proxy_url:
            self.client_kwargs["proxy"] = self.proxy_url

    def health_check(self) -> Dict[str, Any]:
        domain = self.get_domain()
        if self.rate_limiter.is_domain_blocked(domain):
            return {"status": "blocked", "evidence": "Domain marked blocked in rate limiter"}

        test_url = f"{self.base_url}?count=2"
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
                    data = resp.json()
                    return {
                        "status": "ok",
                        "evidence": f"200 OK, retrieved {data.get('jobCount', 0)} jobs from feed",
                    }
                else:
                    return {
                        "status": "degraded",
                        "evidence": f"Jobicy health probe returned HTTP {resp.status_code}",
                    }
        except Exception as e:
            return {"status": "degraded", "evidence": f"Health check failed: {str(e)}"}

    def fetch(self, query: QueryConfig) -> List[RawResult]:
        domain = self.get_domain()
        if self.rate_limiter.is_domain_blocked(domain):
            return []

        search_term = query.role.replace(" ", "+")
        url = f"{self.base_url}?count=50&tag={search_term}"

        raw_results: List[RawResult] = []
        try:
            self.rate_limiter.wait_if_needed(domain)
            with httpx.Client(**self.client_kwargs) as client:
                resp = client.get(url)
                is_blocked, block_type, evidence = BlockDetector.evaluate(
                    resp.status_code, resp.text, dict(resp.headers)
                )
                if is_blocked:
                    self.rate_limiter.mark_domain_blocked(domain)
                    return []

                if resp.status_code != 200:
                    return []

                data = resp.json()
                jobs = data.get("jobs", [])
                for j in jobs:
                    job_id = str(j.get("id"))
                    raw_results.append(
                        RawResult(
                            source=self.name,
                            source_job_id=job_id,
                            fetch_method="api",
                            payload=j,
                            url=j.get("url") or url,
                            status_code=resp.status_code,
                            headers=dict(resp.headers),
                        )
                    )
        except Exception:
            pass

        return raw_results

    def parse(self, raw: RawResult) -> List[NormalizedJob]:
        item = raw.payload
        if not isinstance(item, dict):
            return []

        title = (item.get("jobTitle") or "").strip()
        company = (item.get("companyName") or "").strip()
        if not title or not company:
            return []

        geo = item.get("jobGeo") or "Anywhere"
        location = f"Remote ({geo})" if geo else "Remote"

        # Salary formatting
        salary_range = None
        s_min = item.get("salaryMin")
        s_max = item.get("salaryMax")
        s_curr = item.get("salaryCurrency") or "$"
        if s_min or s_max:
            if s_min and s_max:
                salary_range = f"{s_curr}{s_min:,} - {s_curr}{s_max:,}"
            elif s_min:
                salary_range = f"From {s_curr}{s_min:,}"
            elif s_max:
                salary_range = f"Up to {s_curr}{s_max:,}"

        # Clean HTML description
        desc_raw = item.get("jobDescription") or item.get("jobExcerpt") or ""
        desc_clean = re.sub(r"<[^>]+>", " ", desc_raw)
        description = " ".join(desc_clean.split())

        # Seniority mapping
        seniority = None
        level_raw = (item.get("jobLevel") or "").lower()
        if "senior" in level_raw or "sr" in level_raw:
            seniority = "senior"
        elif "entry" in level_raw or "junior" in level_raw:
            seniority = "entry"
        elif "lead" in level_raw or "director" in level_raw:
            seniority = "lead"
        elif "mid" in level_raw:
            seniority = "mid"
        else:
            title_lower = title.lower()
            if any(w in title_lower for w in ["junior", "entry", "intern"]):
                seniority = "entry"
            elif any(w in title_lower for w in ["lead", "principal", "architect"]):
                seniority = "lead"
            elif any(w in title_lower for w in ["senior", "sr."]):
                seniority = "senior"
            elif any(w in title_lower for w in ["mid", "developer", "engineer"]):
                seniority = "mid"

        # Posted date
        posted_date = None
        pub_date = item.get("pubDate")
        if pub_date:
            posted_date = str(pub_date)[:10]

        confidence = 0.55
        if title: confidence += 0.15
        if company: confidence += 0.15
        if location: confidence += 0.1
        if salary_range: confidence += 0.05
        confidence = min(round(confidence, 2), 1.0)

        job = NormalizedJob(
            source=self.name,
            source_job_id=raw.source_job_id,
            title=title,
            company=company,
            location=location,
            seniority=seniority,
            salary_range=salary_range,
            description=description,
            apply_url=item.get("url") or raw.url,
            posted_date=posted_date,
            scraped_at=datetime.now(timezone.utc).isoformat(),
            fetch_method="api",
            confidence=confidence,
        )
        return [job]
