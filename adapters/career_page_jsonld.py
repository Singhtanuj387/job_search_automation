"""
Tier B Adapter for Direct Career Pages and Structured Data (schema.org/JobPosting in JSON-LD).
Extracts public structured job postings from career sites without anti-scraping blocks.
"""
from datetime import datetime, timezone
import json
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import httpx

from core.adapter_base import BaseAdapter
from core.block_detector import BlockDetector
from core.models import NormalizedJob, QueryConfig, RawResult
from core.politeness import DomainRateLimiter

SAMPLE_STRUCTURED_SOURCES = [
    # Permissive career pages and job boards embedding JSON-LD
    "https://jobs.lever.co/spotify",
]


class CareerPageJsonLdAdapter(BaseAdapter):
    name = "career_jsonld"
    tier = "B"
    base_url = "https://jobs.lever.co"

    def __init__(
        self,
        rate_limiter: Optional[DomainRateLimiter] = None,
        target_urls: Optional[List[str]] = None,
        proxy_url: Optional[str] = None,
    ):
        self.rate_limiter = rate_limiter or DomainRateLimiter()
        self.target_urls = target_urls or SAMPLE_STRUCTURED_SOURCES
        self.proxy_url = proxy_url
        self.client_kwargs: Dict[str, Any] = {
            "timeout": 15.0,
            "follow_redirects": True,
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        }
        if self.proxy_url:
            self.client_kwargs["proxy"] = self.proxy_url

    def health_check(self) -> Dict[str, Any]:
        domain = self.get_domain()
        if self.rate_limiter.is_domain_blocked(domain):
            return {"status": "blocked", "evidence": "Domain marked blocked in rate limiter"}

        test_url = self.target_urls[0] if self.target_urls else "https://jobs.lever.co/spotify"
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
                    soup = BeautifulSoup(resp.text, "html.parser")
                    scripts = soup.find_all("script", type="application/ld+json")
                    return {
                        "status": "ok",
                        "evidence": f"200 OK, detected {len(scripts)} JSON-LD structured blocks on page",
                    }
                else:
                    return {
                        "status": "degraded",
                        "evidence": f"Health check returned HTTP {resp.status_code}",
                    }
        except Exception as e:
            return {"status": "degraded", "evidence": f"Health check failed: {str(e)}"}

    def fetch(self, query: QueryConfig) -> List[RawResult]:
        raw_results: List[RawResult] = []

        for target_url in self.target_urls:
            from urllib.parse import urlparse
            domain = urlparse(target_url).netloc
            if self.rate_limiter.is_domain_blocked(domain):
                continue

            try:
                self.rate_limiter.wait_if_needed(domain)
                with httpx.Client(**self.client_kwargs) as client:
                    resp = client.get(target_url)
                    is_blocked, block_type, evidence = BlockDetector.evaluate(
                        resp.status_code, resp.text, dict(resp.headers)
                    )
                    if is_blocked:
                        self.rate_limiter.mark_domain_blocked(domain)
                        continue

                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    scripts = soup.find_all("script", type="application/ld+json")
                    for idx, s in enumerate(scripts):
                        text = (s.string or "").strip()
                        if not text:
                            continue
                        try:
                            data = json.loads(text)
                            items = data if isinstance(data, list) else [data]
                            for item_idx, item in enumerate(items):
                                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                                    job_id = str(item.get("identifier") or f"{domain}_{idx}_{item_idx}")
                                    raw_results.append(
                                        RawResult(
                                            source=self.name,
                                            source_job_id=job_id,
                                            fetch_method="structured_data",
                                            payload=item,
                                            url=target_url,
                                            status_code=resp.status_code,
                                            headers=dict(resp.headers),
                                        )
                                    )
                        except Exception:
                            continue
            except Exception:
                continue

        return raw_results

    def parse(self, raw: RawResult) -> List[NormalizedJob]:
        item = raw.payload
        if not isinstance(item, dict):
            return []

        title = (item.get("title") or "").strip()
        hiring_org = item.get("hiringOrganization") or {}
        company = (hiring_org.get("name") if isinstance(hiring_org, dict) else str(hiring_org)).strip()

        if not title or not company:
            return []

        # Location extraction from JobPosting Place/PostalAddress
        location = "Unspecified"
        job_loc = item.get("jobLocation")
        if isinstance(job_loc, dict):
            addr = job_loc.get("address")
            if isinstance(addr, dict):
                parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                location = ", ".join([p for p in parts if p])
            elif addr:
                location = str(addr)
        elif isinstance(job_loc, list) and job_loc:
            first = job_loc[0]
            if isinstance(first, dict):
                addr = first.get("address", {})
                if isinstance(addr, dict):
                    parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                    location = ", ".join([p for p in parts if p])

        if item.get("jobLocationType") == "TELECOMMUTE" or "remote" in title.lower():
            location = "Remote" if location == "Unspecified" else f"Remote ({location})"

        # Salary extraction
        salary_range = None
        base_sal = item.get("baseSalary")
        if isinstance(base_sal, dict):
            val = base_sal.get("value")
            curr = base_sal.get("currency") or "$"
            if isinstance(val, dict):
                min_v = val.get("minValue")
                max_v = val.get("maxValue")
                if min_v and max_v:
                    salary_range = f"{curr}{min_v} - {curr}{max_v}"
                elif min_v:
                    salary_range = f"{curr}{min_v}+"

        # Description extraction
        desc_html = item.get("description") or ""
        soup = BeautifulSoup(desc_html, "html.parser")
        description = soup.get_text(separator="\n").strip()

        # Seniority extraction
        seniority = None
        title_lower = title.lower()
        if any(w in title_lower for w in ["junior", "entry", "intern"]):
            seniority = "entry"
        elif any(w in title_lower for w in ["lead", "principal", "architect", "staff"]):
            seniority = "lead"
        elif any(w in title_lower for w in ["senior", "sr."]):
            seniority = "senior"
        elif any(w in title_lower for w in ["mid", "developer", "engineer"]):
            seniority = "mid"

        # Posted date
        posted_date = None
        dp = item.get("datePosted")
        if dp:
            posted_date = str(dp)[:10]

        confidence = 0.6
        if title: confidence += 0.15
        if company: confidence += 0.15
        if location: confidence += 0.1
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
            fetch_method="structured_data",
            confidence=confidence,
        )
        return [job]
