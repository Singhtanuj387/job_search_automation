"""
Application Tracker and Feedback Loop API Routes.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from web.backend.auto_improve import AutoImprovementService
from web.backend.db import AppDatabase
from web.backend.gmail_service import GmailService
from web.backend.session import get_client_id

router = APIRouter(prefix="/api/tracker", tags=["Tracker"])
db = AppDatabase()


class AddTrackerRequest(BaseModel):
    job_id: str
    company: str
    title: str
    location: str
    apply_url: str
    status: str = "found"
    source: str = ""
    notes: str = ""


class UpdateTrackerStatusRequest(BaseModel):
    status: str
    notes: Optional[str] = None


@router.get("")
def get_tracker(client_id: str = Depends(get_client_id)):
    return db.list_tracker_entries(client_id=client_id)


@router.post("")
def add_to_tracker(req: AddTrackerRequest, client_id: str = Depends(get_client_id)):
    res = db.add_tracker_entry(
        job_id=req.job_id,
        company=req.company,
        title=req.title,
        location=req.location,
        apply_url=req.apply_url,
        status=req.status,
        source=req.source,
        notes=req.notes,
        client_id=client_id,
    )
    return res


@router.patch("/{entry_id}")
def update_status(entry_id: int, req: UpdateTrackerStatusRequest, client_id: str = Depends(get_client_id)):
    updated = db.update_tracker_status(entry_id, req.status, notes=req.notes, client_id=client_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Tracker entry not found.")
    return {"status": "ok", "entry_id": entry_id, "new_status": req.status}


@router.get("/auto-improve")
def get_auto_improvement_diagnostics():
    analysis = AutoImprovementService.analyze_feedback_loop(db)
    return {"has_recommendations": analysis is not None, "analysis": analysis}


@router.get("/gmail-query-preview")
def get_gmail_query_preview():
    """Returns the strict privacy query that would be issued to Gmail."""
    q = GmailService.build_privacy_query(db)
    return {
        "privacy_query": q or "(No companies in tracker to query)",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "description": "Restricted exclusively to company senders matching applications in your tracker.",
    }
