"""Unit tests for the end-to-end Orchestrator."""
import tempfile
from core.models import QueryConfig
from core.orchestrator import Orchestrator
from core.storage import RunStorage


def test_orchestrator_mock_run():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db, \
         tempfile.NamedTemporaryFile(suffix=".json") as tmp_res, \
         tempfile.NamedTemporaryFile(suffix=".json") as tmp_rep:

        storage = RunStorage(db_path=tmp_db.name)
        orchestrator = Orchestrator(storage=storage)

        query = QueryConfig(
            role="Engineer",
            location="any",
            seniority="any",
            sources=["arbeitnow"],  # run single source for fast test
        )

        report = orchestrator.run(
            query=query,
            results_path=tmp_res.name,
            report_path=tmp_rep.name,
        )

        assert "run_id" in report
        assert "sources_health" in report
        assert "arbeitnow" in report["sources_health"]
        assert report["sources_health"]["arbeitnow"]["status"] in ["ok", "degraded", "blocked"]
        assert "deduplication" in report
        assert "results_count" in report
