"""
Automate and Nightly Scheduler API Routes.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from web.backend.db import AppDatabase
from web.backend.scheduler import AutomateScheduler
from web.backend.session import get_client_id

router = APIRouter(prefix="/api/automate", tags=["Automate"])
db = AppDatabase()
scheduler_instance = AutomateScheduler(db)


class AutomateConfigRequest(BaseModel):
    enabled: bool
    schedule_time: str = "08:00"
    report_delivery: str = "chat"


@router.get("/config")
def get_config(client_id: str = Depends(get_client_id)):
    return db.get_automate_config(client_id=client_id)


@router.post("/config")
def save_config(req: AutomateConfigRequest, client_id: str = Depends(get_client_id)):
    saved = db.save_automate_config(
        enabled=req.enabled,
        schedule_time=req.schedule_time,
        report_delivery=req.report_delivery,
        client_id=client_id,
    )
    scheduler_instance.reschedule()
    return saved


@router.post("/run-now")
def run_now(client_id: str = Depends(get_client_id)):
    result = scheduler_instance.run_scheduled_job(client_id=client_id)
    return {
        "status": "ok",
        "message": "Automated run executed successfully.",
        "results_count": result.get("total_found", 0),
        "run_id": result.get("run_id"),
    }
