"""
Gmail Readonly Integration with Strict Privacy Query Narrowing.
Queries ONLY for senders matching companies in the application tracker,
never performing general inbox scans.
"""
import re
from typing import Any, Dict, List, Optional
from web.backend.db import AppDatabase


class GmailService:
    """
    Manages privacy-scoped email queries for tracked job applications.
    """

    @classmethod
    def build_privacy_query(cls, db: AppDatabase) -> str:
        """
        Builds a query string restricted ONLY to companies in the user's tracker.
        e.g. 'from:(*canonical* OR *stripe* OR *spotify*) (interview OR application OR offer OR reject OR update)'
        """
        entries = db.list_tracker_entries()
        companies = set()
        for e in entries:
            comp = e.get("company", "").strip()
            if comp and len(comp) > 1:
                clean_comp = re.sub(r"[^\w]", "", comp.lower())
                companies.add(clean_comp)

        if not companies:
            return ""

        comp_clauses = [f"from:*{c}*" for c in sorted(companies)[:25]]
        query = f"({' OR '.join(comp_clauses)}) (status OR interview OR application OR rejection OR offer)"
        return query

    @classmethod
    def classify_email(cls, subject: str, body: str) -> Dict[str, Any]:
        """
        Classifies email content into rejection, interview_invite, assessment, or other.
        """
        text = f"{subject} {body}".lower()

        if any(w in text for w in ["interview", "invitation to interview", "schedule a chat", "speak with the team", "next round"]):
            return {
                "category": "interview_invite",
                "label": "Interview Invitation",
                "suggested_status": "interview",
                "confidence": 0.95,
            }

        if any(w in text for w in ["unfortunately", "not moving forward", "other candidates", "pursue other", "decided to move forward with other", "regret to inform"]):
            return {
                "category": "rejection",
                "label": "Rejection Notice",
                "suggested_status": "rejected",
                "confidence": 0.92,
            }

        if any(w in text for w in ["assessment", "take-home", "coding challenge", "hackerrank", "codesignal", "technical task"]):
            return {
                "category": "assessment",
                "label": "Technical Assessment",
                "suggested_status": "interview",
                "confidence": 0.90,
            }

        if any(w in text for w in ["offer", "pleased to offer", "offer letter"]):
            return {
                "category": "offer",
                "label": "Job Offer",
                "suggested_status": "offer",
                "confidence": 0.98,
            }

        return {
            "category": "other",
            "label": "Application Update",
            "suggested_status": "applied",
            "confidence": 0.70,
        }
