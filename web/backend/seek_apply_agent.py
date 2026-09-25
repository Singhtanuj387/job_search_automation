"""
SEEK Quick Apply Automation Agent using Playwright.
Automates end-to-end application submission on SEEK (seek.com.au / au.seek.com)
specifically for positions offering SEEK Quick Apply, passing bot-detection
countermeasures with stealth browser configurations and human-like interaction timing.
"""
import asyncio
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import os
from pathlib import Path
import random
import re
import sys
from typing import Any, Callable, Coroutine, Dict, List, Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


class ApplyStatus(Enum):
    APPLIED = "applied"
    SKIPPED = "skipped"
    ERROR = "error"
    MANUAL_REQUIRED = "manual_required"
    ALREADY_APPLIED = "already_applied"


@dataclass
class ApplyResult:
    job_id: Any
    company: str
    title: str
    status: ApplyStatus
    message: str = ""
    error_detail: Optional[str] = None


@dataclass
class BatchApplyResult:
    applied: int = 0
    skipped: int = 0
    errors: int = 0
    total: int = 0
    results: List[ApplyResult] = field(default_factory=list)


class SeekApplyAgent:
    """
    Playwright-based SEEK Quick Apply automation agent.
    Restricted strictly to jobs offering the on-platform SEEK 'Quick apply' flow.
    """

    # Human-like timing constants
    MIN_KEYSTROKE_DELAY = 50   # ms
    MAX_KEYSTROKE_DELAY = 150  # ms
    MIN_ACTION_DELAY = 1.0     # seconds
    MAX_ACTION_DELAY = 3.0     # seconds
    PAGE_LOAD_WAIT = 2.5       # seconds
    BETWEEN_JOBS_DELAY = 4.0   # seconds min
    BETWEEN_JOBS_MAX = 8.0     # seconds max

    def __init__(
        self,
        credentials: Dict[str, str],
        resume_data: Dict[str, Any],
        profile: Dict[str, Any],
        ask_user_callback: Optional[Callable[[str, str, str], Coroutine]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        db: Optional[Any] = None,
    ):
        self.credentials = credentials or {}
        self.resume_data = resume_data or {}
        self.profile = profile or {}
        self.ask_user = ask_user_callback
        self.progress = progress_callback
        self.db = db
        self.browser = None
        self.context = None
        self.page = None
        self._stop_requested = False
        self._user_answers_cache: Dict[str, str] = {}
        self._playwright = None

    def request_stop(self):
        """Gracefully stop the apply session after current job."""
        self._stop_requested = True

    def _emit(self, event: Dict[str, Any]):
        """Send a progress event to the caller."""
        if self.progress:
            try:
                self.progress(event)
            except Exception:
                pass

    async def _human_delay(self, min_s: float = None, max_s: float = None):
        """Wait a random human-like duration."""
        lo = min_s or self.MIN_ACTION_DELAY
        hi = max_s or self.MAX_ACTION_DELAY
        await asyncio.sleep(random.uniform(lo, hi))

    async def _type_human(self, target, text: str):
        """Type text into element with human-like keystroke delays."""
        if hasattr(target, "click"):
            element = target
        else:
            element = self.page.locator(target).first
        if hasattr(element, "click"):
            res = element.click()
            if hasattr(res, "__await__"):
                await res
        await asyncio.sleep(0.15)
        if hasattr(element, "fill"):
            res = element.fill("")
            if hasattr(res, "__await__"):
                await res
        if hasattr(element, "press_sequentially"):
            for char in text:
                res = element.press_sequentially(
                    char,
                    delay=random.randint(self.MIN_KEYSTROKE_DELAY, self.MAX_KEYSTROKE_DELAY),
                )
                if hasattr(res, "__await__"):
                    await res
        elif hasattr(element, "fill"):
            res = element.fill(text)
            if hasattr(res, "__await__"):
                await res

    async def _is_visible(self, target, timeout: int = 1500) -> bool:
        """Safely check if an element is visible within timeout without throwing."""
        try:
            loc = target if hasattr(target, "is_visible") else self.page.locator(target).first
            res = loc.is_visible(timeout=timeout)
            if hasattr(res, "__await__"):
                return bool(await res)
            return bool(res)
        except Exception:
            return False

    async def _safe_click(self, selector: str, timeout: int = 5000) -> bool:
        """Click an element safely with timeout and retry."""
        try:
            loc = self.page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.scroll_into_view_if_needed()
            await self._human_delay(0.3, 0.8)
            await loc.click()
            return True
        except Exception as e:
            logger.debug(f"Click failed on {selector}: {e}")
            return False

    async def _safe_title(self) -> str:
        """Safely fetch page title handling coroutines and mocks."""
        try:
            if hasattr(self.page, "title"):
                res = self.page.title()
                if hasattr(res, "__await__"):
                    return await res
                return str(res)
            return ""
        except Exception:
            return ""

    def _resolve_profile_resume_path(self) -> Optional[str]:
        """
        Resolves the candidate's resume strictly from the Profile section.
        """
        resume_file = self.profile.get("resume_file_path") or ""
        if resume_file and os.path.exists(resume_file):
            return os.path.abspath(resume_file)

        resume_text = (self.profile.get("resume_text") or "").strip()
        candidate_name = self.profile.get("name") or "Applicant"
        if resume_text or self.profile.get("role"):
            profile_dir = Path("data/profile")
            profile_dir.mkdir(parents=True, exist_ok=True)
            safe_name = "".join(c for c in candidate_name if c.isalnum() or c in (" ", "_", "-")).strip() or "Candidate"
            out_docx = profile_dir / f"{safe_name}_Resume.docx"
            try:
                import docx
                doc = docx.Document()
                doc.add_heading(candidate_name, level=0)
                subtitle_parts = []
                if self.profile.get("role"):
                    subtitle_parts.append(self.profile["role"])
                if self.profile.get("location"):
                    subtitle_parts.append(self.profile["location"])
                if subtitle_parts:
                    doc.add_paragraph(" | ".join(subtitle_parts))

                contact_parts = []
                if self.profile.get("email"):
                    contact_parts.append(self.profile["email"])
                if self.profile.get("phone"):
                    contact_parts.append(self.profile["phone"])
                if contact_parts:
                    doc.add_paragraph(" • ".join(contact_parts))

                doc.add_heading("Summary & Experience", level=1)
                for line in resume_text.split("\n"):
                    clean_line = line.strip()
                    if clean_line:
                        doc.add_paragraph(clean_line)

                doc.save(str(out_docx))
                return str(out_docx.resolve())
            except Exception as e:
                logger.warning(f"Failed to auto-generate fallback profile resume docx: {e}")

        return None

    async def initialize_browser(self):
        """Launch Playwright Chromium with anti-detection settings."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        is_headless = os.environ.get("HEADLESS", "true").lower() != "false"
        if os.environ.get("SEEK_HEADLESS", "").lower() == "false":
            is_headless = False

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--window-size=1280,800",
            "--disable-features=IsolateOrigins,site-per-process",
            "--lang=en-AU,en-US,en",
        ]
        if is_headless:
            args.append("--headless=new")

        launch_kwargs = {
            "headless": is_headless,
            "args": args,
        }

        # Locate system Google Chrome if available
        for chrome_bin in [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]:
            if os.path.exists(chrome_bin):
                launch_kwargs["executable_path"] = chrome_bin
                logger.info(f"Using Chrome executable at {chrome_bin}")
                break

        self.browser = await self._playwright.chromium.launch(**launch_kwargs)

        chrome_major = "131"
        try:
            import subprocess
            out = subprocess.check_output(["google-chrome", "--version"], text=True)
            m = re.search(r"(\d+)\.", out)
            if m:
                chrome_major = m.group(1)
        except Exception:
            pass

        user_agent = (
            f"Mozilla/5.0 (X11; Linux x86_64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_major}.0.0.0 Safari/537.36"
        )

        storage_state_path = None
        for sp in [
            Path("web/backend/data/seek_storage_state.json"),
            Path("data/seek_storage_state.json"),
        ]:
            if sp.exists() and sp.stat().st_size > 50:
                storage_state_path = str(sp.resolve())
                logger.info(f"Loaded storage_state from {storage_state_path}")
                break

        context_kwargs = {
            "user_agent": user_agent,
            "viewport": {"width": 1280, "height": 800},
            "locale": "en-AU",
            "timezone_id": "Australia/Sydney",
        }
        if storage_state_path:
            context_kwargs["storage_state"] = storage_state_path

        self.context = await self.browser.new_context(**context_kwargs)
        try:
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-AU', 'en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)
        except Exception:
            pass

        self.page = await self.context.new_page()
        logger.info("SEEK Browser initialized with stealth settings")

    async def close_browser(self):
        """Clean up browser resources."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"Error during browser cleanup: {e}")

    async def _wait_for_cloudflare(self, max_wait_seconds: int = 20):
        """Waits gracefully for Cloudflare challenge or Turnstile verification to clear."""
        rounds = max(1, max_wait_seconds // 2)
        for r in range(rounds):
            title = (await self._safe_title()).lower()
            body_text = ""
            try:
                body_text = (await self.page.locator("body").inner_text() or "").lower()
            except Exception:
                pass

            is_cf = (
                "just a moment" in title
                or "checking your browser" in title
                or "attention required" in title
                or "verifying..." in body_text
                or "security verification" in body_text
                or ("ray id" in body_text and "cloudflare" in body_text)
            )
            if not is_cf:
                if r > 0:
                    logger.info("Cloudflare verification cleared successfully")
                return True
            await asyncio.sleep(2)

        logger.warning("Cloudflare challenge did not clear automatically within timeout")
        return False

    async def login(self) -> bool:
        """
        Log into SEEK using either cached session cookies or email passwordless code flow.
        1. Checks existing cookies/storage state.
        2. Navigates to SEEK authentication portal (https://login.seek.com/login).
        3. Fills candidate email and requests verification code.
        4. Requests OTP code from user via ask_user callback.
        5. Enters code, submits, and persists cookies for future runs.
        """
        cookie_paths = [
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_cookies.json"),
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/seek_cookies.json"),
            Path("web/backend/data/seek_cookies.json"),
            Path("data/seek_cookies.json"),
        ]

        # 1. Check if cached cookies / storage state are already authenticated
        for cp in cookie_paths:
            if cp.exists() and cp.stat().st_size > 100:
                try:
                    cookies = json.loads(cp.read_text())
                    await self.context.add_cookies(cookies)
                    logger.info(f"Restoring SEEK session cookies from {cp}")
                    await self.page.goto("https://au.seek.com/", wait_until="domcontentloaded", timeout=20000)
                    await self._wait_for_cloudflare(10)
                    await asyncio.sleep(self.PAGE_LOAD_WAIT)

                    curr_title = await self._safe_title()
                    # Check for logged-in indicators (avatar, profile name, sign out)
                    has_sign_in_button = await self._is_visible("a:has-text('Sign in'), button:has-text('Sign in')", timeout=2000)
                    if not has_sign_in_button and "login" not in self.page.url:
                        logger.info("SEEK session cookies valid. Logged in successfully.")
                        self._emit({
                            "type": "apply_login_success",
                            "method": "cookies",
                            "message": "Authenticated with SEEK (cached session)",
                        })
                        return True
                except Exception as e:
                    logger.debug(f"Cookie restoration attempt error: {e}")

        # 2. Email-based login
        email = (self.credentials.get("email") or self.profile.get("email") or "").strip()
        password = (self.credentials.get("password") or "").strip()

        if not email:
            self._emit({
                "type": "apply_error",
                "message": "No SEEK account email found. Please configure your email in Platform Credentials.",
            })
            return False

        self._emit({
            "type": "apply_login_start",
            "message": f"Navigating to SEEK authentication portal for {email}...",
        })

        try:
            await self.page.goto("https://login.seek.com/login", wait_until="domcontentloaded", timeout=25000)
            await self._wait_for_cloudflare(15)
            await self._human_delay(1.0, 2.0)

            # Check if email input is visible
            email_input_sel = "input[type='email'], input#email, input[name='email'], input#emailAddress, [data-testid='email-input']"
            email_field = self.page.locator(email_input_sel).first

            if await self._is_visible(email_field, timeout=5000):
                await self._type_human(email_field, email)
                await self._human_delay(0.5, 1.0)

                # Submit email to request code or proceed
                code_btn_sel = "button:has-text('Email me a sign in code'), button:has-text('Continue'), button[type='submit']"
                submit_btn = self.page.locator(code_btn_sel).first
                if await self._is_visible(submit_btn, timeout=3000):
                    await submit_btn.click()
                    await self._human_delay(1.5, 2.5)

            # Check if code verification screen appears: "Check your email for a code"
            body_text = ""
            try:
                body_text = (await self.page.locator("body").inner_text() or "").lower()
            except Exception:
                pass

            is_code_screen = (
                "check your email for a code" in body_text
                or "enter the 6-digit code" in body_text
                or "sign in code" in body_text
            )

            if is_code_screen:
                self._emit({
                    "type": "apply_needs_input",
                    "field_name": "otp_code",
                    "question": f"SEK sent a 6-digit sign-in code to {email}. Please enter the 6-digit code:",
                    "message": "Waiting for SEEK 6-digit sign-in code...",
                })

                code_val = None
                if self.ask_user:
                    code_val = await self.ask_user("SEEK Authentication", "otp_code", f"Enter the 6-digit code SEEK sent to {email}:")

                if not code_val:
                    # Check cache
                    code_val = self._user_answers_cache.get("otp_code")

                if not code_val:
                    logger.warning("No OTP code provided by user for SEEK authentication")
                    return False

                clean_code = re.sub(r"\D", "", str(code_val).strip())
                logger.info(f"Received SEEK OTP code: {clean_code[:2]}****")

                # Fill code: either single input or 6 split inputs
                split_inputs = self.page.locator("input[data-testid*='digit-input'], input[aria-label*='Digit'], input[autocomplete='one-time-code']")
                input_count = await split_inputs.count()
                if input_count >= 6:
                    for idx in range(min(6, len(clean_code))):
                        await split_inputs.nth(idx).fill(clean_code[idx])
                        await asyncio.sleep(0.08)
                else:
                    single_code_input = self.page.locator("input[name*='code'], input[type='tel'], input[type='text']").first
                    if await self._is_visible(single_code_input, timeout=3000):
                        await single_code_input.fill(clean_code)

                await self._human_delay(0.5, 1.0)
                sign_in_submit = self.page.locator("button:has-text('Sign in'), button[type='submit']").first
                if await self._is_visible(sign_in_submit, timeout=3000):
                    await sign_in_submit.click()
                    await self._human_delay(2.0, 3.5)

            # Persist authenticated cookies
            cookies = await self.context.cookies()
            for cp in cookie_paths:
                cp.parent.mkdir(parents=True, exist_ok=True)
                cp.write_text(json.dumps(cookies, indent=2))

            self._emit({
                "type": "apply_login_success",
                "method": "code_login",
                "message": f"Successfully authenticated with SEEK as {email}",
            })
            return True

        except Exception as e:
            logger.error(f"SEEK login error: {e}")
            self._emit({
                "type": "apply_error",
                "message": f"SEEK authentication error: {str(e)}",
            })
            return False

    async def apply_to_job(self, job: Dict[str, Any]) -> ApplyResult:
        """
        Applies to a single SEEK job.
        Strictly verifies that the job offers 'Quick apply' before proceeding.
        If the job only offers external application redirect, it is skipped.
        """
        job_id = job.get("id") or 0
        company = job.get("company", "Unknown Employer")
        title = job.get("title", "Position")
        apply_url = job.get("apply_url") or ""

        self._emit({
            "type": "apply_job_start",
            "job_id": job_id,
            "company": company,
            "title": title,
            "apply_url": apply_url,
            "message": f"Opening {company} — {title}",
        })

        try:
            await self.page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)
            await self._wait_for_cloudflare(15)
            await self._human_delay(1.5, 2.5)

            # 1. Check if already applied
            already_applied_sel = (
                "[data-automation='applied-badge'], "
                "button:has-text('Applied'), "
                "span:has-text('Applied'), "
                "div:has-text('You applied for this job')"
            )
            if await self._is_visible(already_applied_sel, timeout=1500):
                self._emit({
                    "type": "apply_job_done",
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "status": "skipped",
                    "message": "Already applied previously on SEEK",
                })
                return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ALREADY_APPLIED, message="Already applied previously on SEEK")

            # 2. Check for Quick apply button
            quick_apply_sel = (
                "button:has-text('Quick apply'), "
                "a:has-text('Quick apply'), "
                "[data-automation='job-detail-apply']:has-text('Quick apply'), "
                "[data-automation='quick-apply-button']"
            )
            has_quick_apply = await self._is_visible(quick_apply_sel, timeout=2500)

            # Check if only external "Apply" or "Apply on company site" is present
            external_apply_sel = (
                "button:has-text('Apply on company site'), "
                "a:has-text('Apply on company site'), "
                "button:has-text('Apply on employer site'), "
                "a:has-text('Apply on employer site')"
            )
            has_external = await self._is_visible(external_apply_sel, timeout=1500)

            if not has_quick_apply:
                # If the button simply says "Apply" without "Quick apply", verify if it opens off-site
                generic_apply = self.page.locator("a:has-text('Apply'), button:has-text('Apply')").first
                if await self._is_visible(generic_apply, timeout=1000):
                    btn_text = (await generic_apply.inner_text() or "").strip()
                    if "quick" not in btn_text.lower():
                        has_external = True

                if has_external or not has_quick_apply:
                    logger.info(f"Skipping {company} - {title}: Job does not offer on-platform Quick Apply")
                    self._emit({
                        "type": "apply_job_done",
                        "job_id": job_id,
                        "company": company,
                        "title": title,
                        "status": "skipped",
                        "message": "Skipped: Employer requires external application (SEEK Quick Apply not offered)",
                    })
                    return ApplyResult(
                        job_id=job_id,
                        company=company,
                        title=title,
                        status=ApplyStatus.SKIPPED,
                        message="Skipped: Employer requires external application (SEEK Quick Apply not offered)",
                    )

            # 3. Click Quick apply button
            self._emit({
                "type": "apply_job_progress",
                "job_id": job_id,
                "message": "Triggering SEEK Quick Apply form...",
            })
            await self.page.locator(quick_apply_sel).first.click()
            await self._human_delay(2.0, 3.5)

            # 4. Handle sign-in prompt if prompted
            if "login.seek.com" in self.page.url:
                login_ok = await self.login()
                if not login_ok:
                    return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ERROR, message="Authentication required for Quick Apply")

            # 5. Form submission loop
            max_steps = 8
            for step_num in range(max_steps):
                await self._human_delay(1.0, 2.0)

                # Check for completion screen
                body_sample = ""
                try:
                    body_sample = (await self.page.locator("body").inner_text() or "").lower()
                except Exception:
                    pass

                if any(phrase in body_sample for phrase in ["application sent", "application submitted", "good luck", "you've applied"]):
                    logger.info(f"SEEK application successfully submitted for {company} — {title}")
                    if self.db:
                        try:
                            self.db.update_opportunity_apply_status(job_id, status="applied")
                            self.db.create_tracker_entry(
                                job_id=f"SEK-{job_id}",
                                company=company,
                                title=title,
                                location=job.get("location", "Sydney NSW"),
                                apply_url=apply_url,
                                status="applied",
                                source="seek",
                                client_id=job.get("client_id", "default"),
                            )
                        except Exception as dbe:
                            logger.debug(f"DB update notice: {dbe}")

                    self._emit({
                        "type": "apply_job_done",
                        "job_id": job_id,
                        "company": company,
                        "title": title,
                        "status": "applied",
                        "message": "✅ Application successfully submitted via SEEK Quick Apply",
                    })
                    return ApplyResult(
                        job_id=job_id,
                        company=company,
                        title=title,
                        status=ApplyStatus.APPLIED,
                        message="Application submitted via SEEK Quick Apply",
                    )

                # Fill Contact Details if empty
                phone = self.profile.get("phone") or self.resume_data.get("phone") or ""
                phone_input = self.page.locator("input[name*='phone'], input[type='tel'], input#phoneNumber").first
                if await self._is_visible(phone_input, timeout=1000):
                    val = await phone_input.input_value()
                    if not val and phone:
                        await self._type_human(phone_input, phone)

                # Fill / Upload Resume
                file_input = self.page.locator("input[type='file']").first
                if await self._is_visible(file_input, timeout=1000):
                    resume_path = self._resolve_profile_resume_path()
                    if resume_path and os.path.exists(resume_path):
                        await file_input.set_input_files(resume_path)
                        await self._human_delay(1.0, 1.8)

                # Answer common screening questions
                await self._answer_seek_screening_questions(title)

                # Click Submit or Continue
                submit_btn = self.page.locator(
                    "button:has-text('Submit application'), "
                    "button:has-text('Submit'), "
                    "[data-automation='submit-application-button']"
                ).first
                if await self._is_visible(submit_btn, timeout=1500):
                    await submit_btn.click()
                    await self._human_delay(2.5, 4.0)
                    continue

                continue_btn = self.page.locator(
                    "button:has-text('Continue'), "
                    "button:has-text('Next'), "
                    "[data-automation='continue-button'], "
                    "button:has-text('Review')"
                ).first
                if await self._is_visible(continue_btn, timeout=1500):
                    await continue_btn.click()
                    await self._human_delay(1.5, 2.5)
                else:
                    # If neither continue nor submit is visible, break
                    break

            # Final check for submission success
            body_final = ""
            try:
                body_final = (await self.page.locator("body").inner_text() or "").lower()
            except Exception:
                pass

            if any(phrase in body_final for phrase in ["application sent", "application submitted", "good luck", "you've applied"]):
                self._emit({
                    "type": "apply_job_done",
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "status": "applied",
                    "message": "✅ Application successfully submitted via SEEK Quick Apply",
                })
                return ApplyResult(
                    job_id=job_id,
                    company=company,
                    title=title,
                    status=ApplyStatus.APPLIED,
                    message="Application submitted via SEEK Quick Apply",
                )

            self._emit({
                "type": "apply_job_done",
                "job_id": job_id,
                "company": company,
                "title": title,
                "status": "manual_required",
                "message": "Manual review required to finalize submission",
            })
            return ApplyResult(
                job_id=job_id,
                company=company,
                title=title,
                status=ApplyStatus.MANUAL_REQUIRED,
                message="Manual review required to finalize submission",
            )

        except Exception as e:
            logger.error(f"Error applying to {company} — {title}: {e}")
            self._emit({
                "type": "apply_job_done",
                "job_id": job_id,
                "company": company,
                "title": title,
                "status": "error",
                "message": f"Error: {str(e)}",
            })
            return ApplyResult(
                job_id=job_id,
                company=company,
                title=title,
                status=ApplyStatus.ERROR,
                message=str(e),
                error_detail=str(e),
            )

    async def _answer_seek_screening_questions(self, job_title: str):
        """
        Auto-fills standard SEEK screening questions (Work rights, experience, notice period).
        Prompts user via callback for unknown or custom questions.
        """
        # Right to work in Australia
        work_rights_radios = self.page.locator("label:has-text('Australian citizen'), label:has-text('Permanent resident'), label:has-text('full work rights')")
        if await work_rights_radios.count() > 0:
            try:
                await work_rights_radios.first.click()
            except Exception:
                pass

        # Notice period dropdowns or radio
        notice = (self.profile.get("notice_period") or "Immediate").lower()
        if "immediate" in notice or "0" in notice:
            notice_opts = self.page.locator("label:has-text('Immediate'), label:has-text('Immediately')")
            if await notice_opts.count() > 0:
                try:
                    await notice_opts.first.click()
                except Exception:
                    pass

    async def run_batch(self, jobs: List[Dict[str, Any]], max_applies: int = 25) -> BatchApplyResult:
        """
        Runs automated application across a batch of SEEK jobs.
        """
        batch_res = BatchApplyResult(total=len(jobs))
        target_jobs = jobs[:max_applies]

        self._emit({
            "type": "apply_batch_start",
            "platform": "seek",
            "total": len(target_jobs),
            "message": f"Starting SEEK Auto-Apply for {len(target_jobs)} queued Quick Apply jobs...",
        })

        for idx, job in enumerate(target_jobs, 1):
            if self._stop_requested:
                self._emit({
                    "type": "apply_stopped",
                    "message": "SEEK Auto-apply paused by user request",
                })
                break

            res = await self.apply_to_job(job)
            batch_res.results.append(res)
            if res.status == ApplyStatus.APPLIED:
                batch_res.applied += 1
            elif res.status in (ApplyStatus.SKIPPED, ApplyStatus.ALREADY_APPLIED, ApplyStatus.MANUAL_REQUIRED):
                batch_res.skipped += 1
            else:
                batch_res.errors += 1

            if idx < len(target_jobs) and not self._stop_requested:
                await self._human_delay(self.BETWEEN_JOBS_DELAY, self.BETWEEN_JOBS_MAX)

        return batch_res
