"""
API Routes for Resume Tailoring and Tailored Resume Downloads.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from web.backend.db import AppDatabase
from web.backend.resume_tailor import ResumeTailorService
from web.backend.session import get_client_id

router = APIRouter(prefix="/api/resume", tags=["Resume Tailor"])
db = AppDatabase()
tailor_service = ResumeTailorService(db=db)


class TailorRequest(BaseModel):
    job_id: Optional[str] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    job_description: Optional[str] = None
    opportunity_id: Optional[int] = None


@router.post("/tailor")
def tailor_resume(req: TailorRequest, client_id: str = Depends(get_client_id)):
    """
    Tailors the candidate's uploaded resume for the target job.
    Uses Resume Matcher keyword extraction and configured LLM provider.
    """
    job_id = req.job_id or ""
    title = req.job_title or ""
    company = req.company or ""
    desc = req.job_description or ""
    opp_id = req.opportunity_id

    # If opportunity_id is given but title/company/description are missing, fetch from DB
    if opp_id and (not title or not company or not desc):
        opp = db.get_opportunity(opp_id)
        if opp:
            title = title or opp.get("title", "")
            company = company or opp.get("company", "")
            job_id = job_id or opp.get("source_job_id", "") or f"opp-{opp_id}"
            if not desc:
                # Try raw_json or match_explanation
                try:
                    import json
                    raw = json.loads(opp.get("raw_json") or "{}")
                    desc = raw.get("description") or opp.get("match_explanation") or f"{title} at {company}"
                except Exception:
                    desc = opp.get("match_explanation") or f"{title} at {company}"

    if not title:
        title = "Software Engineer"
    if not company:
        company = "Target Employer"
    if not desc:
        desc = f"Looking for an experienced {title} at {company}."

    try:
        result = tailor_service.tailor_resume(
            job_id=job_id,
            job_title=title,
            company=company,
            job_description=desc,
            session_id=client_id,
            opportunity_id=opp_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume tailoring failed: {str(e)}")


@router.get("/tailored")
def list_tailored_resumes(client_id: str = Depends(get_client_id)):
    """Lists all tailored resumes for the current session."""
    return db.list_tailored_resumes(session_id=client_id)


@router.get("/tailored/by-job")
def get_tailored_by_job(
    job_id: Optional[str] = Query(None),
    opportunity_id: Optional[int] = Query(None),
    company: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    client_id: str = Depends(get_client_id),
):
    """Checks if a tailored resume exists for a job."""
    res = db.get_tailored_resume_for_job(
        job_id=job_id or "",
        opportunity_id=opportunity_id,
        company=company or "",
        title=title or "",
        session_id=client_id,
    )
    if not res:
        return {"has_tailored": False, "tailored_resume": None}
    
    download_url = f"/api/resume/tailored/{res['id']}/download"
    return {
        "has_tailored": True,
        "tailored_resume": {
            **res,
            "download_url": download_url,
        }
    }


@router.get("/tailored/{record_id}")
def get_tailored_resume(record_id: int, client_id: str = Depends(get_client_id)):
    """Retrieves metadata and keyword analysis for a tailored resume."""
    res = db.get_tailored_resume_by_id(record_id)
    if not res:
        raise HTTPException(status_code=404, detail="Tailored resume not found")
    res["download_url"] = f"/api/resume/tailored/{record_id}/download"
    return res


@router.get("/tailored/{record_id}/download")
def download_tailored_docx(record_id: int, client_id: str = Depends(get_client_id)):
    """Downloads the tailored DOCX resume file."""
    res = db.get_tailored_resume_by_id(record_id)
    if not res:
        raise HTTPException(status_code=404, detail="Tailored resume not found")

    docx_path = res.get("tailored_docx_path")
    if not docx_path or not os.path.exists(docx_path):
        raise HTTPException(status_code=404, detail="Tailored resume document file not found on disk")

    filename = Path(docx_path).name
    return FileResponse(
        path=docx_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.delete("/tailored/{record_id}")
def delete_tailored_resume(record_id: int, client_id: str = Depends(get_client_id)):
    """Deletes a tailored resume record."""
    success = db.delete_tailored_resume(record_id, session_id=client_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tailored resume not found or already deleted")
    return {"status": "ok", "message": "Tailored resume removed."}
