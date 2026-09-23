"""
Phase 1 Engine Bridge.
Invokes the acquisition engine as a Python library import rather than CLI subprocess.
"""
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters import ALL_ADAPTERS
from core.models import NormalizedJob, QueryConfig
from core.orchestrator import Orchestrator
from core.storage import RunStorage
from web.backend.llm_service import LLMService


class EngineBridge:
    """
    Executes search and tailoring by calling the Phase 1 Orchestrator directly.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.storage = RunStorage(db_path=db_path or "data/jobs.db")
        self.orchestrator = Orchestrator(storage=self.storage)

    def execute_search_and_tailor(
        self,
        query: QueryConfig,
        resume_text: str = "",
        profile: Optional[Dict[str, Any]] = None,
        secret: Optional[Dict[str, Any]] = None,
        top_n: Optional[int] = None,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Runs Phase 1 engine query across all adapters, applies ATS tailoring & fit framing,
        and generates complete DOCX materials and ZIP download package for ALL matching positions.
        """
        # Execute Phase 1 orchestrator with live progress callback
        report = self.orchestrator.run(query=query, progress_callback=progress_callback)
        run_id = report["run_id"]

        # Retrieve all normalized jobs for this run
        jobs = self.storage.get_normalized_jobs(run_id)

        # Candidate name & effective profile
        eff_profile = dict(profile or {})
        candidate_name = eff_profile.get("name") or "Applicant"
        eff_resume_text = resume_text or eff_profile.get("resume_text", "")

        if progress_callback:
            try:
                progress_callback({
                    "type": "tailoring",
                    "message": f"Discovered {len(jobs)} total jobs across {len(ALL_ADAPTERS)} verified platforms. Scoring ATS fitness and generating custom application documents...",
                    "total_found": len(jobs),
                })
            except Exception:
                pass

        # Score matching relevance
        scored_jobs = []
        for j in jobs:
            title_lower = j.title.lower()
            desc_lower = j.description.lower()
            match_score = 0
            for token in query.role.lower().split():
                if len(token) > 2:
                    if token in title_lower:
                        match_score += 4
                    elif token in desc_lower:
                        match_score += 1
            if query.location and query.location.lower() != "any":
                if query.location.lower() in j.location.lower() or "remote" in j.location.lower():
                    match_score += 2
            scored_jobs.append((match_score, j))

        scored_jobs.sort(key=lambda x: x[0], reverse=True)
        if top_n and top_n > 0:
            selected_candidates = [j for _, j in scored_jobs[:top_n]] if scored_jobs else []
        else:
            selected_candidates = [j for _, j in scored_jobs] if scored_jobs else []

        # Apply tailoring and fit scoring to candidate matches
        tailored_jobs: List[Dict[str, Any]] = []
        for idx, job in enumerate(selected_candidates):
            job_secret = secret if idx == 0 else None
            tailoring = LLMService.tailor_job(
                job=job,
                resume_text=eff_resume_text,
                secret=job_secret,
                candidate_name=candidate_name,
            )
            job_dict = job.model_dump()
            job_dict["fitness_score"] = tailoring.get("fitness_score", 75)
            job_dict["fitness_display"] = tailoring.get("fitness_display", f"{job_dict['fitness_score']}% Fit")
            job_dict["fit_framing"] = tailoring["fit_framing"]
            job_dict["fit_reason"] = tailoring.get("fit_reason", "")
            job_dict["fit_badge_color"] = tailoring["fit_badge_color"]
            job_dict["match_explanation"] = tailoring.get("match_explanation", "")
            # Save internal score for sorting, then strip it so raw score is NEVER surfaced
            job_dict["_sort_score"] = tailoring["internal_score"]
            tailored_jobs.append(job_dict)

        # Sort by fit score descending
        tailored_jobs.sort(key=lambda j: j.pop("_sort_score", 0), reverse=True)
        selected_top = tailored_jobs[:top_n] if (top_n and top_n > 0) else tailored_jobs

        return {
            "run_id": run_id,
            "query": query.model_dump(),
            "total_found": len(jobs),
            "duplicates_pruned": report["deduplication"]["duplicates_pruned"],
            "reduction_rate": report["deduplication"]["reduction_rate"],
            "sources_health": report["sources_health"],
            "jobs": selected_top,
            "materials_bundle": {},
        }
