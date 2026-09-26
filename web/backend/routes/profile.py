"""
Profile and Resume Upload API Routes.
"""
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from web.backend.db import AppDatabase
from web.backend.resume_extractor import ResumeExtractor
from web.backend.resume_parser import ResumeParser
from web.backend.session import get_client_id

router = APIRouter(prefix="/api/profile", tags=["Profile"])
db = AppDatabase()


class ProfileUpdateRequest(BaseModel):
    role: str
    location: str = "any"
    seniority: str = "any"
    resume_text: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    notice_period: Optional[str] = None
    expected_ctc_lpa: Optional[str] = None
    company_type: Optional[str] = None
    job_type: Optional[str] = "Full-time"
    resume_filename: Optional[str] = None
    resume_uploaded_at: Optional[str] = None
    skills: Optional[List[str]] = None


@router.get("")
def get_profile(client_id: str = Depends(get_client_id)):
    p = db.get_profile(session_id=client_id)
    if not p:
        return {"has_profile": False, "profile": None}
    return {"has_profile": True, "profile": p}


@router.post("")
def update_profile(req: ProfileUpdateRequest, client_id: str = Depends(get_client_id)):
    res = db.upsert_profile(
        role=req.role,
        location=req.location,
        seniority=req.seniority,
        resume_text=req.resume_text,
        name=req.name,
        email=req.email,
        phone=req.phone,
        linkedin_url=req.linkedin_url,
        notice_period=req.notice_period,
        expected_ctc_lpa=req.expected_ctc_lpa,
        company_type=req.company_type,
        job_type=req.job_type,
        resume_filename=req.resume_filename,
        resume_uploaded_at=req.resume_uploaded_at,
        skills=req.skills,
        session_id=client_id,
    )
    return {"status": "ok", "profile": res}


@router.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...), client_id: str = Depends(get_client_id)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected.")

    file_bytes = await file.read()
    try:
        saved_path, extracted_text = ResumeParser.process_upload(file.filename, file_bytes, session_id=client_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")

    # Extract contact info and skills from resume text
    current = db.get_profile(session_id=client_id) or {}
    extracted = ResumeExtractor.extract_all(extracted_text, current)
    skills = extracted.get("skills", [])
    now = datetime.now(timezone.utc).isoformat()

    target_role = (current.get("role") or "").strip() or extracted.get("current_title") or "Software Engineer"
    target_location = current.get("location") if (current.get("location") and current.get("location") != "any") else (extracted.get("location") or "any")

    updated = db.upsert_profile(
        role=target_role,
        location=target_location,
        seniority=current.get("seniority", "any"),
        resume_text=extracted_text,
        resume_file_path=saved_path,
        resume_filename=file.filename,
        resume_uploaded_at=now,
        skills=skills,
        name=extracted.get("full_name") or current.get("name", "Applicant"),
        email=extracted.get("email") or current.get("email", ""),
        phone=extracted.get("phone") or current.get("phone", ""),
        linkedin_url=extracted.get("linkedin_url") or current.get("linkedin_url", ""),
        notice_period=current.get("notice_period", "Immediate"),
        expected_ctc_lpa=current.get("expected_ctc_lpa", ""),
        company_type=current.get("company_type", "Any"),
        job_type=current.get("job_type", "Full-time"),
        session_id=client_id,
    )

    return {
        "status": "ok",
        "filename": file.filename,
        "extracted_length": len(extracted_text),
        "preview": extracted_text[:400] + ("..." if len(extracted_text) > 400 else ""),
        "skills": skills,
        "profile": updated,
    }


@router.get("/resume/download")
def download_profile_resume(client_id: str = Depends(get_client_id)):
    """Downloads the candidate's active uploaded resume file for their session."""
    p = db.get_profile(session_id=client_id) or {}
    file_path = p.get("resume_file_path", "")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="No active resume file found in profile.")

    filename = p.get("resume_filename") or Path(file_path).name
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.delete("/resume")
def delete_profile_resume(client_id: str = Depends(get_client_id)):
    """Clears the resume from the profile for this session."""
    updated = db.clear_profile_resume(session_id=client_id)
    return {
        "status": "ok",
        "message": "Resume successfully removed from profile.",
        "profile": updated,
    }

