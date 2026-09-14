"""
Unit and Integration Tests for Total Job Opportunities Section.
"""
from fastapi.testclient import TestClient
from web.backend.app import app
from web.backend.db import AppDatabase

client = TestClient(app)
db = AppDatabase()


def test_opportunities_db_upsert_and_dedup():
    import uuid
    uid = uuid.uuid4().hex[:6]
    test_jobs = [
        {
            "company": f"Swiggy Test {uid}",
            "title": "Senior React Engineer",
            "location": "Bangalore",
            "source": "instahyre",
            "apply_url": f"https://instahyre.com/job/test-{uid}-1",
            "fitness_score": 92,
            "fit_framing": "Exceptional Fit",
            "fit_reason": "(strong skills match)",
            "fit_badge_color": "emerald",
            "source_job_id": f"TEST-{uid}-01",
        },
        {
            "company": f"Zomato Test {uid}",
            "title": "Backend Python Engineer",
            "location": "Gurgaon",
            "source": "naukri",
            "apply_url": f"https://naukri.com/job/test-{uid}-2",
            "fitness_score": 85,
            "fit_framing": "Strong Match",
            "fit_reason": "(solid experience overlap)",
            "fit_badge_color": "emerald",
            "source_job_id": f"TEST-{uid}-02",
        }
    ]

    # Initial upsert
    added_count = db.upsert_opportunities(test_jobs)
    assert added_count == 2

    # Attempt upserting duplicates with case / whitespace differences
    duplicate_jobs = [
        {
            "company": f" swiggy test {uid} ",
            "title": "senior react engineer",
            "location": "bangalore ",
            "source": "instahyre",
            "apply_url": f"https://instahyre.com/job/test-{uid}-1?utm=source",
            "fitness_score": 95,
        }
    ]
    dupe_added = db.upsert_opportunities(duplicate_jobs)
    assert dupe_added == 0, "Duplicate job should not increase unique count"


def test_opportunities_api_endpoints():
    # 1. Get stats
    resp_stats = client.get("/api/opportunities/stats")
    assert resp_stats.status_code == 200
    stats = resp_stats.json()
    assert "total_opportunities" in stats
    assert stats["total_opportunities"] > 0
    assert "platforms_count" in stats
    assert "high_match_count" in stats

    # 2. List opportunities
    resp_list = client.get("/api/opportunities?limit=10")
    assert resp_list.status_code == 200
    opps = resp_list.json()
    assert isinstance(opps, list)
    assert len(opps) > 0
    first_id = opps[0]["id"]

    # 3. Get single opportunity
    resp_single = client.get(f"/api/opportunities/{first_id}")
    assert resp_single.status_code == 200
    single = resp_single.json()
    assert single["id"] == first_id

    # 4. Save to tracker
    resp_save = client.post(f"/api/opportunities/{first_id}/save-to-tracker")
    assert resp_save.status_code == 200
    data = resp_save.json()
    assert data["status"] in ["ok", "already_saved"]
    assert "entry" in data


def test_clear_all_opportunities(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test_app.db"
    test_db = AppDatabase(db_path=test_db_path)

    # 1. Add dummy opportunity
    test_db.upsert_opportunities([{
        "company": "ClearCo",
        "title": "Clear Developer",
        "location": "Remote",
        "source": "linkedin",
        "apply_url": "https://clearco.com/job/1",
        "fitness_score": 88
    }])

    # 2. Add a 'found' entry and an 'applied' entry to tracker
    test_db.set_tracker_status_by_job_id(
        job_id="test-job-found",
        status="found",
        company="ClearCo",
        title="Clear Developer"
    )
    test_db.set_tracker_status_by_job_id(
        job_id="test-job-applied",
        status="applied",
        company="AppliedCo",
        title="Senior Developer"
    )

    # Verify counts before clear
    opps = test_db.list_opportunities(limit=10)
    assert len(opps) == 1
    tracker_entries = test_db.list_tracker_entries()
    assert len(tracker_entries) == 2

    # 3. Test clear_all_opportunities DB method
    res = test_db.clear_all_opportunities(clear_found_tracker=True)
    assert res["opportunities_cleared"] == 1
    assert res["tracker_found_cleared"] == 1

    # Verify opportunities are now empty
    assert len(test_db.list_opportunities(limit=10)) == 0

    # Verify tracker preserved applied entry but removed found entry
    remaining_tracker = test_db.list_tracker_entries()
    assert len(remaining_tracker) == 1
    assert remaining_tracker[0]["status"] == "applied"
    assert remaining_tracker[0]["company"] == "AppliedCo"

    # 4. Test DELETE /api/opportunities route handler with monkeypatch
    import web.backend.routes.opportunities as opp_route
    monkeypatch.setattr(opp_route, "db", test_db)

    # Re-insert an opportunity to test the API route
    test_db.upsert_opportunities([{
        "company": "RouteCo",
        "title": "Route Developer",
        "location": "Remote",
        "source": "linkedin",
        "apply_url": "https://routeco.com/job/2",
        "fitness_score": 90
    }])
    assert len(test_db.list_opportunities(limit=10)) == 1

    response = client.delete("/api/opportunities?clear_found_tracker=true")
    assert response.status_code == 200
    route_data = response.json()
    assert route_data["status"] == "ok"
    assert route_data["details"]["opportunities_cleared"] == 1
    assert len(test_db.list_opportunities(limit=10)) == 0

