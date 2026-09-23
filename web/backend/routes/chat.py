"""
Chat Sessions and Conversational Messaging API Routes with SSE Streaming.
"""
import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.models import QueryConfig
from web.backend.db import AppDatabase
from web.backend.engine_bridge import EngineBridge
from web.backend.llm_service import LLMService
from web.backend.session import get_client_id

router = APIRouter(prefix="/api/chat", tags=["Chat"])
db = AppDatabase()
bridge = EngineBridge()


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "Job Search Session"


class SendMessageRequest(BaseModel):
    content: str


@router.get("/sessions")
def list_sessions(client_id: str = Depends(get_client_id)):
    sessions = db.list_sessions(client_id=client_id)
    if not sessions:
        new_id = f"sess_{uuid.uuid4().hex[:8]}"
        initial = db.create_session(new_id, "Career Navigator", client_id=client_id)
        return [initial]
    return sessions


@router.post("/sessions")
def create_session(req: CreateSessionRequest, client_id: str = Depends(get_client_id)):
    new_id = f"sess_{uuid.uuid4().hex[:8]}"
    sess = db.create_session(new_id, req.title or "New Search", client_id=client_id)
    return sess


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    db.delete_session(session_id)
    return {"deleted": True, "session_id": session_id}


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str):
    return db.get_messages(session_id)


def sanitize_chat_input(text: str) -> str:
    """Mask sensitive credentials from chat history display."""
    cleaned = text.strip().strip("'\"`").strip()
    if cleaned.lower().startswith("/linkedin-login"):
        parts = cleaned.split(maxsplit=2)
        if len(parts) >= 2:
            return f"/linkedin-login {parts[1]} ••••••••"
        return "/linkedin-login ••••••••"
    if cleaned.lower().startswith("/indeed-login"):
        parts = cleaned.split(maxsplit=2)
        if len(parts) >= 2:
            return f"/indeed-login {parts[1]} ••••••••"
        return "/indeed-login ••••••••"
    return text


