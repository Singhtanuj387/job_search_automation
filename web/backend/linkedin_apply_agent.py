"""
LinkedIn Auto-Apply Agent.
Uses Playwright to automate LinkedIn Easy Apply job applications.
Extracts form data from uploaded resume, asks the user for missing fields via callback.
"""
import asyncio
import json
import logging
import os
import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from web.backend.indeed_apply_agent import _companies_match

logger = logging.getLogger(__name__)


class ApplyStatus(str, Enum):
    APPLIED = "applied"
    SKIPPED = "skipped"
    ERROR = "error"
    MANUAL_REQUIRED = "manual_required"
    NEEDS_INPUT = "needs_input"
    IN_PROGRESS = "in_progress"


@dataclass
class ApplyResult:
    job_id: int
    company: str
    title: str
    status: ApplyStatus
    message: str = ""
    apply_url: str = ""


@dataclass
class BatchResult:
    session_id: str
    total: int = 0
    applied: int = 0
    skipped: int = 0
    errors: int = 0
    results: List[ApplyResult] = field(default_factory=list)


class LinkedInApplyAgent:
    """
    Playwright-based LinkedIn Easy Apply automation agent.
    """

    # Human-like timing constants
    MIN_KEYSTROKE_DELAY = 50   # ms
    MAX_KEYSTROKE_DELAY = 150  # ms
    MIN_ACTION_DELAY = 1.0    # seconds
    MAX_ACTION_DELAY = 3.0    # seconds
    PAGE_LOAD_WAIT = 2.0      # seconds
    BETWEEN_JOBS_DELAY = 5.0  # seconds min
    BETWEEN_JOBS_MAX = 10.0   # seconds max

    def __init__(
        self,
        credentials: Dict[str, str],
        resume_data: Dict[str, Any],
        profile: Dict[str, Any],
        ask_user_callback: Optional[Callable[[str, str, str], Coroutine]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        db: Optional[Any] = None,
    ):
        """
        Args:
            credentials: {"email": ..., "password": ...}
            resume_data: Extracted resume fields from ResumeExtractor
            profile: User profile dict from DB
            ask_user_callback: async fn(job_title, field_name, question) -> answer
                Called when the agent encounters a form field it can't fill from resume.
                The caller should present this question in chat and wait for user response.
            progress_callback: fn(event_dict) for real-time progress updates
            db: AppDatabase instance for status persistence
        """
        self.credentials = credentials
        self.resume_data = resume_data
        self.profile = profile
        self.ask_user = ask_user_callback
        self.progress = progress_callback
        self.db = db
        self.browser = None
        self.context = None
        self.page = None
        self._stop_requested = False
        self._user_answers_cache: Dict[str, str] = {}

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

    async def _type_human(self, selector: str, text: str):
        """Type text with human-like keystroke delays."""
        element = self.page.locator(selector).first
        await element.click()
        await asyncio.sleep(0.2)
        # Clear existing text
        await element.fill("")
        await asyncio.sleep(0.1)
        for char in text:
            await element.type(char, delay=random.randint(self.MIN_KEYSTROKE_DELAY, self.MAX_KEYSTROKE_DELAY))

    async def _safe_click(self, selector: str, timeout: int = 5000):
        """Click an element safely with retry."""
        try:
            await self.page.locator(selector).first.click(timeout=timeout)
            return True
        except Exception as e:
            logger.debug(f"Click failed for {selector}: {e}")
            return False

    async def _take_screenshot(self, name: str = "debug") -> Optional[bytes]:
        """Take a screenshot for debugging."""
        try:
            return await self.page.screenshot(full_page=False)
        except Exception:
            return None

    def _resolve_profile_resume_path(self) -> Optional[str]:
        """
        Resolves the candidate's resume strictly from the Profile section.
        Never scans arbitrary directories or the uploads folder.
        """
        # 1. Check exact file path recorded in profile
        resume_file = self.profile.get("resume_file_path") or ""
        if resume_file and os.path.exists(resume_file):
            return os.path.abspath(resume_file)

        # 2. If path is not on disk but resume_text exists in profile, generate an official DOCX
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
                if self.profile.get("linkedin_url"):
                    contact_parts.append(self.profile["linkedin_url"])
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
        """Launch Playwright browser with stealth settings."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
            ]
        )
        import os
        cookies_path = "web/backend/data/linkedin_cookies.json"
        storage_state = cookies_path if os.path.exists(cookies_path) else None

        self.context = await self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Kolkata",
            storage_state=storage_state,
        )

        # Anti-detection: override navigator.webdriver
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        self.page = await self.context.new_page()
        logger.info("Browser initialized with stealth settings")

    async def close_browser(self):
        """Clean up browser resources."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, '_playwright') and self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    async def login(self) -> bool:
        """
        Log into LinkedIn with stored credentials.
        Returns True on success, False on failure.
        Handles 2FA by asking user via callback.
        """
        self._emit({"type": "apply_login", "message": "Verifying LinkedIn session..."})

        try:
            # 1. Quick check if already authenticated via session cookies
            try:
                await self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1.5)
                curr_url = self.page.url.lower()
                is_logged_in = (
                    ("linkedin.com/feed" in curr_url or "linkedin.com/mynetwork" in curr_url)
                    and "login" not in curr_url
                    and "checkpoint" not in curr_url
                )
                feed_nav = self.page.locator('.global-nav, #global-nav, a[href*="/feed"]')
                if is_logged_in and await feed_nav.count() > 0:
                    self._emit({"type": "apply_login", "message": "Already logged into LinkedIn ✓", "success": True})
                    return True
            except Exception:
                pass

            # 2. Navigate to login page
            self._emit({"type": "apply_login", "message": "Logging into LinkedIn..."})
            await self.page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=20000)
            await self._human_delay(0.8, 1.5)

            # Check again if redirected to feed
            curr_url = self.page.url.lower()
            feed_nav = self.page.locator('.global-nav, #global-nav, a[href*="/feed"]')
            if ("linkedin.com/feed" in curr_url and "login" not in curr_url) or (await feed_nav.count() > 0 and "login" not in curr_url):
                self._emit({"type": "apply_login", "message": "Already logged into LinkedIn ✓", "success": True})
                return True

            # 3. Fill VISIBLE email input (handles LinkedIn dynamic random IDs)
            email_input = self.page.locator(
                "input[type='email']:visible, #username:visible, #session_key:visible, input[name='session_key']:visible"
            ).first
            if await email_input.count() > 0:
                await email_input.fill("")
                await asyncio.sleep(0.1)
                await email_input.fill(self.credentials["email"])
                await self._human_delay(0.3, 0.6)
            else:
                first_input = self.page.locator("input:visible").first
                if await first_input.count() > 0:
                    await first_input.fill(self.credentials["email"])

            # 4. Fill VISIBLE password input
            pwd_input = self.page.locator(
                "input[type='password']:visible, #password:visible, #session_password:visible, input[name='session_password']:visible"
            ).first
            if await pwd_input.count() > 0:
                await pwd_input.fill("")
                await asyncio.sleep(0.1)
                await pwd_input.fill(self.credentials["password"])
                await self._human_delay(0.3, 0.6)

            # 5. Click EXACT "Sign in" button (prevents clicking "Sign in with Apple")
            exact_btn = self.page.get_by_role("button", name="Sign in", exact=True)
            if await exact_btn.count() > 0 and await exact_btn.first.is_visible():
                await exact_btn.first.click()
            else:
                fallback_btn = self.page.locator("button:has-text('Sign in'):not(:has-text('Apple')):not(:has-text('Google')):visible").first
                if await fallback_btn.count() > 0:
                    await fallback_btn.click()
                elif await pwd_input.count() > 0:
                    await pwd_input.press("Enter")

            await self._human_delay(4.0, 6.0)

            # 6. Check for security challenges
            current_url = self.page.url
            page_content = await self.page.content()

            # 2FA / Verification challenge
            if "checkpoint" in current_url or "challenge" in current_url:
                self._emit({
                    "type": "apply_2fa",
                    "message": "LinkedIn is requesting verification. Please check your email/phone for a verification code.",
                    "needs_input": True,
                    "field": "verification_code",
                })

                if self.ask_user:
                    code = await self.ask_user(
                        "LinkedIn Login",
                        "verification_code",
                        "LinkedIn sent a verification code to your email/phone. Please enter the code:"
                    )
                    if code:
                        code_input = self.page.locator('input[name="pin"]:visible, input#input__email_verification_pin:visible, input[type="text"]:visible').first
                        if await code_input.count() > 0:
                            await code_input.fill(code.strip())
                            await self._human_delay(0.5, 1.0)
                            sub_btn = self.page.get_by_role("button", name="Submit", exact=False)
                            if await sub_btn.count() > 0:
                                await sub_btn.first.click()
                            else:
                                await self.page.locator('button[type="submit"]:visible, button:has-text("Submit"):visible').first.click()
                            await self._human_delay(3.0, 5.0)

            # CAPTCHA detection
            if "captcha" in page_content.lower() or "security verification" in page_content.lower():
                self._emit({
                    "type": "apply_error",
                    "message": "LinkedIn CAPTCHA detected. Cannot proceed with automated login. Please try again later.",
                    "error": "captcha",
                })
                return False

            # 7. Verify login success
            await self._human_delay(1.5, 2.5)
            curr_url = self.page.url.lower()
            feed_nav = self.page.locator('.global-nav, #global-nav, a[href*="/feed"]')
            is_logged_in = (
                ("feed" in curr_url or "mynetwork" in curr_url or "jobs" in curr_url)
                and "login" not in curr_url
                and "checkpoint" not in curr_url
            ) or (await feed_nav.count() > 0 and "login" not in curr_url)

            if is_logged_in:
                self._emit({"type": "apply_login", "message": "Successfully logged into LinkedIn ✓", "success": True})
                # Save session cookies for fast reuse
                try:
                    import os
                    os.makedirs("web/backend/data", exist_ok=True)
                    await self.context.storage_state(path="web/backend/data/linkedin_cookies.json")
                except Exception:
                    pass
                return True

            # Check for wrong password
            error_elem = self.page.locator("#error-for-password:visible, .form__label--error:visible, [role='alert']:visible")
            if await error_elem.count() > 0:
                self._emit({
                    "type": "apply_error",
                    "message": "LinkedIn login failed: Incorrect email or password.",
                    "error": "auth_failed",
                })
                return False

            self._emit({
                "type": "apply_error",
                "message": f"LinkedIn login unclear. Current page: {self.page.url}",
                "error": "login_unknown",
            })
            return False

        except Exception as e:
            logger.error(f"LinkedIn login error: {e}")
            self._emit({"type": "apply_error", "message": f"Login error: {str(e)}", "error": "exception"})
            return False

    async def apply_to_job(self, job: Dict[str, Any]) -> ApplyResult:
        """
        Navigate to a LinkedIn job and apply via Easy Apply.
        """
        job_id = job.get("id", 0)
        company = job.get("company", "Unknown")
        title = job.get("title", "Role")
        apply_url = job.get("apply_url", "")

        result = ApplyResult(
            job_id=job_id,
            company=company,
            title=title,
            status=ApplyStatus.ERROR,
            apply_url=apply_url,
        )

        if not apply_url:
            result.status = ApplyStatus.SKIPPED
            result.message = "No apply URL available"
            self._emit({
                "type": "apply_job_done",
                "job_id": job_id,
                "company": company,
                "title": title,
                "status": "skipped",
                "message": result.message,
            })
            return result

        try:
            self._emit({
                "type": "apply_job_start",
                "job_id": job_id,
                "company": company,
                "title": title,
                "message": f"Navigating to {company} — {title}...",
            })

            # Navigate to the job page
            await self.page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay(1.5, 3.0)

            # Check if this is a LinkedIn job page
            page_url = self.page.url
            if "linkedin.com" not in page_url:
                result.status = ApplyStatus.MANUAL_REQUIRED
                result.message = "External application URL — apply manually"
                return result

            # Wait briefly for apply buttons or page content to settle
            try:
                await self.page.wait_for_selector(
                    'button.jobs-apply-button, button[aria-label*="Easy Apply"], button:has-text("Easy Apply"), button:has-text("Apply")',
                    timeout=5000
                )
            except Exception:
                pass

            # Verify that the company displayed on LinkedIn matches target company
            try:
                comp_loc = self.page.locator(
                    ".job-details-jobs-unified-top-card__company-name, "
                    ".jobs-unified-top-card__company-name, "
                    "a.topcard__org-name-link, "
                    ".top-card-layout__first-sub-headline, "
                    "span[class*='primary-description']"
                ).first
                if await comp_loc.count() > 0:
                    page_comp = (await comp_loc.text_content() or "").strip()
                    if page_comp and company and company.lower() != "unknown":
                        if not _companies_match(company, page_comp):
                            logger.warning(
                                f"LinkedIn page company '{page_comp}' does not match target '{company}'. "
                                "Aborting to prevent applying to wrong employer."
                            )
                            result.status = ApplyStatus.SKIPPED
                            result.message = f"Page company '{page_comp}' does not match target '{company}'"
                            return result
            except Exception as comp_err:
                logger.debug(f"Error checking LinkedIn page company: {comp_err}")

            # Look for Easy Apply button
            easy_apply_btn = self.page.locator(
                'button.jobs-apply-button:visible, '
                'button[aria-label*="Easy Apply"]:visible, '
                'button:has-text("Easy Apply"):visible'
            ).first

            if await easy_apply_btn.count() == 0:
                # Check if already applied
                already_applied = self.page.locator(
                    'button:has-text("Applied"):visible, '
                    'span:has-text("Applied"):visible, '
                    '*:has-text("Application submitted"):visible, '
                    '*:has-text("Application status"):visible'
                ).first
                if await already_applied.count() > 0:
                    result.status = ApplyStatus.SKIPPED
                    result.message = "Already applied to this job"
                    return result

                # Check for external apply button (must be the real apply button, not generic text)
                external_btn = self.page.locator(
                    'button.jobs-apply-button:visible, '
                    'button:has-text("Apply on company"):visible, '
                    'a.jobs-apply-button:visible, '
                    'a[aria-label*="Apply on company"]:visible, '
                    'a:has-text("Apply on company website"):visible, '
                    'a:has-text("Apply on company"):visible'
                ).first
                if await external_btn.count() > 0:
                    result.status = ApplyStatus.MANUAL_REQUIRED
                    result.message = "Not Easy Apply — requires external application"
                    return result

                result.status = ApplyStatus.SKIPPED
                result.message = "Easy Apply button not found"
                return result

            # Click Easy Apply
            self._emit({
                "type": "apply_job_progress",
                "job_id": job_id,
                "message": f"Clicking Easy Apply for {company}...",
            })
            await easy_apply_btn.click()
            await self._human_delay(1.5, 3.0)

            # Process the multi-step application form
            applied = await self._fill_application_form(job)

            if applied:
                result.status = ApplyStatus.APPLIED
                result.message = f"Applied to {company} — {title} ✓"
            else:
                result.status = ApplyStatus.ERROR
                result.message = "Could not complete the application form"

        except Exception as e:
            logger.error(f"Error applying to {company} — {title}: {e}")
            result.status = ApplyStatus.ERROR
            result.message = f"Application error: {str(e)[:100]}"
            self._emit({
                "type": "apply_job_error",
                "job_id": job_id,
                "company": company,
                "title": title,
                "message": f"❌ Error applying to {company}: {str(e)[:80]}",
            })

        finally:
            # ALWAYS emit apply_job_done so UI updates from 'in_progress' to final status immediately!
            self._emit({
                "type": "apply_job_done",
                "job_id": job_id,
                "company": company,
                "title": title,
                "status": result.status.value,
                "message": result.message,
            })

        return result

    async def _fill_application_form(self, job: Dict[str, Any]) -> bool:
        """
        Fill a LinkedIn Easy Apply multi-step form.
        Returns True if application was submitted successfully.
        """
        max_steps = 12  # Safety limit for multi-step forms
        company = job.get("company", "Unknown")
        title = job.get("title", "Role")

        for step in range(max_steps):
            await self._human_delay(1.0, 2.0)

            # Check for the modal/form using robust selectors including native <dialog>
            form_modal = None
            modal_selectors = [
                'dialog:visible',
                '[role="dialog"]:visible',
                '.jobs-easy-apply-modal:visible',
                '.jobs-easy-apply-content:visible',
                '.artdeco-modal:visible',
                'div[data-test-modal]:visible',
            ]
            for _ in range(6):
                for sel in modal_selectors:
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        form_modal = loc
                        break
                if form_modal:
                    break
                await asyncio.sleep(0.5)

            if not form_modal:
                logger.warning("Application form modal not found")
                return False

            # Check for Resume upload step
            upload_btn = form_modal.locator('button:has-text("Upload resume"), label:has-text("Upload resume")').first
            resume_alert = form_modal.locator('text="A resume is required"').first
            has_resume_card = form_modal.locator('text=".pdf", text=".doc", text=".docx"').first

            if (await upload_btn.count() > 0 and await upload_btn.is_visible()) and (await has_resume_card.count() == 0 or await resume_alert.count() > 0):
                resume_file = self._resolve_profile_resume_path()
                if resume_file and os.path.exists(resume_file):
                    try:
                        self._emit({
                            "type": "apply_job_progress",
                            "job_id": job.get("id"),
                            "message": f"Uploading profile resume ({Path(resume_file).name}) for {company}...",
                        })
                        async with self.page.expect_file_chooser(timeout=5000) as fc_info:
                            await upload_btn.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(resume_file)
                        await asyncio.sleep(2.5)
                    except Exception as fe:
                        logger.warning(f"File upload error: {fe}")
                else:
                    logger.warning(f"No valid resume found in Candidate Profile for {company}. Proceeding without file upload.")

            # Fill all visible input fields in current step
            await self._fill_visible_fields(company, title, form_modal)

            # Check for "Submit application" button (final step)
            submit_btn = form_modal.locator(
                'button[aria-label*="Submit application"]:visible, '
                'button:has-text("Submit application"):visible, '
                'button[data-control-name*="submit"]:visible'
            ).first
            if await submit_btn.count() == 0:
                submit_btn = self.page.locator('button:has-text("Submit application"):visible').first

            if await submit_btn.count() > 0 and await submit_btn.is_visible():
                self._emit({
                    "type": "apply_job_progress",
                    "job_id": job.get("id"),
                    "message": f"Submitting application to {company}...",
                })
                await self._human_delay(0.5, 1.5)
                try:
                    await submit_btn.click(timeout=5000)
                except Exception:
                    await self.page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
                    await submit_btn.click(force=True, timeout=5000)
                await self._human_delay(2.0, 4.0)

                # Check for success
                try:
                    dismiss_btn = self.page.locator(
                        'button[aria-label*="Dismiss"]:visible, button:has-text("Done"):visible, button[aria-label*="Close"]:visible'
                    ).first
                    if await dismiss_btn.count() > 0:
                        await dismiss_btn.click(timeout=2000, force=True)
                except Exception:
                    pass

                return True  # Submission completed successfully

            # Look for "Next" / "Continue" / "Review" button
            next_btn = form_modal.locator(
                'button:has-text("Review"):visible, '
                'button:has-text("Next"):visible, '
                'button:has-text("Continue"):visible, '
                'button[aria-label*="Review"]:visible, '
                'button[aria-label*="Next"]:visible, '
                'button[aria-label*="Continue"]:visible'
            ).first
            if await next_btn.count() == 0:
                next_btn = self.page.locator(
                    'button:has-text("Review"):visible, '
                    'button:has-text("Next"):visible, '
                    'button:has-text("Continue"):visible'
                ).first

            if await next_btn.count() > 0 and await next_btn.is_visible():
                await self._human_delay(0.5, 1.0)
                try:
                    await next_btn.click(timeout=5000)
                except Exception:
                    # Dismiss any floating autocomplete portal / overlay that intercepts pointer events
                    await self.page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
                    await next_btn.click(force=True, timeout=5000)
                await self._human_delay(1.5, 2.5)
            else:
                error_msg = self.page.locator('.artdeco-inline-feedback--error:visible, [role="alert"]:visible').first
                if await error_msg.count() > 0:
                    error_text = await error_msg.text_content()
                    logger.warning(f"Form validation error: {error_text}")
                    return False
                break

        return False

    async def _fill_visible_fields(self, company: str, title: str, form_modal: Optional[Any] = None):
        """
        Scan the current form step for input fields and fill them from resume data.
        """
        from web.backend.resume_extractor import ResumeExtractor

        scope = form_modal if form_modal is not None else self.page

        # Text inputs
        text_inputs = scope.locator(
            'input:visible:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]):not([type="file"])'
        )
        count = await text_inputs.count()

        for i in range(count):
            inp = text_inputs.nth(i)
            try:
                # Get the label
                inp_id = await inp.get_attribute("id") or ""
                label_text = ""

                if inp_id:
                    label = scope.locator(f'label[for="{inp_id}"]').first
                    if await label.count() == 0:
                        label = self.page.locator(f'label[for="{inp_id}"]').first
                    if await label.count() > 0:
                        label_text = (await label.text_content() or "").strip()

                if not label_text:
                    aria_label = await inp.get_attribute("aria-label") or ""
                    placeholder = await inp.get_attribute("placeholder") or ""
                    label_text = aria_label or placeholder

                if not label_text:
                    try:
                        label_text = await inp.evaluate("el => el.closest('div').innerText.split('\\n')[0]")
                    except Exception:
                        pass

                if not label_text:
                    continue

                # Check if already filled
                current_value = await inp.input_value()
                if current_value and current_value.strip():
                    continue

                label_clean = re.sub(r"[\*:\(\)\?]+", "", label_text).lower().strip()
                value = None

                # 1. Phone number matching
                if "phone" in label_clean or "mobile" in label_clean:
                    value = self.resume_data.get("phone") or self.profile.get("phone")

                # 2. Work experience years matching
                elif any(kw in label_clean for kw in [
                    "experience", "how many years", "years of", "how long", "actively working", "years working", "duration"
                ]):
                    is_specific_domain = any(w in label_clean for w in ["product based", "service based", "startup", "domain"])
                    if not is_specific_domain:
                        value = ResumeExtractor.get_field_value(label_text, self.resume_data)
                        if not value:
                            exp_yr = self.resume_data.get("experience_years") or self.profile.get("years_of_experience")
                            if exp_yr and str(exp_yr).strip() not in ("", "0"):
                                value = str(exp_yr)

                # 3. Notice period matching (handles numeric days vs text)
                elif "notice" in label_clean or "period" in label_clean:
                    val = self.profile.get("notice_period")
                    if val:
                        if any(kw in label_clean for kw in ["day", "days", "no of days", "number of days"]):
                            val_str = str(val).lower()
                            if "immediate" in val_str or "0" in val_str:
                                value = "0"
                            elif "15" in val_str:
                                value = "15"
                            elif "30" in val_str or "1 month" in val_str:
                                value = "30"
                            elif "60" in val_str or "2 month" in val_str:
                                value = "60"
                            elif "90" in val_str or "3 month" in val_str:
                                value = "90"
                            else:
                                digits = "".join(filter(str.isdigit, str(val)))
                                value = digits if digits else str(val)
                        else:
                            value = str(val)

                # 3b. Expected CTC / Salary / Compensation matching from profile
                elif any(kw in label_clean for kw in ["salary", "ctc", "compensation", "expected ctc", "current ctc"]):
                    val = self.profile.get("expected_ctc_lpa")
                    if val:
                        value = str(val)

                # 4. General resume data extraction
                if not value:
                    value = ResumeExtractor.get_field_value(label_text, self.resume_data)

                # 5. User answer cache
                if not value:
                    value = self._user_answers_cache.get(label_clean)

                # 6. Ask user if no value found
                if not value and self.ask_user:
                    value = await self.ask_user(
                        f"{company} — {title}",
                        label_text,
                        f"The application for {company} requires: **{label_text}**\nPlease provide your answer:"
                    )
                    if value:
                        self._user_answers_cache[label_clean] = value

                if value:
                    fill_value = str(value).strip()

                    # Detect if this is a numeric / integer field
                    inp_type = await inp.get_attribute("type") or ""
                    input_mode = await inp.get_attribute("inputmode") or ""
                    is_numeric_field = (
                        inp_type == "number"
                        or input_mode == "numeric"
                        or any(kw in label_clean for kw in ["how many", "how long", "years", "duration", "number of", "no of", "experience"])
                    )

                    # If numeric field and user provided words like "3 years" or "2 yrs", extract digits
                    if is_numeric_field and not fill_value.isdigit():
                        num_match = re.search(r'\d+', fill_value)
                        if num_match:
                            fill_value = num_match.group(0)

                    await inp.fill("")
                    await asyncio.sleep(0.1)
                    for char in fill_value:
                        await inp.type(char, delay=random.randint(20, 50))
                    await self._human_delay(0.2, 0.5)

                    # Dispatch native DOM input & change events for React / LinkedIn validation
                    try:
                        await inp.evaluate("""el => {
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }""")
                    except Exception:
                        pass

                    # If this input triggered a floating autocomplete portal (e.g. City / Location)
                    try:
                        portal_opt = self.page.locator(
                            'div[data-floating-ui-portal] [role="option"]:visible, '
                            'div[data-floating-ui-portal] li:visible, '
                            'ul[role="listbox"] li:visible, '
                            '.artdeco-typeahead__results-container li:visible'
                        ).first
                        if await portal_opt.count() > 0 and await portal_opt.is_visible():
                            await portal_opt.click(timeout=1500)
                            await asyncio.sleep(0.3)
                    except Exception:
                        pass

                    # Blur the input element so floating focus popups close and onBlur validators fire
                    try:
                        await inp.evaluate("el => el.blur()")
                    except Exception:
                        pass

            except Exception as e:
                logger.debug(f"Error filling field: {e}")
                continue

        # Handle textareas (cover letter, additional info)
        textareas = scope.locator('textarea:visible')
        ta_count = await textareas.count()
        for i in range(ta_count):
            ta = textareas.nth(i)
            try:
                current_value = await ta.input_value()
                if current_value and current_value.strip():
                    continue

                label_text = await ta.get_attribute("aria-label") or await ta.get_attribute("placeholder") or ""

                if not label_text:
                    ta_id = await ta.get_attribute("id") or ""
                    if ta_id:
                        label = scope.locator(f'label[for="{ta_id}"]').first
                        if await label.count() == 0:
                            label = self.page.locator(f'label[for="{ta_id}"]').first
                        if await label.count() > 0:
                            label_text = (await label.text_content() or "").strip()

                if label_text:
                    label_clean = re.sub(r"[\*:\(\)\?]+", "", label_text).lower().strip()
                    value = ResumeExtractor.get_field_value(label_text, self.resume_data)
                    if not value:
                        value = self._user_answers_cache.get(label_clean)
                    if not value and self.ask_user:
                        value = await self.ask_user(
                            f"{company} — {title}",
                            label_text,
                            f"The application for {company} requires: **{label_text}**\nPlease provide your answer:"
                        )
                        if value:
                            self._user_answers_cache[label_clean] = value
                    if value:
                        await ta.fill(str(value))
                        await self._human_delay(0.3, 0.7)

            except Exception as e:
                logger.debug(f"Error filling textarea: {e}")

        # Handle select/dropdowns
        selects = scope.locator('select:visible')
        sel_count = await selects.count()
        for i in range(sel_count):
            sel = selects.nth(i)
            try:
                label_text = ""
                sel_id = await sel.get_attribute("id") or ""
                if sel_id:
                    label = scope.locator(f'label[for="{sel_id}"]').first
                    if await label.count() == 0:
                        label = self.page.locator(f'label[for="{sel_id}"]').first
                    if await label.count() > 0:
                        label_text = (await label.text_content() or "").strip()

                if not label_text:
                    label_text = await sel.get_attribute("aria-label") or ""

                if not label_text:
                    continue

                # Get options
                options = sel.locator("option")
                opt_count = await options.count()
                if opt_count <= 1:
                    continue

                # Try to match a value
                value = ResumeExtractor.get_field_value(label_text, self.resume_data)
                if value:
                    for j in range(opt_count):
                        opt_text = (await options.nth(j).text_content() or "").strip().lower()
                        if value.lower() in opt_text or opt_text in value.lower():
                            opt_value = await options.nth(j).get_attribute("value")
                            if opt_value:
                                await sel.select_option(value=opt_value)
                                await self._human_delay(0.3, 0.5)
                                break
                    else:
                        if opt_count > 1:
                            opt_value = await options.nth(1).get_attribute("value")
                            if opt_value:
                                await sel.select_option(value=opt_value)

            except Exception as e:
                logger.debug(f"Error handling select: {e}")

        # Handle radio buttons (Yes/No questions)
        fieldsets = scope.locator('fieldset:visible, [role="radiogroup"]:visible')
        fs_count = await fieldsets.count()
        for i in range(fs_count):
            fs = fieldsets.nth(i)
            try:
                # 1. Get question text from legend, span, or div[role="radio"][aria-label]
                question_text = ""
                legend = fs.locator("legend, span.t-14, p.t-14").first
                if await legend.count() > 0:
                    question_text = (await legend.text_content() or "").strip()
                if not question_text:
                    role_radio = fs.locator('div[role="radio"][aria-label]').first
                    if await role_radio.count() > 0:
                        question_text = (await role_radio.get_attribute("aria-label") or "").strip()
                if not question_text:
                    aria_label = await fs.get_attribute("aria-label") or ""
                    question_text = aria_label.strip()

                if not question_text:
                    continue

                # 2. Check if already answered
                checked = fs.locator('input[type="radio"]:checked, div[role="radio"][aria-checked="true"]')
                if await checked.count() > 0:
                    continue

                # 3. Try to answer Yes/No questions or ask user
                cache_key = f"radio:{question_text}"
                target_choice = None

                if cache_key in self._user_answers_cache:
                    target_choice = self._user_answers_cache[cache_key]
                else:
                    guessed = self._guess_radio_answer(question_text)
                    if guessed is not None:
                        target_choice = "Yes" if guessed else "No"
                    elif self.ask_user:
                        self._emit({
                            "type": "apply_step",
                            "step": "needs_input",
                            "message": f"Agent needs your input for: {question_text}",
                        })
                        radio_options = fs.locator('div[role="radio"], label')
                        r_count = await radio_options.count()
                        option_labels = []
                        for j in range(r_count):
                            txt = (await radio_options.nth(j).text_content() or "").strip()
                            if txt and txt not in option_labels:
                                option_labels.append(txt)

                        answer_str = await self.ask_user(
                            f"{company} — {title}",
                            question_text,
                            f"The application asks: **{question_text}**\nOptions: {', '.join(option_labels) if option_labels else 'Yes / No'}\nPlease respond:"
                        )
                        if answer_str:
                            target_choice = answer_str.strip()
                            self._user_answers_cache[cache_key] = target_choice

                if target_choice:
                    target_choice_lower = target_choice.lower()
                    is_yes = target_choice_lower in ("yes", "true", "1", "y")
                    is_no = target_choice_lower in ("no", "false", "0", "n")
                    target_label = "yes" if is_yes else ("no" if is_no else target_choice_lower)

                    # Try clicking modern LinkedIn div[role="radio"] first
                    target_div = fs.locator(
                        f'div[role="radio"]:has-text("{target_label.capitalize()}"), '
                        f'div[role="radio"]:has(p:has-text("{target_label.capitalize()}")), '
                        f'div[role="radio"]:has-text("{target_choice}"), '
                        f'div[role="radio"][aria-label*="{target_label}"]'
                    ).first
                    if await target_div.count() > 0:
                        await target_div.click(force=True)
                        await self._human_delay(0.3, 0.5)
                    else:
                        # Fallback to radio input or label
                        radio_options = fs.locator('input[type="radio"]')
                        r_count = await radio_options.count()
                        for j in range(r_count):
                            r_id = await radio_options.nth(j).get_attribute("id") or ""
                            r_label = fs.locator(f'label[for="{r_id}"]').first
                            if await r_label.count() > 0:
                                lbl_text = (await r_label.text_content() or "").strip().lower()
                                if target_label in lbl_text or target_choice_lower in lbl_text:
                                    await r_label.click(force=True)
                                    await self._human_delay(0.3, 0.5)
                                    break
                            else:
                                await radio_options.nth(j).click(force=True)
                                await self._human_delay(0.3, 0.5)
                                break

            except Exception as e:
                logger.debug(f"Error handling fieldset: {e}")

    def _guess_radio_answer(self, question: str) -> Optional[bool]:
        """
        Attempt to answer common Yes/No application questions automatically.
        Returns True (Yes), False (No), or None (ask user).
        Do NOT make default rules for experience, previous employment, or domain-specific questions!
        """
        q = question.lower().strip()

        # Questions about experience, background, previous application, etc. must NOT have default rules -> Ask user in chat!
        if any(kw in q for kw in [
            "experience", "knowledge", "product based", "service based",
            "previously applied", "applied before", "previously employed", "formerly employed",
            "worked at", "former employee", "currently employed", "currently working"
        ]):
            return None

        # "Are you authorized to work" → Yes
        if any(kw in q for kw in ["authorized to work", "legally authorized", "work authorization", "eligible to work"]):
            return True

        # "Will you now or in the future require sponsorship" → depends, ask user
        if "sponsorship" in q or "visa" in q:
            return None

        # "Are you willing to relocate" → Yes (generally safe default)
        if "willing to relocate" in q or "open to relocation" in q:
            return True

        return None

    async def run_batch(self, jobs: List[Dict[str, Any]], max_applies: int = 25) -> BatchResult:
        """
        Apply to a batch of LinkedIn jobs.
        """
        session_id = f"apply_{uuid.uuid4().hex[:8]}"
        batch = BatchResult(session_id=session_id, total=min(len(jobs), max_applies))

        self._emit({
            "type": "apply_batch_start",
            "session_id": session_id,
            "total": batch.total,
            "message": f"🤖 Starting LinkedIn auto-apply — {batch.total} jobs queued",
        })

        for idx, job in enumerate(jobs[:max_applies]):
            if self._stop_requested:
                self._emit({
                    "type": "apply_batch_stopped",
                    "message": "Auto-apply session stopped by user.",
                })
                break

            self._emit({
                "type": "apply_job_progress",
                "job_id": job.get("id"),
                "company": job.get("company"),
                "title": job.get("title"),
                "index": idx + 1,
                "total": batch.total,
                "message": f"[{idx + 1}/{batch.total}] Applying to {job.get('company')} — {job.get('title')}...",
            })

            result = await self.apply_to_job(job)
            batch.results.append(result)

            # Update counters
            if result.status == ApplyStatus.APPLIED:
                batch.applied += 1
                # Update DB status
                if self.db:
                    try:
                        self.db.update_opportunity_apply_status(result.job_id, "applied")
                        self.db.add_tracker_entry(
                            job_id=str(result.job_id),
                            company=result.company,
                            title=result.title,
                            location=job.get("location", ""),
                            apply_url=result.apply_url,
                            status="applied",
                            source="linkedin",
                            notes="Auto-applied via LinkedIn Easy Apply agent",
                        )
                    except Exception as e:
                        logger.error(f"DB update error: {e}")

            elif result.status == ApplyStatus.SKIPPED:
                batch.skipped += 1
                if self.db:
                    try:
                        self.db.update_opportunity_apply_status(result.job_id, "skipped")
                    except Exception:
                        pass

            elif result.status == ApplyStatus.MANUAL_REQUIRED:
                batch.skipped += 1
                if self.db:
                    try:
                        self.db.update_opportunity_apply_status(result.job_id, "manual_required")
                    except Exception:
                        pass

            else:
                batch.errors += 1
                if self.db:
                    try:
                        self.db.update_opportunity_apply_status(result.job_id, "error")
                    except Exception:
                        pass

            # Update apply session in DB
            if self.db:
                try:
                    self.db.update_apply_session(
                        session_id,
                        applied_count=batch.applied,
                        skipped_count=batch.skipped,
                        error_count=batch.errors,
                        results_json=json.dumps([
                            {"job_id": r.job_id, "company": r.company, "title": r.title,
                             "status": r.status.value, "message": r.message}
                            for r in batch.results
                        ]),
                    )
                except Exception:
                    pass

            # Human-like delay between jobs
            if idx < len(jobs[:max_applies]) - 1:
                wait = random.uniform(self.BETWEEN_JOBS_DELAY, self.BETWEEN_JOBS_MAX)
                self._emit({
                    "type": "apply_waiting",
                    "message": f"Waiting {wait:.0f}s before next application (human-like pacing)...",
                })
                await asyncio.sleep(wait)

        self._emit({
            "type": "apply_batch_complete",
            "session_id": session_id,
            "applied": batch.applied,
            "skipped": batch.skipped,
            "errors": batch.errors,
            "total": batch.total,
            "message": (
                f"✅ Auto-apply session complete!\n"
                f"Applied: {batch.applied} | Skipped: {batch.skipped} | Errors: {batch.errors} | Total: {batch.total}"
            ),
        })

        return batch
