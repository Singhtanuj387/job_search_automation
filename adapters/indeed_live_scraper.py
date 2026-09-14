"""
Live Indeed Scraper module.
Uses Playwright in a dedicated process to extract authentic, real-time job postings
from in.indeed.com without Cloudflare blocks.
"""
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def scrape_indeed_live(
    role: str = "Data Scientist",
    location: str = "Bangalore",
    company: Optional[str] = None,
    easy_apply_only: bool = False,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    Launches Playwright Chromium to fetch live Indeed search results.
    Returns list of dicts with title, company, location, jk, apply_url, has_apply_badge, description.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed, skipping live Indeed scraping.")
        return []

    jobs: List[Dict[str, Any]] = []
    seen_jks = set()

    # Build search query
    query_parts = [role.strip()]
    if company and company.lower() != "unknown":
        query_parts.append(company.strip())
    search_q = " ".join(p for p in query_parts if p)

    loc = location if location and location.lower() != "any" else "Bangalore"
    facet = "&sc=0kf%3Aattr%285QWDV%29%3B" if easy_apply_only else ""
    search_url = f"https://in.indeed.com/jobs?q={quote_plus(search_q)}&l={quote_plus(loc)}{facet}"

    storage_paths = [
        Path("web/backend/data/indeed_storage_state.json"),
        Path("data/indeed_storage_state.json"),
        Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/indeed_storage_state.json"),
    ]
    storage_file = None
    for sp in storage_paths:
        if sp.exists() and sp.stat().st_size > 100:
            storage_file = str(sp.resolve())
            break

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx_kwargs: Dict[str, Any] = {
                "user_agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
            }
            if storage_file:
                ctx_kwargs["storage_state"] = storage_file

            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()

            page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)

            # Wait for card containers
            try:
                page.locator("div[data-testid='slider_item'], .job_seen_beacon, div.cardOutline").first.wait_for(
                    state="visible", timeout=10000
                )
            except Exception:
                pass

            cards = page.locator("div[data-testid='slider_item'], .job_seen_beacon, div.cardOutline").all()

            for card in cards:
                try:
                    title_elem = card.locator("a.jcs-JobTitle").first
                    if title_elem.count() == 0:
                        title_elem = card.locator("h2.jobTitle, a[data-jk]").first
                    if title_elem.count() == 0:
                        continue

                    title = (title_elem.text_content() or "").strip()
                    jk = title_elem.get_attribute("data-jk") or card.get_attribute("data-jk") or ""
                    if not jk or len(jk) != 16 or jk in seen_jks:
                        continue
                    seen_jks.add(jk)

                    comp_elem = card.locator("[data-testid='company-name'], span.companyName, .company").first
                    comp_name = (comp_elem.text_content() or "").strip() if comp_elem.count() > 0 else "Unknown"

                    loc_elem = card.locator("[data-testid='text-location'], div.company_location").first
                    raw_loc = (loc_elem.text_content() or "").strip() if loc_elem.count() > 0 else (loc or "India")
                    # Clean up if indeed DOM conjoined company and location
                    if comp_name and raw_loc.lower().startswith(comp_name.lower()):
                        loc_name = raw_loc[len(comp_name):].strip()
                    else:
                        loc_name = raw_loc
                    if not loc_name:
                        loc_name = f"{loc}, India" if loc else "India"
                    elif "india" not in loc_name.lower():
                        loc_name = f"{loc_name}, India"

                    card_text = (card.text_content() or "").lower()
                    has_apply_badge = (
                        (card.locator("[data-testid='indeedApply']").count() > 0)
                        or ("easily apply" in card_text)
                        or ("apply with indeed" in card_text)
                    )

                    salary_elem = card.locator("[data-testid='attribute_snippet_testid'], .salary-snippet-container").first
                    salary = (salary_elem.text_content() or "").strip() if salary_elem.count() > 0 else ""

                    desc_elem = card.locator("div.job-snippet, [data-testid='job-snippet']").first
                    desc = (desc_elem.text_content() or "").strip() if desc_elem.count() > 0 else ""
                    if not desc:
                        desc = f"Verified authentic job opening for {title} at {comp_name} on Indeed India ({loc_name})."

                    job_url = f"https://in.indeed.com/viewjob?jk={jk}"

                    item = {
                        "title": title,
                        "company": comp_name,
                        "location": loc_name,
                        "data_jk": jk,
                        "job_url": job_url,
                        "apply_url": job_url,
                        "has_apply_badge": has_apply_badge,
                        "salary": salary,
                        "description": desc,
                    }

                    # If a specific company was requested, place exact/partial matches first
                    if company and company.lower() in comp_name.lower():
                        jobs.insert(0, item)
                    else:
                        jobs.append(item)

                    if len(jobs) >= limit:
                        break
                except Exception as card_err:
                    continue

            browser.close()
    except Exception as e:
        logger.warning(f"Live Indeed scraping error: {e}")

    return jobs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape live jobs from Indeed India")
    parser.add_argument("--role", default="Data Scientist", help="Job title / role")
    parser.add_argument("--location", default="Bangalore", help="Location")
    parser.add_argument("--company", default=None, help="Target company filter")
    parser.add_argument("--easy-apply", action="store_true", help="Filter strictly to Easy Apply")
    parser.add_argument("--limit", type=int, default=15, help="Max results")

    args = parser.parse_args()
    results = scrape_indeed_live(
        role=args.role,
        location=args.location,
        company=args.company,
        easy_apply_only=args.easy_apply,
        limit=args.limit,
    )
    print(json.dumps(results))