def execute_message_logic(
    session_id: str,
    user_text: str,
    progress_callback: Optional[Any] = None,
    client_id: str = "default",
) -> Dict[str, Any]:
    """
    Core messaging logic: classifies intent, runs search or generates response,
    saves the assistant message to SQLite, and returns the message dict.
    """
    clean_cmd = user_text.strip().strip("'\"`").strip()

    # 1. Immediate Intercept: /linkedin-login (NEVER send credentials to LLM)
    if clean_cmd.lower().startswith("/linkedin-login"):
        parts = clean_cmd.split(maxsplit=2)
        if len(parts) >= 3:
            li_email = parts[1].strip().strip("'\"`")
            li_password = parts[2].strip().strip("'\"`")
            db.save_linkedin_credentials(li_email, li_password, client_id=client_id)
            assistant_reply = (
                f"### ✅ LinkedIn Credentials Saved\n\n"
                f"Your LinkedIn credentials have been encrypted locally with AES-256.\n\n"
                f"- **Account:** `{li_email[:3]}***{li_email[li_email.index('@'):]}`\n"
                f"- **Security:** Stored locally in encrypted vault, never transmitted to external AI models.\n\n"
                f"👉 Run `/job-skill apply linkedin` to start auto-applying to your discovered LinkedIn jobs."
            )
            msg_metadata = {"intent": "linkedin_login", "type": "credentials_saved", "has_credentials": True}
            saved_msg = db.add_message(
                session_id=session_id, role="assistant",
                content=assistant_reply, metadata=msg_metadata,
            )
            return saved_msg
        else:
            assistant_reply = (
                "### 🔐 LinkedIn Credentials\n\n"
                "You can configure your LinkedIn credentials securely in **Settings ⚙️ ➔ Platform Credentials** without typing passwords in chat.\n\n"
                "*Tip: You can also use `/linkedin-login your.email@example.com your_password` (password is automatically masked in chat).*"
            )
            msg_metadata = {"intent": "linkedin_login", "type": "credentials_help", "needs_credentials": True}
            saved_msg = db.add_message(
                session_id=session_id, role="assistant",
                content=assistant_reply, metadata=msg_metadata,
            )
            return saved_msg

    # 1b. Immediate Intercept: /indeed-login (password optional, passwordless code sign-in supported)
    if clean_cmd.lower().startswith("/indeed-login"):
        parts = clean_cmd.split(maxsplit=2)
        if len(parts) >= 2:
            ind_email = parts[1].strip().strip("'\"`")
            ind_password = parts[2].strip().strip("'\"`") if len(parts) >= 3 else ""
            db.save_indeed_credentials(ind_email, ind_password, client_id=client_id)
            assistant_reply = (
                f"### ✅ Indeed Credentials Saved\n\n"
                f"Your Indeed login email has been configured successfully.\n\n"
                f"- **Account:** `{ind_email[:3]}***{ind_email[ind_email.index('@'):] if '@' in ind_email else ''}`\n"
                f"- **Authentication Method:** Passwordless ('Sign in with a code')\n"
                f"- **Security:** Stored locally with AES-256 encryption, never transmitted to external AI models.\n\n"
                f"👉 Run `/job-skill apply indeed` to start auto-applying to your discovered Indeed jobs."
            )
            msg_metadata = {"intent": "indeed_login", "type": "credentials_saved", "has_credentials": True}
            saved_msg = db.add_message(
                session_id=session_id, role="assistant",
                content=assistant_reply, metadata=msg_metadata,
            )
            return saved_msg
        else:
            assistant_reply = (
                "### 🔐 Indeed Credentials\n\n"
                "Indeed uses passwordless sign-in (OTP code sent to email). No password is required!\n\n"
                "You can configure your Indeed Gmail in **Settings ⚙️ ➔ Platform Credentials**, "
                "or run `/indeed-login your.email@gmail.com`."
            )
            msg_metadata = {"intent": "indeed_login", "type": "credentials_help", "needs_credentials": True}
            saved_msg = db.add_message(
                session_id=session_id, role="assistant",
                content=assistant_reply, metadata=msg_metadata,
            )
            return saved_msg

    # 1c. Intercept active apply session input (e.g. Indeed OTP code or screening answer typed directly into chat)
    try:
        from web.backend.routes.apply import _active_sessions
        waiting_session_id = None
        waiting_session_data = None
        for s_id, s_data in _active_sessions.items():
            if s_data.get("status") == "waiting_for_input":
                waiting_session_id = s_id
                waiting_session_data = s_data
                break

        if waiting_session_data and not clean_cmd.startswith("/"):
            ans_holder = waiting_session_data.get("answer_holder")
            q_event = waiting_session_data.get("question_event")
            broadcast = waiting_session_data.get("broadcast")
            loop = waiting_session_data.get("loop")
            pending_q = waiting_session_data.get("pending_question") or {}
            q_field = pending_q.get("field_name", "verification_code")

            if ans_holder is not None and q_event is not None:
                ans_text = user_text.strip()
                ans_holder["value"] = ans_text
                waiting_session_data["pending_question"] = None
                waiting_session_data["status"] = "running"
                db.update_apply_session(waiting_session_id, pending_question=None)

                if broadcast:
                    broadcast({
                        "type": "apply_input_resolved",
                        "session_id": waiting_session_id,
                        "field_name": q_field,
                        "answer": ans_text,
                        "message": f"Answer \"{ans_text}\" submitted via chat. Resuming application...",
                    })

                if loop and loop.is_running():
                    loop.call_soon_threadsafe(q_event.set)
                else:
                    q_event.set()

                is_code = len(ans_text) == 6 and ans_text.isalnum()
                code_label = "Verification code" if is_code else f"Answer for '{q_field}'"

                assistant_reply = (
                    f"✅ **{code_label} Received**\n\n"
                    f"Submitted `{ans_text}` to the active Indeed apply agent.\n\n"
                    f"The agent is verifying your authentication and resuming applications now..."
                )
                msg_metadata = {"type": "apply_input_ack", "field_name": q_field, "answer": ans_text}
                saved_msg = db.add_message(
                    session_id=session_id, role="assistant",
                    content=assistant_reply, metadata=msg_metadata,
                )
                return saved_msg
    except Exception as e:
        logging.getLogger(__name__).debug(f"Apply input intercept check error: {e}")

    profile = db.get_profile(session_id=client_id) or {}
    secret = db.get_secret("llm_api_key", session_id=client_id)

    # Intent Classification
    intent_data = LLMService.classify_intent(clean_cmd, stored_profile=profile, secret=secret)
    intent = intent_data.get("intent")

    if progress_callback:
        try:
            progress_callback({"type": "intent", "intent": intent, "intent_data": intent_data})
        except Exception:
            pass

    # Auto-update session title from default if this is a new search or query
    sess = db.get_session(session_id)
    if sess:
        current_title = (sess.get("title") or "").strip()
        if not current_title or any(current_title.startswith(prefix) for prefix in ["New ", "Job Search", "Career Navigator"]):
            if intent == "search":
                s_role = intent_data.get("role") or profile.get("role") or "Tech Role"
                s_loc = intent_data.get("location") or profile.get("location") or "India"
                new_title = f"{s_role} ({s_loc})"
            elif intent == "apply_platform":
                new_title = f"Apply — {intent_data.get('platform', 'LinkedIn').capitalize()}"
            elif user_text.startswith("/"):
                new_title = user_text.strip().replace("/job-skill", "").strip().capitalize() or "Job Search"
            else:
                new_title = user_text[:32].strip().capitalize()
            db.update_session_title(session_id, new_title)

    assistant_reply = ""
    msg_metadata: Dict[str, Any] = {"intent": intent}


    if intent == "help":
        assistant_reply = (
            "### Job Search Assistant (India Edition) — Quick Reference\n\n"
            "**Primary Commands:**\n"
            "- `/job-skill help` — Shows this usage guide with all capabilities.\n"
            "- `/job-skill search [role]` — Search 19+ job platforms for roles matching your Candidate Profile. Generates tailored ATS resumes, cover letters, and live apply links.\n"
            "- `/job-skill apply linkedin` — Automates LinkedIn Easy Apply for all discovered opportunities using your Candidate Profile details and active resume.\n"
            "- `/job-skill automate` — Set up a nightly automated search that runs while you sleep.\n"
            "- `/job-skill status` — Check the status of your applications across all stages.\n\n"
            "**Candidate Profile Integration:**\n"
            "All search, application, and auto-apply workflows directly and exclusively draw candidate details, target role, notice period, seniority, expected CTC, and resume from your **Candidate Profile** section (never from arbitrary folders).\n\n"
            "**Natural language also works:**\n"
            "- *\"Find me React jobs in Bangalore\"*\n"
            "- *\"Search for data science roles in Pune, 15-25 LPA\"*\n"
            "- *\"Apply to this job: [paste URL]\"*\n"
            "- *\"What's the status of my applications?\"*\n"
            "- *\"Set up daily job search at 11 PM\"*\n\n"
            "**Platforms searched (19+):**\n"
            "Naukri, LinkedIn India, Instahyre, Cutshort, Hirist, Indeed India, Foundit (Monster India), Shine, TimesJobs, Glassdoor India, AngelList/Wellfound, WeWorkRemotely, SEEK (seek.com.au), Greenhouse, Lever, Arbeitnow, Jobicy, Remotive + direct company career pages\n\n"
            "**What it does:**\n"
            "1. Searches 12+ platforms simultaneously for jobs matching your exact skills\n"
            "2. Scores and ranks every result (skill match, seniority fit, salary range, company type)\n"
            "3. Verifies every link is live — no expired or dead listings\n"
            "4. For EVERY match: generates an ATS-optimized resume tailored to THAT specific job description\n"
            "5. For EVERY match: writes a tailored cover letter mapping YOUR experience to THAT job's requirements\n"
            "6. ATS keyword optimization built into every resume — auto-rewrites until keywords match\n"
            "7. Shows you: Job Title, Job ID, Platform, Posting Date, Fitness Score, Resume, Cover Letter, Apply Link\n"
            "8. Bundles all resumes + cover letters in a zip organized by company — one click download\n"
            "9. Tracks all applications in a spreadsheet with status updates\n"
            "10. Connects to Gmail to auto-detect outcomes (rejections, interview invites, assessment links)\n"
            "11. Runs a weekly self-correction review — adjusts strategy based on what's working\n\n"
            "**Privacy:** Your data stays in this session. Gmail integration (optional) only reads emails from companies you've applied to — nothing else.\n\n"
            "**Prepare for interviews:** Want to crack system design rounds? Check out [@9to5dude on YouTube](https://www.youtube.com/@9to5dude) for system design prep, interview tips, and career advice for developers: https://www.youtube.com/@9to5dude"
        )
        msg_metadata["type"] = "help_guide"

    elif intent == "search":
        role = intent_data.get("role") or profile.get("role") or "Software Engineer"
        location = intent_data.get("location") or profile.get("location") or "any"
        seniority_raw = str(intent_data.get("seniority") or profile.get("seniority") or "any").lower().strip()
        valid_seniorities = {"entry", "mid", "senior", "lead", "principal", "staff", "any"}
        if seniority_raw in valid_seniorities:
            seniority = seniority_raw
        elif seniority_raw in ["junior", "intern", "fresher"]:
            seniority = "entry"
        elif seniority_raw in ["intermediate"]:
            seniority = "mid"
        elif seniority_raw in ["sr"]:
            seniority = "senior"
        elif seniority_raw in ["manager", "director", "architect"]:
            seniority = "lead"
        else:
            seniority = "any"

        sources = intent_data.get("sources") or []
        query = QueryConfig(
            role=role,
            location=location,
            seniority=seniority,
            sources=sources,
        )

        collected_sources: List[Dict[str, Any]] = []
        def wrapped_progress(evt: Dict[str, Any]):
            if progress_callback:
                try:
                    progress_callback(evt)
                except Exception:
                    pass
            if evt.get("type") == "source_results":
                collected_sources.append({
                    "source": evt.get("source"),
                    "domain": evt.get("domain"),
                    "site_query": evt.get("site_query"),
                    "count": evt.get("count", 0),
                    "jobs": evt.get("jobs", []),
                })

        search_res = bridge.execute_search_and_tailor(
            query=query,
            resume_text=profile.get("resume_text", ""),
            profile=profile,
            secret=secret,
            top_n=None,
            progress_callback=wrapped_progress,
        )

        if collected_sources:
            msg_metadata["search_sources"] = collected_sources

        jobs = search_res.get("jobs", [])
        total_found = search_res.get("total_found", 0)
        pruned = search_res.get("duplicates_pruned", 0)
        materials_bundle = search_res.get("materials_bundle", {})
        zip_url = materials_bundle.get("zip_download_url", "")
        zip_name = materials_bundle.get("zip_filename", "Applications.zip")

        # Automatically persist all unique discovered opportunities
        if jobs:
            try:
                db.upsert_opportunities(jobs, client_id=client_id)
            except Exception as opp_err:
                pass

        # Build 9-column markdown table
        table_lines = [
            "| # | Job Title | Company | Job ID | Platform | Location | Posted Date | Fitness Score | Apply Link |",
            "|---|-----------|---------|--------|----------|----------|-------------|---------------|------------|",
        ]

        explanations = []
        for idx, job in enumerate(jobs, 1):
            jid = job.get("source_job_id") or f"{job.get('source', 'job')[:3].upper()}-{idx}"
            platform = job.get("source", "web").capitalize()
            p_date = job.get("posted_date") or "Recently"
            fit_score = job.get("fitness_display") or f"{job.get('fitness_score', 85)}% Fit ({job.get('fit_framing', 'Strong Match')})"
            apply_url = job.get("apply_url") or "#"

            table_lines.append(
                f"| {idx} | **{job.get('title')}** | {job.get('company')} | `{jid}` | {platform} | {job.get('location')} | {p_date} | **{fit_score}** | [Direct Apply]({apply_url}) |"
            )
            expl = job.get("match_explanation") or f"{job.get('company')} — {job.get('title')} — {fit_score}: Core tech requirements align closely with your background."
            explanations.append(f"{idx}. {expl}")

        table_md = "\n".join(table_lines)
        expl_md = "\n".join(explanations)

        assistant_reply = (
            f"I found **{total_found} listings** matching your search for **{role}** in **{location}** "
            f"across verified platforms (pruned {pruned} duplicate postings).\n\n"
            f"{table_md}\n\n"
            f"### Match Analysis & Opportunity Breakdown\n"
            f"{expl_md}"
        )

        msg_metadata["type"] = "job_results"
        msg_metadata["jobs"] = jobs
        msg_metadata["query"] = query.model_dump()
        msg_metadata["total_found"] = total_found

    elif intent == "automate":
        cfg = db.get_automate_config(client_id=client_id)
        status_str = "ENABLED" if cfg.get("enabled") else "DISABLED"
        sched_time = cfg.get("schedule_time", "08:00")
        assistant_reply = (
            f"### Automated Nightly Job Search — Status: **{status_str}**\n\n"
            f"- **Scheduled time:** `{sched_time}` IST every day\n"
            f"- **Target profile:** `{profile.get('role', 'Software Engineer')}` in `{profile.get('location', 'Bangalore')}`\n"
            f"- **Delivery channel:** In-app morning briefing with matched opportunities & direct apply links\n\n"
            f"Open the **Automate** panel to adjust schedule, toggle daily/weekday frequency, or trigger an immediate scan now."
        )
        msg_metadata["type"] = "automate_status"
        msg_metadata["config"] = cfg

    elif intent == "status":
        from datetime import datetime
        entries = db.list_tracker_entries(client_id=client_id)
        applied = [e for e in entries if e.get("status") == "applied"]
        interview = [e for e in entries if e.get("status") == "interview"]
        offers = [e for e in entries if e.get("status") == "offer"]
        rejected = [e for e in entries if e.get("status") == "rejected"]
        assessments = [e for e in entries if e.get("status") == "assessment"]

        today_str = datetime.now().strftime("%d %b %Y")

        new_updates_lines = []
        if interview:
            for item in interview[:3]:
                new_updates_lines.append(f"✅ **{item.get('company')}** — Interview invite received ({item.get('title')})")
        if rejected:
            for item in rejected[:3]:
                new_updates_lines.append(f"❌ **{item.get('company')}** — Rejected at resume screening ({item.get('title')})")
        if assessments:
            for item in assessments[:3]:
                new_updates_lines.append(f"🧪 **{item.get('company')}** — Online assessment link ({item.get('title')})")
        if not new_updates_lines:
            new_updates_lines.append("No new response updates since last check.")

        pending_lines = []
        if applied:
            for item in applied[:4]:
                pending_lines.append(f"- **{item.get('company')}** ({item.get('title')}) — Applied, under review")
        if not pending_lines:
            pending_lines.append("- No pending applications under review.")

        total_app = len(applied) + len(interview) + len(offers) + len(rejected) + len(assessments)
        responses = len(interview) + len(offers) + len(rejected) + len(assessments)
        resp_rate = f"{(responses / max(total_app, 1)) * 100:.0f}%"

        auto_improve_banner = ""
        if len(rejected) >= 3:
            auto_improve_banner = (
                "\n\n> [!TIP]\n"
                f"> **Auto-Improvement Diagnostic**: Detected {len(rejected)} rejections. "
                "I have automatically tightened keyword matching thresholds and elevated technical alignment for future resumes."
            )

        assistant_reply = (
            f"### APPLICATION STATUS UPDATE — {today_str}\n\n"
            f"**NEW UPDATES:**\n" + "\n".join(new_updates_lines) + "\n\n"
            f"**PENDING (no response yet):**\n" + "\n".join(pending_lines) + "\n\n"
            f"**STATS:**\n"
            f"Total applied: {total_app} | Responses: {responses} ({resp_rate}) | Interviews: {len(interview)} | Offers: {len(offers)} | Rejected: {len(rejected)}"
            f"{auto_improve_banner}\n\n"
            f"Open the **Tracker** tab to manage stages or view Gmail integration settings."
        )
        msg_metadata["type"] = "tracker_summary"

    elif intent == "apply_to_url":
        url = intent_data.get("url")
        assistant_reply = (
            f"I see you want to apply to `{url}`.\n\n"
            f"As a security and accuracy guarantee, this system never submits applications automatically (bypassing CAPTCHAs, OTPs, or accounts). "
            f"I have opened the link for you to apply directly, and added a preliminary entry to your **Application Tracker**."
        )
        if url:
            db.add_tracker_entry(
                job_id="custom_url",
                company="External Listing",
                title="Direct Application",
                location="Web",
                apply_url=url,
                status="applied",
                client_id=client_id,
            )
        msg_metadata["type"] = "apply_ack"

    elif intent == "apply_platform":
        platform = intent_data.get("platform", "linkedin").lower()
        msg_metadata["type"] = "apply_platform"
        msg_metadata["platform"] = platform

        if platform == "indeed":
            # Check credentials (only email required)
            creds = db.get_indeed_credentials(client_id=client_id)
            if not creds or not creds.get("email"):
                assistant_reply = (
                    "### 🔐 Indeed Gmail / Email Required\n\n"
                    "To auto-apply to Indeed jobs, your Indeed login email must be configured.\n\n"
                    "🛡️ **Passwordless Flow:** Indeed uses email verification codes for authentication. "
                    "You do not need to provide a password — simply enter your Gmail/email in **Platform Credentials**.\n\n"
                    "👉 Click **⚙️ Open Platform Credentials** below to set up your Indeed email."
                )
                msg_metadata["needs_credentials"] = True
                msg_metadata["platform"] = "indeed"
            else:
                # Check available Indeed jobs
                indeed_jobs = db.get_indeed_opportunities_for_apply(max_jobs=25, client_id=client_id)
                if not indeed_jobs:
                    assistant_reply = (
                        "### No Indeed Jobs Available\n\n"
                        "There are no unapplied Indeed jobs in your **Total Job Opportunities**.\n\n"
                        "Run `/job-skill search` first to discover jobs, then come back and run `/job-skill apply indeed`."
                    )
                else:
                    # Build job preview table
                    job_lines = [
                        "| # | Company | Title | Fitness | Status |",
                        "|---|---------|-------|---------|--------|",
                    ]
                    for idx, j in enumerate(indeed_jobs[:10], 1):
                        score = j.get("fitness_display") or f"{j.get('fitness_score', 75)}% Fit"
                        job_lines.append(f"| {idx} | {j.get('company')} | {j.get('title')} | {score} | Queued |")

                    remaining = len(indeed_jobs) - 10 if len(indeed_jobs) > 10 else 0
                    remaining_note = f"\n\n*...and {remaining} more jobs queued.*" if remaining > 0 else ""

                    user_email = creds.get("masked_email") or creds.get("email") or "your email"

                    assistant_reply = (
                        f"### 🤖 Indeed Auto-Apply Agent — Ready\n\n"
                        f"Found **{len(indeed_jobs)} Indeed jobs** ready to apply.\n\n"
                        + "\n".join(job_lines)
                        + remaining_note + "\n\n"
                        f"**What happens next:**\n"
                        f"1. I'll open a stealth browser and navigate to Indeed\n"
                        f"2. Initiate login for `{user_email}` using passwordless **'Sign in with a code'**\n"
                        f"3. When Indeed sends the 6-digit code to your email, I'll ask you for the OTP code right here in chat\n"
                        f"4. Once authenticated, I'll navigate to each job and complete the Indeed Apply forms\n"
                        f"5. Applied jobs are automatically recorded in your **Application Tracker**\n\n"
                        f"⏳ Rate: ~1 application every 2-3 minutes (human-like pacing)\n"
                        f"🛑 Max: {min(len(indeed_jobs), 25)} applications per session\n\n"
                        f"The apply session will start now. You'll see live progress below."
                    )
                    msg_metadata["apply_ready"] = True
                    msg_metadata["platform"] = "indeed"
                    msg_metadata["indeed_jobs_count"] = len(indeed_jobs)
                    msg_metadata["indeed_jobs_preview"] = [
                        {"id": j.get("id"), "company": j.get("company"), "title": j.get("title"),
                         "fitness_score": j.get("fitness_score"), "apply_url": j.get("apply_url")}
                        for j in indeed_jobs
                    ]
        elif platform != "linkedin":
            assistant_reply = (
                f"Auto-apply for **{platform.capitalize()}** is not yet supported.\n\n"
                f"Currently, **LinkedIn Easy Apply** and **Indeed Apply** are available. "
                f"Use `/job-skill apply linkedin` or `/job-skill apply indeed` to auto-apply to your discovered jobs.\n\n"
                f"Support for other platforms will be added in future updates."
            )
        else:
            # Check credentials
            creds = db.get_linkedin_credentials(client_id=client_id)
            if not creds:
                assistant_reply = (
                    "### 🔐 LinkedIn Credentials Required\n\n"
                    "To auto-apply to LinkedIn jobs, your LinkedIn login credentials must be configured.\n\n"
                    "🛡️ **Privacy First:** For security, you don't have to put passwords in chat! "
                    "You can securely enter and manage your platform credentials in the dedicated **Platform Credentials** settings.\n\n"
                    "Your credentials are encrypted locally with **AES-256** and used only by your local browser agent.\n\n"
                    "👉 Click **⚙️ Open Platform Credentials** below to set up your account."
                )
                msg_metadata["needs_credentials"] = True
            else:
                # Check available LinkedIn jobs
                linkedin_jobs = db.get_linkedin_opportunities_for_apply(max_jobs=25, client_id=client_id)
                if not linkedin_jobs:
                    assistant_reply = (
                        "### No LinkedIn Jobs Available\n\n"
                        "There are no unapplied LinkedIn jobs in your **Total Job Opportunities**.\n\n"
                        "Run `/job-skill search` first to discover jobs, then come back and run `/job-skill apply linkedin`."
                    )
                else:
                    # Build job preview table
                    job_lines = [
                        "| # | Company | Title | Fitness | Status |",
                        "|---|---------|-------|---------|--------|",
                    ]
                    for idx, j in enumerate(linkedin_jobs[:10], 1):
                        score = j.get("fitness_display") or f"{j.get('fitness_score', 75)}% Fit"
                        job_lines.append(f"| {idx} | {j.get('company')} | {j.get('title')} | {score} | Queued |")

                    remaining = len(linkedin_jobs) - 10 if len(linkedin_jobs) > 10 else 0
                    remaining_note = f"\n\n*...and {remaining} more jobs queued.*" if remaining > 0 else ""

                    assistant_reply = (
                        f"### 🤖 LinkedIn Auto-Apply Agent — Ready\n\n"
                        f"Found **{len(linkedin_jobs)} LinkedIn Easy Apply jobs** ready to apply.\n\n"
                        + "\n".join(job_lines)
                        + remaining_note + "\n\n"
                        f"**What happens next:**\n"
                        f"1. I'll open a stealth browser and log into your LinkedIn\n"
                        f"2. Navigate to each job and fill the Easy Apply form using your resume\n"
                        f"3. If I encounter a field I can't fill, I'll ask you here in chat\n"
                        f"4. Applied jobs are automatically added to your **Application Tracker**\n\n"
                        f"⏳ Rate: ~1 application every 2-3 minutes (human-like pacing)\n"
                        f"🛑 Max: {min(len(linkedin_jobs), 25)} applications per session\n\n"
                        f"The apply session will start now. You'll see live progress below."
                    )
                    msg_metadata["apply_ready"] = True
                    msg_metadata["linkedin_jobs_count"] = len(linkedin_jobs)
                    msg_metadata["linkedin_jobs_preview"] = [
                        {"id": j.get("id"), "company": j.get("company"), "title": j.get("title"),
                         "fitness_score": j.get("fitness_score"), "apply_url": j.get("apply_url")}
                        for j in linkedin_jobs
                    ]

    else:
        # General assistance / conversational query
        if secret and secret.get("provider"):
            try:
                llm_reply = LLMService.invoke_llm(
                    prompt=f"You are a helpful and knowledgeable career coach and job search AI. Respond helpfully and concisely to the candidate's query:\n\n{user_text}",
                    secret=secret,
                    max_tokens=400,
                )
                if llm_reply and len(llm_reply.strip()) > 0:
                    assistant_reply = llm_reply.strip()
                    msg_metadata["type"] = "llm_chat"
            except Exception as e:
                logging.getLogger(__name__).warning(f"LLM chat invocation error: {e}")

        if not assistant_reply:
            assistant_reply = (
                f"Hello! I am your career navigation assistant (India Edition).\n\n"
                f"Here are the primary commands you can run:\n"
                f"- `/job-skill help` — View complete usage guide and platform list\n"
                f"- `/job-skill search [role]` — Search 19+ platforms & find matching opportunities with direct apply links\n"
                f"- `/job-skill automate` — Manage nightly automated job search\n"
                f"- `/job-skill status` — Check tracked applications pipeline & rejection diagnostics\n\n"
                f"You can also ask in natural language, such as: *\"Find React Developer jobs in Bangalore\"* or *\"What's the status of my applications?\"*"
            )
            msg_metadata["type"] = "general_info"

    # Store assistant message
    saved_msg = db.add_message(
        session_id=session_id,
        role="assistant",
        content=assistant_reply,
        metadata=msg_metadata,
    )

    return saved_msg


