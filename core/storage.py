"""
SQLite-backed resumable persistence engine for job search tasks, raw results, and normalized records.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.models import NormalizedJob, QueryConfig, RawResult


class RunStorage:
    """
    Manages SQLite database for query run state, task queues, and job listings.
    """

    def __init__(self, db_path: str = "data/jobs.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    query_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS raw_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_job_id TEXT NOT NULL,
                    fetch_method TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    url TEXT NOT NULL,
                    status_code INTEGER,
                    fetched_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS normalized_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_job_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT NOT NULL,
                    seniority TEXT,
                    salary_range TEXT,
                    description TEXT,
                    apply_url TEXT NOT NULL,
                    posted_date TEXT,
                    scraped_at TEXT NOT NULL,
                    fetch_method TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    job_json TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
            """)
            conn.commit()

    def create_run(self, query: QueryConfig) -> str:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, query_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, query.model_dump_json(), "running", now, now)
            )
            conn.commit()
        return run_id

    def update_run_status(self, run_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (status, now, run_id)
            )
            conn.commit()

    def enqueue_tasks(self, run_id: str, tasks: List[Dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            for t in tasks:
                conn.execute(
                    """
                    INSERT INTO tasks (run_id, source, task_type, payload, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (run_id, t["source"], t["task_type"], json.dumps(t.get("payload", {})), now, now)
                )
            conn.commit()

    def get_pending_tasks(self, run_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT task_id, run_id, source, task_type, payload, status FROM tasks WHERE run_id = ? AND status = 'pending'",
                (run_id,)
            )
            rows = cursor.fetchall()
            return [
                {
                    "task_id": r["task_id"],
                    "run_id": r["run_id"],
                    "source": r["source"],
                    "task_type": r["task_type"],
                    "payload": json.loads(r["payload"]),
                    "status": r["status"]
                }
                for r in rows
            ]

    def mark_task_status(self, task_id: int, status: str, error_message: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, error_message = ?, updated_at = ? WHERE task_id = ?",
                (status, error_message, now, task_id)
            )
            conn.commit()

    def save_raw_result(self, run_id: str, raw: RawResult) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO raw_results (run_id, source, source_job_id, fetch_method, payload_json, url, status_code, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    raw.source,
                    raw.source_job_id,
                    raw.fetch_method,
                    json.dumps(raw.payload),
                    raw.url,
                    raw.status_code,
                    raw.fetched_at
                )
            )
            conn.commit()

    def save_normalized_jobs(self, run_id: str, jobs: List[NormalizedJob]) -> None:
        with self._get_connection() as conn:
            for job in jobs:
                conn.execute(
                    """
                    INSERT INTO normalized_jobs (
                        run_id, source, source_job_id, title, company, location, seniority,
                        salary_range, description, apply_url, posted_date, scraped_at,
                        fetch_method, confidence, job_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        job.source,
                        job.source_job_id,
                        job.title,
                        job.company,
                        job.location,
                        job.seniority,
                        job.salary_range,
                        job.description,
                        job.apply_url,
                        job.posted_date,
                        job.scraped_at,
                        job.fetch_method,
                        job.confidence,
                        job.model_dump_json()
                    )
                )
            conn.commit()

    def get_normalized_jobs(self, run_id: str) -> List[NormalizedJob]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT job_json FROM normalized_jobs WHERE run_id = ?",
                (run_id,)
            )
            rows = cursor.fetchall()
            return [NormalizedJob.model_validate_json(r["job_json"]) for r in rows]

    def get_latest_incomplete_run(self) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT run_id FROM runs WHERE status = 'running' ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return row["run_id"] if row else None
