"""
Auto-Apply API Routes.
Manages LinkedIn credentials, apply sessions, and real-time apply progress via SSE.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from web.backend.db import AppDatabase
from web.backend.resume_extractor import ResumeExtractor
from web.backend.session import get_client_id

router = APIRouter(prefix="/api/apply", tags=["Apply"])
db = AppDatabase()

# Global registry for active apply sessions (for stop/respond)
_active_sessions: Dict[str, Dict[str, Any]] = {}


# ────────────── Request Models ──────────────

class LinkedInCredentialsRequest(BaseModel):
    email: str
    password: str


class StartApplyRequest(BaseModel):
    max_applies: int = 25
    platform: str = "linkedin"


class RespondToQuestionRequest(BaseModel):
    answer: str


# ────────────── LinkedIn Credentials ──────────────

@router.post("/credentials")
def save_credentials(req: LinkedInCredentialsRequest, client_id: str = Depends(get_client_id)):
    """Save LinkedIn login credentials (encrypted)."""
    if not req.email or not req.password:
        raise HTTPException(status_code=400, detail="Email and password are required.")
    result = db.save_linkedin_credentials(req.email.strip(), req.password.strip(), client_id=client_id)
    return result


@router.get("/credentials")
def get_credentials(client_id: str = Depends(get_client_id)):
    """Check if LinkedIn credentials are stored. Returns masked email, no password."""
    import os
    creds = db.get_linkedin_credentials(client_id=client_id)
    cookies_path = "web/backend/data/linkedin_cookies.json"
    has_cookies = os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 100

    if not creds:
        return {
            "has_credentials": False,
            "has_cookies": has_cookies,
        }
    return {
        "has_credentials": True,
        "masked_email": creds.get("masked_email", ""),
        "email": creds.get("email", ""),
        "saved_at": creds.get("saved_at", ""),
        "has_cookies": has_cookies,
    }


@router.delete("/credentials")
def delete_credentials(client_id: str = Depends(get_client_id)):
    """Remove stored LinkedIn credentials and cached cookies."""
    import os
    deleted = db.delete_linkedin_credentials(client_id=client_id)
    cookies_path = "web/backend/data/linkedin_cookies.json"
    if os.path.exists(cookies_path):
        try:
            os.remove(cookies_path)
        except Exception:
            pass
    return {"deleted": deleted}


@router.delete("/credentials/cookies")
def clear_cookies():
    """Clear cached LinkedIn browser cookies."""
    import os
    cookies_path = "web/backend/data/linkedin_cookies.json"
    if os.path.exists(cookies_path):
        try:
            os.remove(cookies_path)
            return {"cleared": True}
        except Exception as e:
            return {"cleared": False, "error": str(e)}
    return {"cleared": True}


# ────────────── Indeed Credentials ──────────────

class IndeedCredentialsRequest(BaseModel):
    email: str
    password: Optional[str] = ""


@router.post("/indeed/credentials")
def save_indeed_credentials(req: IndeedCredentialsRequest, client_id: str = Depends(get_client_id)):
    """Save Indeed login credentials (encrypted). Only email is required."""
    if not req.email or not req.email.strip():
        raise HTTPException(status_code=400, detail="Indeed email / Gmail is required.")
    result = db.save_indeed_credentials(req.email.strip(), (req.password or "").strip(), client_id=client_id)
    return result


@router.get("/indeed/credentials")
def get_indeed_credentials(client_id: str = Depends(get_client_id)):
    """Check if Indeed credentials are stored. Returns masked email, no password."""
    import os
    creds = db.get_indeed_credentials(client_id=client_id)
    cookie_paths = ["web/backend/data/indeed_cookies.json", "data/indeed_cookies.json"]
    has_cookies = any(os.path.exists(p) and os.path.getsize(p) > 100 for p in cookie_paths)

    if not creds:
        return {
            "has_credentials": False,
            "has_cookies": has_cookies,
        }
    return {
        "has_credentials": True,
        "masked_email": creds.get("masked_email", ""),
        "email": creds.get("email", ""),
        "saved_at": creds.get("saved_at", ""),
        "has_cookies": has_cookies,
    }


@router.delete("/indeed/credentials")
def delete_indeed_credentials(client_id: str = Depends(get_client_id)):
    """Remove stored Indeed credentials and cached cookies."""
    import os
    deleted = db.delete_indeed_credentials(client_id=client_id)
    for p in ["web/backend/data/indeed_cookies.json", "data/indeed_cookies.json"]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    return {"deleted": deleted}


@router.delete("/indeed/credentials/cookies")
def clear_indeed_cookies():
    """Clear cached Indeed browser cookies."""
    import os
    cleared_any = False
    for p in ["web/backend/data/indeed_cookies.json", "data/indeed_cookies.json"]:
        if os.path.exists(p):
            try:
                os.remove(p)
                cleared_any = True
            except Exception as e:
                return {"cleared": False, "error": str(e)}
    return {"cleared": True}


# ────────────── SEEK Credentials ──────────────

class SeekCredentialsRequest(BaseModel):
    email: str
    password: Optional[str] = ""


@router.post("/seek/credentials")
def save_seek_credentials(req: SeekCredentialsRequest, client_id: str = Depends(get_client_id)):
    """Save SEEK login credentials (encrypted). Only email is required for passwordless code sign-in."""
    if not req.email or not req.email.strip():
        raise HTTPException(status_code=400, detail="SEEK email is required.")
    result = db.save_seek_credentials(req.email.strip(), (req.password or "").strip(), client_id=client_id)
    return result


@router.get("/seek/credentials")
def get_seek_credentials(client_id: str = Depends(get_client_id)):
    """Check if SEEK credentials are stored. Returns masked email, no password."""
    import os
    creds = db.get_seek_credentials(client_id=client_id)
    cookie_paths = ["web/backend/data/seek_cookies.json", "data/seek_cookies.json"]
    has_cookies = any(os.path.exists(p) and os.path.getsize(p) > 100 for p in cookie_paths)

    if not creds:
        return {
            "has_credentials": False,
            "has_cookies": has_cookies,
        }
    return {
        "has_credentials": True,
        "masked_email": creds.get("masked_email", ""),
        "email": creds.get("email", ""),
        "saved_at": creds.get("saved_at", ""),
        "has_cookies": has_cookies,
    }


@router.delete("/seek/credentials")
def delete_seek_credentials(client_id: str = Depends(get_client_id)):
    """Remove stored SEEK credentials and cached cookies."""
    import os
    deleted = db.delete_seek_credentials(client_id=client_id)
    for p in ["web/backend/data/seek_cookies.json", "data/seek_cookies.json"]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    return {"deleted": deleted}


@router.delete("/seek/credentials/cookies")
def clear_seek_cookies():
    """Clear cached SEEK browser cookies."""
    import os
    cleared_any = False
    for p in ["web/backend/data/seek_cookies.json", "data/seek_cookies.json"]:
        if os.path.exists(p):
            try:
                os.remove(p)
                cleared_any = True
            except Exception as e:
                return {"cleared": False, "error": str(e)}
    return {"cleared": True}


# ────────────── Apply Sessions ──────────────

@router.get("/sessions")
def list_apply_sessions(platform: str = "", client_id: str = Depends(get_client_id)):
    """List all apply sessions."""
    return db.list_apply_sessions(platform=platform, client_id=client_id)


@router.get("/active")
def get_active_apply_session(client_id: str = Depends(get_client_id)):
    """
    Get the currently active apply session or the most recent session status.
    Enables reloaded browser pages to instantly recover live apply progress.
    """
    # 1. First check in-memory active sessions
    for sid, sdata in list(_active_sessions.items()):
        if sdata.get("client_id", "default") == client_id:
            status = sdata.get("status", "running")
            if status in ("running", "waiting_for_input"):
                return {
                    "active": True,
                    "session_id": sid,
                    "platform": sdata.get("platform", "linkedin"),
                    "status": status,
                    "total_jobs": sdata.get("total_jobs", 0),
                    "applied_count": sdata.get("applied_count", 0),
                    "skipped_count": sdata.get("skipped_count", 0),
                    "error_count": sdata.get("error_count", 0),
                    "pending_question": sdata.get("pending_question"),
                    "events": list(sdata.get("event_buffer", [])),
                    "jobs": sdata.get("jobs", []),
                }

    # 2. Check DB for most recent session
    sessions = db.list_apply_sessions(client_id=client_id)
    if sessions:
        recent = sessions[0]
        pending_q = None
        if recent.get("pending_question"):
            try:
                pending_q = json.loads(recent["pending_question"]) if isinstance(recent["pending_question"], str) else recent["pending_question"]
            except Exception:
                pending_q = None

        results = []
        if recent.get("results_json"):
            try:
                results = json.loads(recent["results_json"]) if isinstance(recent["results_json"], str) else recent["results_json"]
            except Exception:
                results = []

        is_running = recent.get("status") in ("running", "waiting_for_input")
        return {
            "active": is_running,
            "session_id": recent.get("id"),
            "platform": recent.get("platform", "linkedin"),
            "status": recent.get("status"),
            "total_jobs": recent.get("total_jobs", 0),
            "applied_count": recent.get("applied_count", 0),
            "skipped_count": recent.get("skipped_count", 0),
            "error_count": recent.get("error_count", 0),
            "pending_question": pending_q,
            "events": [],
            "results": results,
            "started_at": recent.get("started_at"),
            "completed_at": recent.get("completed_at"),
        }

    return {"active": False, "session_id": None}


@router.get("/sessions/{session_id}")
def get_apply_session(session_id: str):
    """Get status of a specific apply session."""
    if session_id in _active_sessions:
        sdata = _active_sessions[session_id]
        return {
            "id": session_id,
            "platform": sdata.get("platform", "linkedin"),
            "status": sdata.get("status", "running"),
            "total_jobs": sdata.get("total_jobs", 0),
            "applied_count": sdata.get("applied_count", 0),
            "skipped_count": sdata.get("skipped_count", 0),
            "error_count": sdata.get("error_count", 0),
            "pending_question": sdata.get("pending_question"),
            "events": list(sdata.get("event_buffer", [])),
        }
    session = db.get_apply_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Apply session not found")
    return session


@router.get("/sessions/{session_id}/stream")
async def stream_apply_session(session_id: str):
    """
    Reconnect to an ongoing apply session's SSE stream.
    Replays buffered past events and streams live events in real-time.
    """
    if session_id not in _active_sessions:
        # If not active in memory, stream completed status from DB
        session = db.get_apply_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Apply session not found")

        async def static_event_stream():
            res_json = session.get("results_json") or "[]"
            try:
                results = json.loads(res_json) if isinstance(res_json, str) else res_json
            except Exception:
                results = []
            yield f"data: {json.dumps({'type': 'apply_complete', 'session_id': session_id, 'result': {'applied': session.get('applied_count', 0), 'skipped': session.get('skipped_count', 0), 'errors': session.get('error_count', 0)}, 'results': results})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            static_event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    sdata = _active_sessions[session_id]
    sub_queue: asyncio.Queue = asyncio.Queue()
    sdata.setdefault("subscribers", []).append(sub_queue)

    async def reconnect_event_generator():
        try:
            # 1. Replay historical events
            for evt in list(sdata.get("event_buffer", [])):
                yield f"data: {json.dumps(evt)}\n\n"

            # 2. Stream subsequent live events
            while True:
                evt = await sub_queue.get()
                if evt is None:
                    break
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("type") in ("apply_complete", "apply_batch_complete", "apply_stopped"):
                    break
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if sub_queue in sdata.get("subscribers", []):
                sdata["subscribers"].remove(sub_queue)

    return StreamingResponse(
        reconnect_event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/linkedin/start")
async def start_linkedin_apply(req: StartApplyRequest, client_id: str = Depends(get_client_id)):
    """
    Start a LinkedIn auto-apply session.
    Returns SSE stream with real-time progress.
    """
    # 1. Stop any currently running background session to prevent concurrency conflicts
    for existing_id, sdata in list(_active_sessions.items()):
        if sdata.get("client_id", "default") == client_id and sdata.get("status") in ("running", "waiting_for_input"):
            agent = sdata.get("agent")
            if agent:
                try:
                    agent.request_stop()
                except Exception:
                    pass
            db.update_apply_session(existing_id, status="stopped")
            sdata["status"] = "stopped"

    # 2. Validate credentials exist
    creds = db.get_linkedin_credentials(client_id=client_id)
    if not creds:
        raise HTTPException(
            status_code=400,
            detail="LinkedIn credentials not saved. Please provide your LinkedIn email and password first."
        )

    # 3. Get profile and resume data
    profile = db.get_profile(session_id=client_id) or {}
    resume_text = profile.get("resume_text", "")
    if not resume_text:
        raise HTTPException(
            status_code=400,
            detail="No resume uploaded. Please upload your resume first in the Candidate Profile section."
        )

    # 4. Get LinkedIn jobs to apply to
    jobs = db.get_linkedin_opportunities_for_apply(max_jobs=req.max_applies, client_id=client_id)
    if not jobs:
        raise HTTPException(
            status_code=404,
            detail="No LinkedIn jobs available to apply to. Run a search first with /job-skill search to discover opportunities."
        )

    # 5. Extract structured resume data
    resume_data = ResumeExtractor.extract_all(resume_text, profile)

    # 6. Create apply session
    session_id = f"apply_{uuid.uuid4().hex[:8]}"
    db.create_apply_session(
        session_id=session_id,
        platform="linkedin",
        max_applies=req.max_applies,
        total_jobs=len(jobs),
        client_id=client_id,
    )

    loop = asyncio.get_running_loop()
    question_event = asyncio.Event()
    answer_holder: Dict[str, Optional[str]] = {"value": None}
    event_buffer: List[Dict[str, Any]] = []
    subscribers: List[asyncio.Queue] = []
    main_queue: asyncio.Queue = asyncio.Queue()
    subscribers.append(main_queue)

    session_entry: Dict[str, Any] = {
        "session_id": session_id,
        "client_id": client_id,
        "agent": None,
        "agent_task": None,
        "question_event": question_event,
        "answer_holder": answer_holder,
        "stop_requested": False,
        "event_buffer": event_buffer,
        "subscribers": subscribers,
        "status": "running",
        "jobs": jobs,
        "total_jobs": len(jobs),
        "applied_count": 0,
        "skipped_count": 0,
        "error_count": 0,
        "pending_question": None,
        "loop": loop,
    }

    def broadcast(evt: Dict[str, Any]):
        """Append event to history and push to all connected subscriber queues."""
        event_buffer.append(evt)
        # Update real-time counts if job done
        if evt.get("type") == "apply_job_done":
            st = evt.get("status")
            if st == "applied":
                session_entry["applied_count"] += 1
            elif st in ("skipped", "manual_required"):
                session_entry["skipped_count"] += 1
            else:
                session_entry["error_count"] += 1
            db.update_apply_session(
                session_id,
                applied_count=session_entry["applied_count"],
                skipped_count=session_entry["skipped_count"],
                error_count=session_entry["error_count"],
            )

        for q in list(subscribers):
            try:
                q.put_nowait(evt)
            except Exception:
                pass

    session_entry["broadcast"] = broadcast
    _active_sessions[session_id] = session_entry

    async def ask_user_fn(job_title: str, field_name: str, question: str) -> Optional[str]:
        """
        Called by the agent when it needs user input.
        Sets pending question in session & DB, broadcasts SSE event, and waits for response.
        """
        q_data = {
            "job_title": job_title,
            "field_name": field_name,
            "question": question,
        }
        session_entry["status"] = "waiting_for_input"
        session_entry["pending_question"] = q_data
        db.update_apply_session(session_id, pending_question=q_data)

        broadcast({
            "type": "apply_needs_input",
            "session_id": session_id,
            "job_title": job_title,
            "field_name": field_name,
            "question": question,
            "message": f"Agent needs your input for: {field_name}",
        })

        answer_holder["value"] = None
        question_event.clear()

        try:
            await asyncio.wait_for(question_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            session_entry["status"] = "running"
            session_entry["pending_question"] = None
            db.update_apply_session(session_id, pending_question=None)
            broadcast({
                "type": "apply_input_timeout",
                "session_id": session_id,
                "field_name": field_name,
                "message": f"Input timed out for '{field_name}'. Proceeding...",
            })
            return None

        # Received answer
        ans = answer_holder["value"]
        session_entry["status"] = "running"
        session_entry["pending_question"] = None
        db.update_apply_session(session_id, pending_question=None)

        broadcast({
            "type": "apply_input_resolved",
            "session_id": session_id,
            "field_name": field_name,
            "answer": ans,
            "message": f"Answer received for '{field_name}'. Resuming application...",
        })
        return ans

    # Broadcast initial session start event
    broadcast({
        "type": "apply_init",
        "session_id": session_id,
        "total_jobs": len(jobs),
        "message": f"Initialized LinkedIn auto-apply session with {len(jobs)} jobs",
    })

    async def run_agent():
        from web.backend.linkedin_apply_agent import LinkedInApplyAgent

        agent = LinkedInApplyAgent(
            credentials=creds,
            resume_data=resume_data,
            profile=profile,
            ask_user_callback=ask_user_fn,
            progress_callback=broadcast,
            db=db,
        )
        session_entry["agent"] = agent

        try:
            await agent.initialize_browser()

            logged_in = await agent.login()
            if not logged_in:
                broadcast({
                    "type": "apply_error",
                    "session_id": session_id,
                    "message": "Failed to log into LinkedIn. Check your credentials in Platform Credentials.",
                })
                now = datetime.now(timezone.utc).isoformat()
                db.update_apply_session(session_id, status="error", completed_at=now)
                session_entry["status"] = "error"
                return None

            result = await agent.run_batch(jobs, max_applies=req.max_applies)
            return result

        except Exception as e:
            broadcast({
                "type": "apply_error",
                "session_id": session_id,
                "message": f"Apply agent error: {str(e)}",
            })
            now = datetime.now(timezone.utc).isoformat()
            db.update_apply_session(session_id, status="error", completed_at=now)
            session_entry["status"] = "error"
            return None
        finally:
            await agent.close_browser()

    # Start the agent background task
    agent_task = asyncio.create_task(run_agent())
    session_entry["agent_task"] = agent_task

    # Background handler to finalize session once agent completes
    async def finalize_session():
        try:
            batch_result = await agent_task
            now = datetime.now(timezone.utc).isoformat()
            if batch_result:
                db.update_apply_session(
                    session_id,
                    status="completed",
                    applied_count=batch_result.applied,
                    skipped_count=batch_result.skipped,
                    error_count=batch_result.errors,
                    completed_at=now,
                    results_json=json.dumps([
                        {"job_id": r.job_id, "company": r.company, "title": r.title,
                         "status": r.status.value, "message": r.message}
                        for r in batch_result.results
                    ]),
                )
                session_entry["status"] = "completed"
                broadcast({
                    "type": "apply_complete",
                    "session_id": session_id,
                    "result": {
                        "applied": batch_result.applied,
                        "skipped": batch_result.skipped,
                        "errors": batch_result.errors,
                    },
                    "message": f"Auto-apply complete: {batch_result.applied} applied, {batch_result.skipped} skipped, {batch_result.errors} errors",
                })
            else:
                session_entry["status"] = "error"
        except Exception as fe:
            now = datetime.now(timezone.utc).isoformat()
            db.update_apply_session(session_id, status="error", completed_at=now)
            session_entry["status"] = "error"
        finally:
            # Signal all queues that stream is finished
            for q in list(subscribers):
                try:
                    q.put_nowait(None)
                except Exception:
                    pass

    asyncio.create_task(finalize_session())

    # Stream generator for this HTTP connection
    async def event_generator():
        try:
            while True:
                evt = await main_queue.get()
                if evt is None:
                    break
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("type") in ("apply_complete", "apply_error", "apply_stopped"):
                    break
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if main_queue in subscribers:
                subscribers.remove(main_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/linkedin/respond/{session_id}")
async def respond_to_question(session_id: str, req: RespondToQuestionRequest):
    """
    User responds to a question the apply agent asked.
    Directly awakens the agent's asyncio Event and emits apply_input_resolved event.
    """
    answer_text = req.answer.strip()
    if not answer_text:
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    if session_id not in _active_sessions:
        # Fallback check DB: session might have been interrupted
        session = db.get_apply_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Apply session not found or not active.")
        db.update_apply_session(session_id, pending_question=None)
        return {"status": "ok", "message": "Answer recorded in database."}

    session_data = _active_sessions[session_id]
    answer_holder = session_data.get("answer_holder")
    question_event = session_data.get("question_event")
    broadcast = session_data.get("broadcast")

    if answer_holder is None or question_event is None:
        raise HTTPException(status_code=400, detail="No pending question for this session.")

    # 1. Store answer
    answer_holder["value"] = answer_text

    # 2. Clear pending question and set status
    session_data["pending_question"] = None
    session_data["status"] = "running"
    db.update_apply_session(session_id, pending_question=None)

    # 3. Broadcast resolving event immediately so frontend gets instant feedback
    if broadcast:
        broadcast({
            "type": "apply_input_resolved",
            "session_id": session_id,
            "answer": answer_text,
            "message": f"Answer \"{answer_text}\" submitted. Resuming application...",
        })

    # 4. Awaken agent coroutine thread-safely
    loop = session_data.get("loop")
    if loop and loop.is_running():
        loop.call_soon_threadsafe(question_event.set)
    else:
        question_event.set()

    return {"status": "ok", "message": "Answer submitted to the apply agent."}


@router.post("/seek/respond/{session_id}")
@router.post("/indeed/respond/{session_id}")
@router.post("/respond/{session_id}")
async def respond_to_question_alias(session_id: str, req: RespondToQuestionRequest):
    """Alias for responding to question across LinkedIn, Indeed, and SEEK."""
    return await respond_to_question(session_id, req)


@router.post("/linkedin/stop/{session_id}")
async def stop_apply_session(session_id: str):
    """
    Gracefully stop an active apply session.
    """
    if session_id in _active_sessions:
        session_data = _active_sessions[session_id]
        agent = session_data.get("agent")
        if agent:
            try:
                agent.request_stop()
            except Exception:
                pass
        session_data["status"] = "stopped"
        db.update_apply_session(session_id, status="stopped")

        broadcast = session_data.get("broadcast")
        if broadcast:
            broadcast({
                "type": "apply_stopped",
                "session_id": session_id,
                "message": "Auto-apply session stopped by user.",
            })

        return {"status": "ok", "message": "Stop signal sent. Session will end after current step."}

    # Try DB fallback
    session = db.get_apply_session(session_id)
    if session:
        db.update_apply_session(session_id, status="stopped")
        return {"status": "ok", "message": "Session marked as stopped."}

    raise HTTPException(status_code=404, detail="Apply session not found.")


@router.post("/seek/stop/{session_id}")
@router.post("/indeed/stop/{session_id}")
@router.post("/stop/{session_id}")
async def stop_apply_session_alias(session_id: str):
    """Alias for stopping an active apply session across LinkedIn, Indeed, and SEEK."""
    return await stop_apply_session(session_id)


# ────────────── Indeed Auto-Apply ──────────────

@router.post("/indeed/start")
async def start_indeed_apply(req: StartApplyRequest, client_id: str = Depends(get_client_id)):
    """
    Start an Indeed auto-apply session.
    Returns SSE stream with real-time progress.
    """
    # 1. Stop any currently running background session to prevent concurrency conflicts
    for existing_id, sdata in list(_active_sessions.items()):
        if sdata.get("client_id", "default") == client_id and sdata.get("status") in ("running", "waiting_for_input"):
            agent = sdata.get("agent")
            if agent:
                try:
                    agent.request_stop()
                except Exception:
                    pass
            db.update_apply_session(existing_id, status="stopped")
            sdata["status"] = "stopped"

    # 2. Validate credentials exist (or fall back to profile email / cached session)
    profile = db.get_profile(session_id=client_id) or {}
    creds = db.get_indeed_credentials(client_id=client_id)
    if not creds:
        p_email = (profile.get("email") or "").strip()
        if p_email:
            db.save_indeed_credentials(p_email, "", client_id=client_id)
            creds = db.get_indeed_credentials(client_id=client_id)
    if not creds:
        raise HTTPException(
            status_code=400,
            detail="Indeed credentials not saved. Please provide your Indeed email and password first in Platform Credentials."
        )

    # 3. Get profile and resume data
    resume_text = profile.get("resume_text", "")
    if not resume_text:
        raise HTTPException(
            status_code=400,
            detail="No resume uploaded. Please upload your resume first in the Candidate Profile section."
        )

    # 4. Get Indeed jobs to apply to
    jobs = db.get_indeed_opportunities_for_apply(max_jobs=req.max_applies, client_id=client_id)
    if not jobs:
        raise HTTPException(
            status_code=404,
            detail="No Indeed jobs available to apply to. Run a search first with /job-skill search to discover opportunities."
        )

    # 5. Extract structured resume data
    resume_data = ResumeExtractor.extract_all(resume_text, profile)

    # 6. Create apply session
    session_id = f"apply_indeed_{uuid.uuid4().hex[:8]}"
    db.create_apply_session(
        session_id=session_id,
        platform="indeed",
        max_applies=req.max_applies,
        total_jobs=len(jobs),
        client_id=client_id,
    )

    loop = asyncio.get_running_loop()
    question_event = asyncio.Event()
    answer_holder: Dict[str, Optional[str]] = {"value": None}
    event_buffer: List[Dict[str, Any]] = []
    subscribers: List[asyncio.Queue] = []
    main_queue: asyncio.Queue = asyncio.Queue()
    subscribers.append(main_queue)

    session_entry: Dict[str, Any] = {
        "session_id": session_id,
        "client_id": client_id,
        "platform": "indeed",
        "agent": None,
        "agent_task": None,
        "question_event": question_event,
        "answer_holder": answer_holder,
        "stop_requested": False,
        "event_buffer": event_buffer,
        "subscribers": subscribers,
        "status": "running",
        "jobs": jobs,
        "total_jobs": len(jobs),
        "applied_count": 0,
        "skipped_count": 0,
        "error_count": 0,
        "pending_question": None,
        "loop": loop,
    }

    def broadcast(evt: Dict[str, Any]):
        """Append event to history and push to all connected subscriber queues."""
        event_buffer.append(evt)
        if evt.get("type") == "apply_job_done":
            st = evt.get("status")
            if st == "applied":
                session_entry["applied_count"] += 1
            elif st in ("skipped", "manual_required"):
                session_entry["skipped_count"] += 1
            else:
                session_entry["error_count"] += 1
            db.update_apply_session(
                session_id,
                applied_count=session_entry["applied_count"],
                skipped_count=session_entry["skipped_count"],
                error_count=session_entry["error_count"],
            )

        for q in list(subscribers):
            try:
                q.put_nowait(evt)
            except Exception:
                pass

    session_entry["broadcast"] = broadcast
    _active_sessions[session_id] = session_entry

    async def ask_user_fn(job_title: str, field_name: str, question: str) -> Optional[str]:
        """
        Called by the agent when it needs user input.
        Sets pending question in session & DB, broadcasts SSE event, and waits for response.
        """
        q_data = {
            "job_title": job_title,
            "field_name": field_name,
            "question": question,
        }
        session_entry["status"] = "waiting_for_input"
        session_entry["pending_question"] = q_data
        db.update_apply_session(session_id, pending_question=q_data)

        broadcast({
            "type": "apply_needs_input",
            "session_id": session_id,
            "job_title": job_title,
            "field_name": field_name,
            "question": question,
            "message": f"Agent needs your input for: {field_name}",
        })

        answer_holder["value"] = None
        question_event.clear()

        try:
            await asyncio.wait_for(question_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            session_entry["status"] = "running"
            session_entry["pending_question"] = None
            db.update_apply_session(session_id, pending_question=None)
            broadcast({
                "type": "apply_input_timeout",
                "session_id": session_id,
                "field_name": field_name,
                "message": f"Input timed out for '{field_name}'. Proceeding...",
            })
            return None

        ans = answer_holder["value"]
        session_entry["status"] = "running"
        session_entry["pending_question"] = None
        db.update_apply_session(session_id, pending_question=None)

        broadcast({
            "type": "apply_input_resolved",
            "session_id": session_id,
            "field_name": field_name,
            "answer": ans,
            "message": f"Answer received for '{field_name}'. Resuming application...",
        })
        return ans

    broadcast({
        "type": "apply_init",
        "session_id": session_id,
        "platform": "indeed",
        "total_jobs": len(jobs),
        "message": f"Initialized Indeed auto-apply session with {len(jobs)} jobs",
    })

    async def run_agent():
        from web.backend.indeed_apply_agent import IndeedApplyAgent

        agent = IndeedApplyAgent(
            credentials=creds,
            resume_data=resume_data,
            profile=profile,
            ask_user_callback=ask_user_fn,
            progress_callback=broadcast,
            db=db,
        )
        session_entry["agent"] = agent

        try:
            await agent.initialize_browser()

            logged_in = await agent.login()
            if not logged_in:
                broadcast({
                    "type": "apply_error",
                    "session_id": session_id,
                    "message": "Failed to log into Indeed. Check your credentials in Platform Credentials.",
                })
                now = datetime.now(timezone.utc).isoformat()
                db.update_apply_session(session_id, status="error", completed_at=now)
                session_entry["status"] = "error"
                return None

            result = await agent.run_batch(jobs, max_applies=req.max_applies)
            return result

        except Exception as e:
            broadcast({
                "type": "apply_error",
                "session_id": session_id,
                "message": f"Indeed apply agent error: {str(e)}",
            })
            now = datetime.now(timezone.utc).isoformat()
            db.update_apply_session(session_id, status="error", completed_at=now)
            session_entry["status"] = "error"
            return None
        finally:
            await agent.close_browser()

    agent_task = asyncio.create_task(run_agent())
    session_entry["agent_task"] = agent_task

    async def finalize_session():
        try:
            batch_result = await agent_task
            now = datetime.now(timezone.utc).isoformat()
            if batch_result:
                db.update_apply_session(
                    session_id,
                    status="completed",
                    applied_count=batch_result.applied,
                    skipped_count=batch_result.skipped,
                    error_count=batch_result.errors,
                    completed_at=now,
                    results_json=json.dumps([
                        {"job_id": r.job_id, "company": r.company, "title": r.title,
                         "status": r.status.value, "message": r.message}
                        for r in batch_result.results
                    ]),
                )
                session_entry["status"] = "completed"
                broadcast({
                    "type": "apply_complete",
                    "session_id": session_id,
                    "platform": "indeed",
                    "result": {
                        "applied": batch_result.applied,
                        "skipped": batch_result.skipped,
                        "errors": batch_result.errors,
                    },
                    "message": f"Indeed auto-apply complete: {batch_result.applied} applied, {batch_result.skipped} skipped, {batch_result.errors} errors",
                })
            else:
                session_entry["status"] = "error"
        except Exception:
            now = datetime.now(timezone.utc).isoformat()
            db.update_apply_session(session_id, status="error", completed_at=now)
            session_entry["status"] = "error"
        finally:
            for q in list(subscribers):
                try:
                    q.put_nowait(None)
                except Exception:
                    pass

    asyncio.create_task(finalize_session())

    async def event_generator():
        try:
            while True:
                evt = await main_queue.get()
                if evt is None:
                    break
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("type") in ("apply_complete", "apply_error", "apply_stopped"):
                    break
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if main_queue in subscribers:
                subscribers.remove(main_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ────────────── SEEK Auto-Apply ──────────────

@router.post("/seek/start")
async def start_seek_apply(req: StartApplyRequest, client_id: str = Depends(get_client_id)):
    """
    Start a SEEK auto-apply session for Quick apply jobs.
    Returns SSE stream with real-time progress.
    """
    # 1. Stop any currently running background session to prevent concurrency conflicts
    for existing_id, sdata in list(_active_sessions.items()):
        if sdata.get("client_id", "default") == client_id and sdata.get("status") in ("running", "waiting_for_input"):
            agent = sdata.get("agent")
            if agent:
                try:
                    agent.request_stop()
                except Exception:
                    pass
            db.update_apply_session(existing_id, status="stopped")
            sdata["status"] = "stopped"

    # 2. Validate credentials exist (or fall back to profile email / cached session)
    profile = db.get_profile(session_id=client_id) or {}
    creds = db.get_seek_credentials(client_id=client_id)
    if not creds:
        p_email = (profile.get("email") or "").strip()
        if p_email:
            db.save_seek_credentials(p_email, "", client_id=client_id)
            creds = db.get_seek_credentials(client_id=client_id)
    if not creds:
        raise HTTPException(
            status_code=400,
            detail="SEEK credentials not saved. Please provide your SEEK email first in Platform Credentials."
        )

    # 3. Get profile and resume data
    resume_text = profile.get("resume_text", "")
    if not resume_text:
        raise HTTPException(
            status_code=400,
            detail="No resume uploaded. Please upload your resume first in the Candidate Profile section."
        )

    # 4. Get SEEK jobs to apply to
    jobs = db.get_seek_opportunities_for_apply(max_jobs=req.max_applies, client_id=client_id)
    if not jobs:
        # Fallback: check general opportunities for any with seek in apply_url or source
        all_opps = db.get_opportunities(limit=50, client_id=client_id)
        jobs = [
            o for o in all_opps
            if "seek.com" in (o.get("apply_url") or "").lower() or (o.get("source") or "").lower() == "seek"
        ][:req.max_applies]

    if not jobs:
        raise HTTPException(
            status_code=404,
            detail="No SEEK jobs available to apply to. Run a search first with /job-skill search to discover opportunities."
        )

    # 5. Extract structured resume data
    resume_data = ResumeExtractor.extract_all(resume_text, profile)

    # 6. Create apply session
    session_id = f"apply_seek_{uuid.uuid4().hex[:8]}"
    db.create_apply_session(
        session_id=session_id,
        platform="seek",
        max_applies=req.max_applies,
        total_jobs=len(jobs),
        client_id=client_id,
    )

    loop = asyncio.get_running_loop()
    question_event = asyncio.Event()
    answer_holder: Dict[str, Optional[str]] = {"value": None}
    event_buffer: List[Dict[str, Any]] = []
    subscribers: List[asyncio.Queue] = []
    main_queue: asyncio.Queue = asyncio.Queue()
    subscribers.append(main_queue)

    session_entry: Dict[str, Any] = {
        "session_id": session_id,
        "client_id": client_id,
        "platform": "seek",
        "agent": None,
        "agent_task": None,
        "question_event": question_event,
        "answer_holder": answer_holder,
        "stop_requested": False,
        "event_buffer": event_buffer,
        "subscribers": subscribers,
        "status": "running",
        "jobs": jobs,
        "total_jobs": len(jobs),
        "applied_count": 0,
        "skipped_count": 0,
        "error_count": 0,
        "pending_question": None,
        "loop": loop,
    }

    def broadcast(evt: Dict[str, Any]):
        """Append event to history and push to all connected subscriber queues."""
        event_buffer.append(evt)
        if evt.get("type") == "apply_job_done":
            st = evt.get("status")
            if st == "applied":
                session_entry["applied_count"] += 1
            elif st in ("skipped", "manual_required"):
                session_entry["skipped_count"] += 1
            else:
                session_entry["error_count"] += 1
            db.update_apply_session(
                session_id,
                applied_count=session_entry["applied_count"],
                skipped_count=session_entry["skipped_count"],
                error_count=session_entry["error_count"],
            )

        for q in list(subscribers):
            try:
                q.put_nowait(evt)
            except Exception:
                pass

    session_entry["broadcast"] = broadcast
    _active_sessions[session_id] = session_entry

    async def ask_user_fn(job_title: str, field_name: str, question: str) -> Optional[str]:
        """
        Called by the agent when it needs user input (e.g. 6-digit code or screening question).
        Sets pending question in session & DB, broadcasts SSE event, and waits for response.
        """
        q_data = {
            "job_title": job_title,
            "field_name": field_name,
            "question": question,
        }
        session_entry["status"] = "waiting_for_input"
        session_entry["pending_question"] = q_data
        db.update_apply_session(session_id, pending_question=q_data)

        broadcast({
            "type": "apply_needs_input",
            "session_id": session_id,
            "platform": "seek",
            "job_title": job_title,
            "field_name": field_name,
            "question": question,
            "message": f"SEEK agent needs your input for: {field_name}",
        })

        answer_holder["value"] = None
        question_event.clear()

        try:
            await asyncio.wait_for(question_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            session_entry["status"] = "running"
            session_entry["pending_question"] = None
            db.update_apply_session(session_id, pending_question=None)
            broadcast({
                "type": "apply_input_timeout",
                "session_id": session_id,
                "field_name": field_name,
                "message": f"Input timed out for '{field_name}'. Proceeding...",
            })
            return None

        ans = answer_holder["value"]
        session_entry["status"] = "running"
        session_entry["pending_question"] = None
        db.update_apply_session(session_id, pending_question=None)

        broadcast({
            "type": "apply_input_resolved",
            "session_id": session_id,
            "field_name": field_name,
            "answer": ans,
            "message": f"Answer received for '{field_name}'. Resuming SEEK application...",
        })
        return ans

    broadcast({
        "type": "apply_init",
        "session_id": session_id,
        "platform": "seek",
        "total_jobs": len(jobs),
        "message": f"Initialized SEEK auto-apply session with {len(jobs)} jobs (Quick Apply only)",
    })

    async def run_agent():
        from web.backend.seek_apply_agent import SeekApplyAgent

        agent = SeekApplyAgent(
            credentials=creds,
            resume_data=resume_data,
            profile=profile,
            ask_user_callback=ask_user_fn,
            progress_callback=broadcast,
            db=db,
        )
        session_entry["agent"] = agent

        try:
            await agent.initialize_browser()

            logged_in = await agent.login()
            if not logged_in:
                broadcast({
                    "type": "apply_error",
                    "session_id": session_id,
                    "platform": "seek",
                    "message": "SEEK session inactive or verification required. Please open SEEK (au.seek.com) in Brave or Chrome to log in once, then rerun.",
                })
                now = datetime.now(timezone.utc).isoformat()
                db.update_apply_session(session_id, status="error", completed_at=now)
                session_entry["status"] = "error"
                return None

            result = await agent.run_batch(jobs, max_applies=req.max_applies)
            return result

        except Exception as e:
            broadcast({
                "type": "apply_error",
                "session_id": session_id,
                "platform": "seek",
                "message": f"SEEK apply agent error: {str(e)}",
            })
            now = datetime.now(timezone.utc).isoformat()
            db.update_apply_session(session_id, status="error", completed_at=now)
            session_entry["status"] = "error"
            return None
        finally:
            await agent.close_browser()

    agent_task = asyncio.create_task(run_agent())
    session_entry["agent_task"] = agent_task

    async def finalize_session():
        try:
            batch_result = await agent_task
            now = datetime.now(timezone.utc).isoformat()
            if batch_result:
                db.update_apply_session(
                    session_id,
                    status="completed",
                    applied_count=batch_result.applied,
                    skipped_count=batch_result.skipped,
                    error_count=batch_result.errors,
                    completed_at=now,
                    results_json=json.dumps([
                        {"job_id": r.job_id, "company": r.company, "title": r.title,
                         "status": r.status.value, "message": r.message}
                        for r in batch_result.results
                    ]),
                )
                session_entry["status"] = "completed"
                broadcast({
                    "type": "apply_complete",
                    "session_id": session_id,
                    "platform": "seek",
                    "result": {
                        "applied": batch_result.applied,
                        "skipped": batch_result.skipped,
                        "errors": batch_result.errors,
                    },
                    "message": f"SEEK auto-apply complete: {batch_result.applied} applied, {batch_result.skipped} skipped, {batch_result.errors} errors",
                })
            else:
                session_entry["status"] = "error"
        except Exception:
            now = datetime.now(timezone.utc).isoformat()
            db.update_apply_session(session_id, status="error", completed_at=now)
            session_entry["status"] = "error"
        finally:
            for q in list(subscribers):
                try:
                    q.put_nowait(None)
                except Exception:
                    pass

    asyncio.create_task(finalize_session())

    async def event_generator():
        try:
            while True:
                evt = await main_queue.get()
                if evt is None:
                    break
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("type") in ("apply_complete", "apply_error", "apply_stopped"):
                    break
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if main_queue in subscribers:
                subscribers.remove(main_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ────────────── Unified Start Endpoint ──────────────

@router.post("/start")
async def start_apply(req: StartApplyRequest, client_id: str = Depends(get_client_id)):
    """
    Unified start endpoint for LinkedIn, Indeed, and SEEK auto-apply.
    """
    if req.platform.lower() == "seek":
        return await start_seek_apply(req, client_id=client_id)
    if req.platform.lower() == "indeed":
        return await start_indeed_apply(req, client_id=client_id)
    return await start_linkedin_apply(req, client_id=client_id)

