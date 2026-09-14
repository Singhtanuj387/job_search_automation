"""
Automated Nightly Scheduler for Job Acquisition.
Uses APScheduler in-process background scheduler to run nightly searches
and compile morning reports waiting in chat.
"""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None

from core.models import QueryConfig
from web.backend.db import AppDatabase
from web.backend.engine_bridge import EngineBridge

logger = logging.getLogger("automate_scheduler")


class AutomateScheduler:
    """
    Manages scheduled automated search runs.
    """

    def __init__(self, db: Optional[AppDatabase] = None):
        self.db = db or AppDatabase()
        self.bridge = EngineBridge()
        self.scheduler = BackgroundScheduler() if BackgroundScheduler else None
        self._is_running = False

    def start(self) -> None:
        if not self.scheduler:
            logger.warning("APScheduler not installed; automated background scheduling disabled.")
            return
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            self.reschedule()
            logger.info("AutomateScheduler started.")

    def shutdown(self) -> None:
        if self.scheduler and self._is_running:
            self.scheduler.shutdown()
            self._is_running = False

    def reschedule(self) -> None:
        """Reads config from DB and updates scheduled job."""
        if not self.scheduler:
            return
        cfg = self.db.get_automate_config()
        self.scheduler.remove_all_jobs()

        if not cfg.get("enabled"):
            logger.info("Automate scheduling is currently disabled.")
            return

        time_str = cfg.get("schedule_time", "08:00")
        try:
            hour, minute = [int(p) for p in time_str.split(":")]
        except Exception:
            hour, minute = 8, 0

        self.scheduler.add_job(
            self.run_scheduled_job,
            trigger="cron",
            hour=hour,
            minute=minute,
            id="nightly_automate_job",
            replace_existing=True,
        )
        logger.info(f"Nightly automate job scheduled for {hour:02d}:{minute:02d} daily.")

    def run_scheduled_job(self, client_id: str = "default") -> Dict[str, Any]:
        """Executes nightly job pipeline and prepares morning report."""
        logger.info(f"Executing scheduled nightly job acquisition for client_id={client_id}...")
        profile = self.db.get_profile(session_id=client_id) or {}
        role = profile.get("role", "Software Engineer")
        location = profile.get("location", "any")
        seniority = profile.get("seniority", "any")
        resume_text = profile.get("resume_text", "")

        query = QueryConfig(
            role=role,
            location=location,
            seniority=seniority,
        )

        secret = self.db.get_secret("llm_api_key", session_id=client_id)
        result = self.bridge.execute_search_and_tailor(
            query=query,
            resume_text=resume_text,
            secret=secret,
            top_n=10,
        )

        # Update last_run_at in DB
        now_str = datetime.now(timezone.utc).isoformat()
        with self.db._get_connection() as conn:
            conn.execute("UPDATE user_automate_config SET last_run_at = ? WHERE client_id = ?", (now_str, client_id))
            conn.commit()

        # Format Morning Report Chat Message
        jobs = result.get("jobs", [])
        total_found = result.get("total_found", 0)

        # Automatically persist all unique discovered opportunities
        if jobs:
            try:
                self.db.upsert_opportunities(jobs, client_id=client_id)
            except Exception:
                pass

        report_md = f"### 🌅 Morning Job Report — {datetime.now().strftime('%b %d, %Y')}\n\n"
        report_md += f"Automated acquisition ran for **{role}** ({location}, {seniority} level).\n"
        report_md += f"- **Total unique matches found:** {total_found}\n"
        report_md += f"- **Duplicates pruned:** {result.get('duplicates_pruned', 0)} ({result.get('reduction_rate', 0)}%)\n\n"

        if not jobs:
            report_md += "No new postings met your criteria overnight. Will scan again at next schedule.\n"
        else:
            report_md += "Here are your top recommended opportunities tailored to your resume:\n"

        # Create or fetch morning session
        sessions = self.db.list_sessions(client_id=client_id)
        session_id = sessions[0]["id"] if sessions else f"sess_{client_id[:8]}"
        if not sessions:
            self.db.create_session(session_id, "Morning Briefings", client_id=client_id)

        self.db.add_message(
            session_id=session_id,
            role="assistant",
            content=report_md,
            metadata={"type": "job_results", "jobs": jobs, "query": query.model_dump()},
        )

        return result
