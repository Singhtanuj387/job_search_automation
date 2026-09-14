"""
Materials Download Routes for Application ZIP bundles and individual DOCX files.
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/materials", tags=["Materials"])
MATERIALS_BASE = Path("data/materials")


@router.get("/{run_id}/zip")
def download_zip(run_id: str):
    run_dir = MATERIALS_BASE / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run materials folder not found.")

    zip_files = list(run_dir.glob("*_Applications_*.zip"))
    if not zip_files:
        raise HTTPException(status_code=404, detail="ZIP bundle not found for this run.")

    zip_path = zip_files[0]
    return FileResponse(
        path=str(zip_path),
        filename=zip_path.name,
        media_type="application/zip",
    )


@router.get("/{run_id}/resume/{job_id}")
def download_resume(run_id: str, job_id: str):
    run_dir = MATERIALS_BASE / run_id
    resume_path = run_dir / f"{job_id}_resume.docx"
    if not resume_path.exists():
        raise HTTPException(status_code=404, detail=f"Resume for job {job_id} not found.")

    return FileResponse(
        path=str(resume_path),
        filename=f"Resume_{job_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/{run_id}/cover-letter/{job_id}")
def download_cover_letter(run_id: str, job_id: str):
    run_dir = MATERIALS_BASE / run_id
    letter_path = run_dir / f"{job_id}_letter.docx"
    if not letter_path.exists():
        raise HTTPException(status_code=404, detail=f"Cover letter for job {job_id} not found.")

    return FileResponse(
        path=str(letter_path),
        filename=f"CoverLetter_{job_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
