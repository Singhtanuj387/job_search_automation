"""Unit tests for SQLite storage and queue management."""
import tempfile
from core.models import NormalizedJob, QueryConfig, RawResult
from core.storage import RunStorage


def test_storage_lifecycle():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        storage = RunStorage(db_path=tmp.name)
        q = QueryConfig(role="Python Engineer", location="Bangalore")

        # 1. Create run
        run_id = storage.create_run(q)
        assert run_id.startswith("run_")

        # 2. Enqueue and get tasks
        tasks = [
            {"source": "arbeitnow", "task_type": "fetch", "payload": {}},
            {"source": "greenhouse", "task_type": "fetch", "payload": {}},
        ]
        storage.enqueue_tasks(run_id, tasks)
        pending = storage.get_pending_tasks(run_id)
        assert len(pending) == 2

        # 3. Mark task status
        storage.mark_task_status(pending[0]["task_id"], "completed")
        remaining = storage.get_pending_tasks(run_id)
        assert len(remaining) == 1

        # 4. Save raw result
        raw = RawResult(
            source="arbeitnow",
            source_job_id="test_1",
            fetch_method="api",
            payload={"key": "val"},
            url="https://example.com",
            status_code=200,
        )
        storage.save_raw_result(run_id, raw)

        # 5. Save and read normalized job
        job = NormalizedJob(
            source="arbeitnow",
            source_job_id="test_1",
            title="Python Engineer",
            company="Startup Ltd",
            location="Bangalore",
            apply_url="https://example.com/apply",
            fetch_method="api",
            confidence=0.85,
        )
        storage.save_normalized_jobs(run_id, [job])
        saved_jobs = storage.get_normalized_jobs(run_id)
        assert len(saved_jobs) == 1
        assert saved_jobs[0].title == "Python Engineer"
