"""
Total Job Opportunities API Routes.
Exposes unique discovered opportunities catalog, statistics, search filtering,
and one-click save-to-tracker functionality.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from web.backend.db import AppDatabase
from web.backend.session import get_client_id

router = APIRouter(prefix="/api/opportunities", tags=["Opportunities"])
db = AppDatabase()


@router.get("")
def list_opportunities(
    q: Optional[str] = Query(None, description="Search keyword matching title, company, or skills"),
    source: Optional[str] = Query(None, description="Filter by source platform"),
    min_score: Optional[int] = Query(0, description="Filter by minimum fitness score"),
    limit: Optional[int] = Query(None, description="Pagination limit"),
    offset: Optional[int] = Query(0, description="Pagination offset"),
    client_id: str = Depends(get_client_id),
):
    """
    Returns list of all stored unique job opportunities sorted by fitness score and discovery date.
    """
    return db.list_opportunities(
        query=q or "",
        source=source or "",
        min_score=min_score or 0,
        limit=limit,
        offset=offset or 0,
        client_id=client_id,
    )


@router.get("/stats")
def get_opportunities_stats(client_id: str = Depends(get_client_id)):
    """
    Returns aggregate metrics on total unique opportunities, platform breakdown, and match tiers.
    """
    return db.get_opportunities_stats(client_id=client_id)


@router.get("/{opp_id}")
def get_opportunity(opp_id: int):
    """
    Returns details for a single job opportunity.
    """
    opp = db.get_opportunity(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp


@router.post("/{opp_id}/save-to-tracker")
def save_opportunity_to_tracker(opp_id: int, client_id: str = Depends(get_client_id)):
    """
    Saves an opportunity directly into the Application Tracker.
    """
    opp = db.get_opportunity(opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Check if already in tracker
    existing_tracker = db.list_tracker_entries(client_id=client_id)
    for item in existing_tracker:
        if item.get("apply_url") == opp.get("apply_url") or (
            item.get("company", "").lower() == opp.get("company", "").lower()
            and item.get("title", "").lower() == opp.get("title", "").lower()
        ):
            return {
                "status": "already_saved",
                "message": "Opportunity is already in Application Tracker.",
                "entry": item,
            }

    jid = opp.get("source_job_id") or f"{opp.get('source', 'job')[:3].upper()}-{opp['id']}"
    entry = db.add_tracker_entry(
        job_id=jid,
        company=opp.get("company", "Company"),
        title=opp.get("title", "Role"),
        location=opp.get("location", "Remote"),
        apply_url=opp.get("apply_url", ""),
        status="found",
        source=opp.get("source", "web"),
        notes=f"Saved from Total Job Opportunities ({opp.get('fitness_score', 75)}% Fit).",
        client_id=client_id,
    )
    return {
        "status": "ok",
        "message": "Opportunity saved to Application Tracker.",
        "entry": entry,
    }


@router.delete("")
def clear_all_opportunities(clear_found_tracker: bool = True, client_id: str = Depends(get_client_id)):
    """
    Clears all job opportunities from the catalog.
    If clear_found_tracker is True, also clears unapplied 'found' entries from the tracker
    while preserving applied/interviewing/offer entries.
    """
    res = db.clear_all_opportunities(clear_found_tracker=clear_found_tracker, client_id=client_id)
    return {
        "status": "ok",
        "message": f"Successfully cleared {res.get('opportunities_cleared', 0)} opportunities.",
        "details": res,
    }