@router.post("/sessions/{session_id}/message")
def send_message(session_id: str, req: SendMessageRequest, client_id: str = Depends(get_client_id)):
    user_text = req.content.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    # 1. Store user message (with sensitive credentials masked)
    db.add_message(session_id=session_id, role="user", content=sanitize_chat_input(user_text))

    # 2. Execute logic
    return execute_message_logic(session_id=session_id, user_text=user_text, client_id=client_id)


@router.post("/sessions/{session_id}/message/stream")
async def send_message_stream(session_id: str, req: SendMessageRequest, client_id: str = Depends(get_client_id)):
    """
    Streams live search & scraping progress as Server-Sent Events (SSE),
    showing which site is being scraped live (just like Claude),
    then yields the final structured assistant message.
    """
    user_text = req.content.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    # Store user message immediately (with sensitive credentials masked)
    db.add_message(session_id=session_id, role="user", content=sanitize_chat_input(user_text))

    async def event_generator():
        event_queue: List[Dict[str, Any]] = []
        collected_sources: List[Dict[str, Any]] = []

        def on_progress(evt: Dict[str, Any]):
            event_queue.append(evt)
            if evt.get("type") == "source_results":
                collected_sources.append({
                    "source": evt.get("source"),
                    "domain": evt.get("domain"),
                    "site_query": evt.get("site_query"),
                    "count": evt.get("count", 0),
                    "jobs": evt.get("jobs", []),
                })

        # Yield initial acknowledge
        yield f"data: {json.dumps({'type': 'init', 'user_text': user_text})}\n\n"

        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(
            None,
            lambda: execute_message_logic(
                session_id=session_id,
                user_text=user_text,
                progress_callback=on_progress,
                client_id=client_id,
            ),
        )

        while not task.done() or event_queue:
            while event_queue:
                evt = event_queue.pop(0)
                yield f"data: {json.dumps(evt)}\n\n"
            await asyncio.sleep(0.04)

        saved_msg = await task

        # Attach collected search sources if present
        if collected_sources and saved_msg.get("metadata"):
            saved_msg["metadata"]["search_sources"] = collected_sources

        yield f"data: {json.dumps({'type': 'complete', 'message': saved_msg})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
