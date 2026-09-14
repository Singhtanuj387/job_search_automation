import uuid
from fastapi.testclient import TestClient
from web.backend.app import app

client = TestClient(app)

def test_session_isolation_profiles_and_tracker():
    sess_alice = f"sess_alice_{uuid.uuid4().hex[:8]}"
    sess_bob = f"sess_bob_{uuid.uuid4().hex[:8]}"

    headers_alice = {"X-Session-ID": sess_alice}
    headers_bob = {"X-Session-ID": sess_bob}

    # 1. Bob initially sees no profile
    r_bob_init = client.get("/api/profile", headers=headers_bob)
    assert r_bob_init.status_code == 200
    assert r_bob_init.json()["has_profile"] is False

    # 2. Alice initially sees no profile
    r_alice_init = client.get("/api/profile", headers=headers_alice)
    assert r_alice_init.status_code == 200
    assert r_alice_init.json()["has_profile"] is False

    # 3. Alice saves her profile
    alice_profile_data = {
        "name": "Alice Wonderland",
        "role": "AI Research Scientist",
        "location": "Bengaluru",
        "seniority": "senior",
        "notice_period": "Immediate",
        "expected_ctc_lpa": "45 LPA",
        "company_type": "Product-based",
        "email": "alice@wonderland.ai",
        "phone": "+919876543210",
        "skills": ["PyTorch", "Transformers", "Distributed Training"],
    }
    r_alice_save = client.post("/api/profile", json=alice_profile_data, headers=headers_alice)
    assert r_alice_save.status_code == 200
    assert r_alice_save.json()["status"] == "ok"
    assert r_alice_save.json()["profile"]["name"] == "Alice Wonderland"

    # 4. Alice adds a job to her tracker
    tracker_item = {
        "job_id": "DEEP-001",
        "company": "DeepMind",
        "title": "Staff Research Engineer",
        "location": "Bengaluru",
        "apply_url": "https://deepmind.google/careers",
        "status": "applied",
        "notes": "Applied directly with referral",
    }
    r_alice_track = client.post("/api/tracker", json=tracker_item, headers=headers_alice)
    assert r_alice_track.status_code == 200

    # 5. Verify Alice can fetch her profile and tracker
    r_alice_get = client.get("/api/profile", headers=headers_alice)
    assert r_alice_get.json()["has_profile"] is True
    assert r_alice_get.json()["profile"]["name"] == "Alice Wonderland"
    assert r_alice_get.json()["profile"]["email"] == "alice@wonderland.ai"

    r_alice_tracker = client.get("/api/tracker", headers=headers_alice)
    alice_entries = r_alice_tracker.json()
    assert any(e["company"] == "DeepMind" for e in alice_entries)

    # 6. CRITICAL VERIFICATION: Bob MUST NOT see Alice's profile or tracker!
    r_bob_check = client.get("/api/profile", headers=headers_bob)
    assert r_bob_check.json()["has_profile"] is False

    r_bob_tracker = client.get("/api/tracker", headers=headers_bob)
    bob_entries = r_bob_tracker.json()
    assert len(bob_entries) == 0

    # 7. Bob saves his own profile
    bob_profile_data = {
        "name": "Bob The Builder",
        "role": "Cloud DevOps Engineer",
        "location": "Hyderabad",
        "seniority": "mid",
        "notice_period": "30 Days",
        "expected_ctc_lpa": "25 LPA",
        "company_type": "Startup",
        "email": "bob@builder.io",
        "skills": ["Kubernetes", "Terraform", "GCP"],
    }
    r_bob_save = client.post("/api/profile", json=bob_profile_data, headers=headers_bob)
    assert r_bob_save.status_code == 200
    assert r_bob_save.json()["profile"]["name"] == "Bob The Builder"

    # 8. Bob now sees his profile, and still has 0 tracker entries
    r_bob_profile = client.get("/api/profile", headers=headers_bob)
    assert r_bob_profile.json()["has_profile"] is True
    assert r_bob_profile.json()["profile"]["name"] == "Bob The Builder"
    assert r_bob_profile.json()["profile"]["email"] == "bob@builder.io"

    r_bob_tracker2 = client.get("/api/tracker", headers=headers_bob)
    assert len(r_bob_tracker2.json()) == 0

    # 9. Alice still has her original profile and tracker unmodified
    r_alice_final_prof = client.get("/api/profile", headers=headers_alice)
    assert r_alice_final_prof.json()["profile"]["name"] == "Alice Wonderland"
    r_alice_final_track = client.get("/api/tracker", headers=headers_alice)
    assert any(e["company"] == "DeepMind" for e in r_alice_final_track.json())


def test_session_isolation_chat_and_secrets():
    sess_charlie = f"sess_charlie_{uuid.uuid4().hex[:8]}"
    sess_dave = f"sess_dave_{uuid.uuid4().hex[:8]}"

    headers_c = {"X-Session-ID": sess_charlie}
    headers_d = {"X-Session-ID": sess_dave}

    from web.backend.llm_service import LLMService
    monkeypatch_original = LLMService.validate_api_key
    LLMService.validate_api_key = classmethod(lambda cls, **kwargs: (True, "Valid API key"))
    try:
        # Charlie saves a secret API key
        r_c_save = client.post("/api/settings/secret", json={"provider": "gemini", "api_key": "AIzaSy_CharlieSecretKey123"}, headers=headers_c)
        assert r_c_save.status_code == 200

        # Charlie sees his secret configured
        r_c_sec = client.get("/api/settings/secret", headers=headers_c)
        assert r_c_sec.json()["has_key"] is True
        assert "AIzaSy" in r_c_sec.json()["masked_key"] and "y123" in r_c_sec.json()["masked_key"]

        # Dave MUST NOT see Charlie's secret!
        r_d_sec = client.get("/api/settings/secret", headers=headers_d)
        assert r_d_sec.json()["has_key"] is False
        assert r_d_sec.json()["masked_key"] is None

        # Charlie creates a chat session
        r_c_create_sess = client.post("/api/chat/sessions", json={"title": "Charlie AI Job Search"}, headers=headers_c)
        assert r_c_create_sess.status_code == 200
        c_sess_id = r_c_create_sess.json()["id"]

        # Charlie lists sessions
        r_c_list = client.get("/api/chat/sessions", headers=headers_c)
        assert any(s["id"] == c_sess_id for s in r_c_list.json())

        # Dave lists sessions -> MUST NOT see Charlie's session!
        r_d_list = client.get("/api/chat/sessions", headers=headers_d)
        assert not any(s["id"] == c_sess_id for s in r_d_list.json())
    finally:
        LLMService.validate_api_key = monkeypatch_original


