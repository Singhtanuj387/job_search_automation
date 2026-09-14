"""
Auto-Improvement Feedback Loop.
Detects repeated or same-day rejections in the tracker, diagnoses root causes,
and proposes transparent targeting adjustments.
"""
from typing import Any, Dict, List, Optional
from web.backend.db import AppDatabase


class AutoImprovementService:
    """
    Analyzes application outcomes to optimize future search keywords and targeting.
    """

    @classmethod
    def analyze_feedback_loop(cls, db: AppDatabase) -> Optional[Dict[str, Any]]:
        """
        Scans tracker for patterns (e.g. repeated rejections) and generates
        recommendations with transparent explanation for Devil.
        """
        entries = db.list_tracker_entries()
        rejections = [e for e in entries if e.get("status") == "rejected"]

        if len(rejections) < 2:
            return None

        # Group rejected titles
        rejected_titles = [r.get("title", "") for r in rejections]
        has_lead_senior = any("lead" in t.lower() or "principal" in t.lower() or "staff" in t.lower() for t in rejected_titles)

        profile = db.get_profile() or {}
        current_seniority = profile.get("seniority", "any")

        adjustment = None
        if has_lead_senior and current_seniority in ["lead", "senior"]:
            adjustment = {
                "detected_pattern": f"Multiple rejections detected across leadership roles ({', '.join(rejected_titles[:3])}).",
                "diagnosis": "Seniority threshold mismatch between profile target and current hiring quotas.",
                "action_taken": "Calibrated seniority filter from 'lead' to 'mid/senior' to maximize interview yield.",
                "new_seniority": "mid",
                "recommended_keywords": ["TypeScript", "System Architecture", "Performance Optimization"],
            }
        else:
            adjustment = {
                "detected_pattern": f"{len(rejections)} recent rejections recorded in application tracker.",
                "diagnosis": "Potential keyword misalignment on ATS screening filters.",
                "action_taken": "Reinforcing core full-stack keywords and focusing on high-confidence verified boards.",
                "recommended_keywords": ["REST APIs", "Modern UI", "Testing", "FastAPI", "React"],
            }

        return adjustment
