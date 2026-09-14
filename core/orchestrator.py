"""
Acquisition Engine Orchestrator.
Coordinates adapters, handles SQLite resumable queuing, health reporting,
and fuzzy deduplication.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from adapters import ALL_ADAPTERS
from core.adapter_base import BaseAdapter
from core.dedup import deduplicate_jobs
from core.logger import get_structured_logger, log_event
from core.models import NormalizedJob, QueryConfig, RawResult
from core.politeness import DomainRateLimiter
from core.storage import RunStorage


ADAPTER_DOMAINS: Dict[str, str] = {
    # 1. Indian Job Portals
    "naukri": "naukri.com",
    "linkedin": "in.linkedin.com",
    "instahyre": "instahyre.com",
    "cutshort": "cutshort.io",
    "hirist": "hirist.tech",
    "indeed": "in.indeed.com",
    "foundit": "foundit.in",
    "shine": "shine.com",
    "timesjobs": "timesjobs.com",
    "glassdoor": "glassdoor.co.in",
    # 2. Startup & Remote Platforms
    "wellfound": "wellfound.com",
    "weworkremotely": "weworkremotely.com",
    # 3. Direct ATS & Global Platforms
    "greenhouse": "boards.greenhouse.io",
    "lever": "jobs.lever.co",
    "arbeitnow": "arbeitnow.com",
    "jobicy": "jobicy.com",
    "remotive": "remotive.com",
    "career_jsonld": "careers.company.com",
}


class Orchestrator:
    """
    Central orchestrator executing multi-source job acquisition runs.
    """

    def __init__(
        self,
        storage: Optional[RunStorage] = None,
        rate_limiter: Optional[DomainRateLimiter] = None,
        logger: Optional[logging.Logger] = None,
        proxy_url: Optional[str] = None,
    ):
        self.storage = storage or RunStorage()
        self.rate_limiter = rate_limiter or DomainRateLimiter(proxy_url=proxy_url)
        self.logger = logger or get_structured_logger()
        self.proxy_url = proxy_url

    def _matches_query(self, job: NormalizedJob, query: QueryConfig) -> bool:
        """Evaluates whether a normalized job satisfies the query filters."""
        # 1. Role matching: tokenized match against title or description
        role_tokens = [t.lower() for t in query.role.split() if len(t) > 2]
        title_lower = job.title.lower()
        desc_lower = job.description.lower()

        # At least one major role token must appear in title or description
        if role_tokens:
            matches_title = any(t in title_lower for t in role_tokens)
            matches_desc = any(t in desc_lower for t in role_tokens)
            if not (matches_title or matches_desc):
                return False

        # 2. Location matching
        if query.location and query.location.lower() != "any":
            target_loc = query.location.lower()
            job_loc = job.location.lower()
            # Synonym mapping
            if target_loc in ["bangalore", "bengaluru"]:
                if not ("bangalore" in job_loc or "bengaluru" in job_loc or "remote" in job_loc):
                    return False
            elif target_loc == "remote":
                if "remote" not in job_loc:
                    return False
            else:
                if target_loc not in job_loc and "remote" not in job_loc:
                    return False

        # 3. Seniority matching
        if query.seniority and query.seniority != "any" and job.seniority:
            if query.seniority == "entry" and job.seniority not in ["entry", "any"]:
                return False
            if query.seniority == "mid" and job.seniority not in ["mid", "entry", "any"]:
                return False
            if query.seniority == "senior" and job.seniority not in ["senior", "lead", "principal", "staff", "any"]:
                return False
            if query.seniority in ["lead", "principal", "staff"] and job.seniority not in ["lead", "principal", "staff", "senior", "any"]:
                return False

        # 4. Keywords matching
        if query.keywords:
            for kw in query.keywords:
                kw_lower = kw.lower()
                if kw_lower not in title_lower and kw_lower not in desc_lower:
                    return False

        return True

    def run(
        self,
        query: QueryConfig,
        resume_run_id: Optional[str] = None,
        results_path: str = "results.json",
        report_path: str = "run_report.json",
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Executes a job acquisition run across enabled adapters.
        """
        start_time = datetime.now(timezone.utc)
        run_id = resume_run_id or self.storage.create_run(query)

        log_event(
            self.logger,
            logging.INFO,
            f"Starting acquisition run {run_id} for role '{query.role}' in '{query.location}'",
            "run_started",
            run_id=run_id,
            query=query.model_dump(),
        )

        # Instantiate adapters
        selected_sources = query.sources if query.sources else list(ALL_ADAPTERS.keys())
        active_adapters: Dict[str, BaseAdapter] = {}
        for src in selected_sources:
            if src in ALL_ADAPTERS:
                adapter_cls = ALL_ADAPTERS[src]
                if src == "greenhouse":
                    active_adapters[src] = adapter_cls(
                        rate_limiter=self.rate_limiter,
                        companies=query.companies or None,
                        proxy_url=self.proxy_url,
                    )
                elif src == "lever":
                    active_adapters[src] = adapter_cls(
                        rate_limiter=self.rate_limiter,
                        companies=query.companies or None,
                        proxy_url=self.proxy_url,
                    )
                else:
                    active_adapters[src] = adapter_cls(
                        rate_limiter=self.rate_limiter,
                        proxy_url=self.proxy_url,
                    )

        # Execute Health Checks
        health_report: Dict[str, Dict[str, Any]] = {}
        for src, adapter in active_adapters.items():
            log_event(
                self.logger,
                logging.INFO,
                f"Performing health check for adapter: {src}",
                "health_check_started",
                source=src,
            )
            hc = adapter.health_check()
            health_report[src] = hc
            log_event(
                self.logger,
                logging.INFO if hc["status"] == "ok" else logging.WARNING,
                f"Health check for {src}: {hc['status']} - {hc['evidence']}",
                "health_check_completed",
                source=src,
                status=hc["status"],
                evidence=hc["evidence"],
            )

        # Enqueue acquisition tasks if not resuming
        pending_tasks = self.storage.get_pending_tasks(run_id)
        if not pending_tasks:
            tasks_to_queue = []
            for src in active_adapters:
                if health_report[src]["status"] != "blocked":
                    tasks_to_queue.append({
                        "source": src,
                        "task_type": "fetch_jobs",
                        "payload": query.model_dump()
                    })
            self.storage.enqueue_tasks(run_id, tasks_to_queue)
            pending_tasks = self.storage.get_pending_tasks(run_id)

        all_raw_results: List[RawResult] = []
        all_parsed_jobs: List[NormalizedJob] = []
        source_counts: Dict[str, Dict[str, int]] = {
            src: {"fetched": 0, "parsed": 0, "matched": 0}
            for src in active_adapters
        }

        # Process Tasks
        for task in pending_tasks:
            task_id = task["task_id"]
            src = task["source"]
            adapter = active_adapters.get(src)

            if not adapter or health_report[src]["status"] == "blocked":
                self.storage.mark_task_status(task_id, "skipped", "Source blocked or unavailable")
                continue

            self.storage.mark_task_status(task_id, "in_progress")
            domain = ADAPTER_DOMAINS.get(src, f"{src}.com")
            loc_str = f" {query.location}" if query.location and query.location.lower() != "any" else ""
            site_query = f"site:{domain} \"{query.role}\"{loc_str}".strip()

            if progress_callback:
                try:
                    progress_callback({
                        "type": "source_searching",
                        "source": src,
                        "domain": domain,
                        "site_query": site_query,
                    })
                except Exception:
                    pass

            log_event(
                self.logger,
                logging.INFO,
                f"Executing fetch for adapter '{src}'",
                "fetch_started",
                source=src,
            )

            try:
                raw_list = adapter.fetch(query)
                source_counts[src]["fetched"] += len(raw_list)

                source_matched_jobs: List[NormalizedJob] = []
                for raw in raw_list:
                    self.storage.save_raw_result(run_id, raw)
                    all_raw_results.append(raw)

                    # Parse into normalized schema
                    parsed_jobs = adapter.parse(raw)
                    source_counts[src]["parsed"] += len(parsed_jobs)

                    for job in parsed_jobs:
                        if self._matches_query(job, query):
                            source_counts[src]["matched"] += 1
                            all_parsed_jobs.append(job)
                            source_matched_jobs.append(job)

                self.storage.mark_task_status(task_id, "completed")
                log_event(
                    self.logger,
                    logging.INFO,
                    f"Fetch complete for '{src}': {len(raw_list)} raw, {source_counts[src]['matched']} matched query",
                    "fetch_completed",
                    source=src,
                    counts=source_counts[src],
                )

                if progress_callback:
                    sample_preview = [
                        {
                            "title": j.title,
                            "company": j.company,
                            "location": j.location,
                            "domain": domain,
                            "url": j.apply_url,
                        }
                        for j in source_matched_jobs[:5]
                    ]
                    try:
                        progress_callback({
                            "type": "source_results",
                            "source": src,
                            "domain": domain,
                            "site_query": site_query,
                            "count": len(source_matched_jobs),
                            "jobs": sample_preview,
                        })
                    except Exception:
                        pass
            except Exception as e:
                self.storage.mark_task_status(task_id, "failed", str(e))
                log_event(
                    self.logger,
                    logging.ERROR,
                    f"Error running adapter '{src}': {str(e)}",
                    "adapter_failed",
                    source=src,
                    exception=str(e),
                )

        # Deduplication
        unique_jobs, dedup_metrics = deduplicate_jobs(all_parsed_jobs)

        # Save to SQLite and export files
        self.storage.save_normalized_jobs(run_id, unique_jobs)
        self.storage.update_run_status(run_id, "completed")

        end_time = datetime.now(timezone.utc)
        duration_seconds = round((end_time - start_time).total_seconds(), 2)

        # Write results.json
        out_path = Path(results_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([j.model_dump() for j in unique_jobs], f, indent=2)

        # Build run_report.json
        run_report = {
            "run_id": run_id,
            "timestamp": end_time.isoformat(),
            "duration_seconds": duration_seconds,
            "query": query.model_dump(),
            "sources_health": health_report,
            "source_metrics": source_counts,
            "deduplication": dedup_metrics,
            "results_count": len(unique_jobs),
            "output_file": str(out_path),
        }

        rep_path = Path(report_path)
        rep_path.parent.mkdir(parents=True, exist_ok=True)
        with open(rep_path, "w", encoding="utf-8") as f:
            json.dump(run_report, f, indent=2)

        log_event(
            self.logger,
            logging.INFO,
            f"Run completed in {duration_seconds}s. Found {len(unique_jobs)} unique jobs (pruned {dedup_metrics['duplicates_pruned']}). Output: {out_path}",
            "run_completed",
            run_id=run_id,
            metrics=dedup_metrics,
        )

        return run_report
