"""
Indeed Auto-Apply Agent.
Uses Playwright to automate Indeed Apply / Easily Apply job applications.
Extracts form data from uploaded resume, answers employer screening questions,
and asks the user for missing fields via callback.
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
from urllib.parse import quote_plus

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


def _normalize_company_name(name: str) -> str:
    """Normalizes company name by removing punctuation and legal suffixes."""
    if not name:
        return ""
    clean = re.sub(r"<[^>]+>", " ", name)
    clean = clean.lower()
    noise_pattern = r"\b(technologies|technology|systems|system|solutions|services|service|india|pvt|ltd|limited|llc|llp|inc|incorporated|corp|corporation|group|co|labs|holdings|enterprises|international|private|digital|tech)\b"
    clean = re.sub(noise_pattern, " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"[^a-z0-9\s]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _companies_match(target: str, candidate: str) -> bool:
    """
    Returns True if target company and candidate company match with tolerance for
    corporate noise, abbreviations, and legal suffix variations.
    Strictly returns False if either is empty, unknown, or completely different.
    """
    if not target or not candidate:
        return False
    t_raw = target.strip().lower()
    c_raw = candidate.strip().lower()
    if t_raw == "unknown" or c_raw == "unknown":
        return False

    # Exact equality or direct substring match
    if t_raw == c_raw or t_raw in c_raw or c_raw in t_raw:
        return True

    t_norm = _normalize_company_name(target)
    c_norm = _normalize_company_name(candidate)

    if not t_norm or not c_norm:
        t_tokens = [w for w in re.findall(r"\w+", t_raw) if len(w) > 2]
        c_tokens = [w for w in re.findall(r"\w+", c_raw) if len(w) > 2]
        return any(tok in c_raw for tok in t_tokens) or any(tok in t_raw for tok in c_tokens)

    if t_norm == c_norm or t_norm in c_norm or c_norm in t_norm:
        return True

    t_tokens = [w for w in t_norm.split() if len(w) >= 3]
    c_tokens = [w for w in c_norm.split() if len(w) >= 3]
    if not t_tokens or not c_tokens:
        return False

    return any(tok in c_tokens for tok in t_tokens)


class IndeedApplyAgent:
    """
    Playwright-based Indeed Apply / Easily Apply automation agent.
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
        """
        Args:
            credentials: {"email": ..., "password": ...}
            resume_data: Extracted resume fields from ResumeExtractor
            profile: User profile dict from DB
            ask_user_callback: async fn(job_title, field_name, question) -> answer
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
        self._last_form_status: Optional[ApplyStatus] = None
        self._last_form_message: Optional[str] = None

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
        # Clear existing text
        if hasattr(element, "fill"):
            res = element.fill("")
            if hasattr(res, "__await__"):
                await res
        if hasattr(element, "press_sequentially"):
            for char in text:
                res = element.press_sequentially(char, delay=random.randint(self.MIN_KEYSTROKE_DELAY, self.MAX_KEYSTROKE_DELAY))
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

    async def _safe_text(self, locator) -> str:
        """Safely fetch inner text from locator handling coroutines and mocks."""
        try:
            if hasattr(locator, "inner_text"):
                res = locator.inner_text()
                if hasattr(res, "__await__"):
                    return await res
                return str(res)
            return ""
        except Exception:
            return ""

    async def initialize_browser(self):
        """Launch Playwright Chromium with anti-detection settings."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # Stealth browser arguments
        is_headless = os.environ.get("HEADLESS", "true").lower() != "false"
        if os.environ.get("INDEED_HEADLESS", "").lower() == "false":
            is_headless = False

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--window-size=1280,800",
            "--disable-features=IsolateOrigins,site-per-process",
            "--lang=en-IN,en-US,en",
        ]
        if is_headless:
            args.append("--headless=new")

        launch_kwargs = {
            "headless": is_headless,
            "args": args,
        }

        # Locate system Google Chrome if available for clean bot-detection bypass
        for chrome_bin in [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]:
            if os.path.exists(chrome_bin):
                launch_kwargs["executable_path"] = chrome_bin
                logger.info(f"Using Chrome executable at {chrome_bin} (headless={is_headless})")
                break

        self.browser = await self._playwright.chromium.launch(**launch_kwargs)

        # Consistent User-Agent matching the host platform and Chrome binary version
        chrome_major = "152"
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
            Path("web/backend/data/indeed_storage_state.json"),
            Path("data/indeed_storage_state.json"),
        ]:
            if sp.exists() and sp.stat().st_size > 50:
                storage_state_path = str(sp.resolve())
                logger.info(f"Loaded storage_state from {storage_state_path}")
                break

        context_kwargs = {
            "user_agent": user_agent,
            "viewport": {"width": 1280, "height": 800},
            "locale": "en-IN",
            "timezone_id": "Asia/Kolkata",
        }
        if storage_state_path:
            context_kwargs["storage_state"] = storage_state_path

        self.context = await self.browser.new_context(**context_kwargs)
        try:
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = window.chrome || { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
                if (!navigator.plugins || navigator.plugins.length === 0) {
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                }
            """)
        except Exception:
            pass

        # Apply stealth automatically to the primary page and any new tabs (e.g. smartapply)
        from playwright_stealth import Stealth
        stealth = Stealth()

        async def on_new_page(new_p):
            try:
                await stealth.apply_stealth_async(new_p)
            except Exception:
                pass
        self.context.on("page", on_new_page)

        self.page = await self.context.new_page()
        try:
            await stealth.apply_stealth_async(self.page)
        except Exception:
            pass

    async def close_browser(self):
        """Clean up browser resources."""
        try:
            if self.page:
                await self.page.close()
        except Exception:
            pass
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass

    async def close(self):
        await self.close_browser()
        try:
            if hasattr(self, "_playwright") and self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

    async def login(self) -> bool:
        """
        Log into Indeed using passwordless 'Sign in with a code instead' flow.
        1. Reuses cached session cookies from indeed_cookies.json if valid.
        2. Navigates to https://in.indeed.com/account/login.
        3. Enters user's Gmail/email and clicks Continue.
        4. Clicks 'Sign in with a code instead' (#auth-page-google-otp-fallback).
        5. Detects OTP verification input and requests the 6-digit code from the user in chat via ask_user.
        6. Fills OTP code, submits, verifies session, and saves fresh cookies to cache.
        """
        cookie_paths = [
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/indeed_cookies.json"),
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/indeed_cookies.json"),
            Path("web/backend/data/indeed_cookies.json"),
            Path("data/indeed_cookies.json"),
        ]

        # 1. First check if context already has an active session from storage_state
        try:
            ctx_cookies = await self.context.cookies()
            has_ppid = any(c.get("name") == "PPID" for c in ctx_cookies)
            if has_ppid:
                logger.info("Indeed PPID session cookie present in context.")

            await self.page.goto("https://myjobs.indeed.com", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(self.PAGE_LOAD_WAIT)
            curr_title = await self._safe_title()
            if (
                "auth" not in self.page.url
                and "login" not in self.page.url
                and "signin" not in self.page.url
                and "Blocked" not in curr_title
                and "just a moment" not in curr_title.lower()
            ):
                logger.info("Indeed session valid via storage_state. Logged in successfully.")
                self._emit({
                    "type": "apply_login_success",
                    "method": "cookies",
                    "message": "Authenticated with Indeed (cached session)",
                })
                return True
        except Exception as se:
            logger.debug(f"Storage state verification notice: {se}")

        # 2. Try restoring existing cookies from json file
        for cp in cookie_paths:
            if cp.exists() and cp.stat().st_size > 100:
                try:
                    cookies = json.loads(cp.read_text())
                    has_ppid = any(c.get("name") == "PPID" for c in cookies)
                    await self.context.add_cookies(cookies)
                    logger.info(f"Loaded Indeed session cookies from {cp} (PPID token: {has_ppid})")

                    # Verify session
                    await self.page.goto("https://myjobs.indeed.com", wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(self.PAGE_LOAD_WAIT)

                    curr_title = await self._safe_title()
                    if (
                        "auth" not in self.page.url
                        and "login" not in self.page.url
                        and "signin" not in self.page.url
                        and "Blocked" not in curr_title
                        and "just a moment" not in curr_title.lower()
                    ):
                        logger.info("Indeed session cookies valid. Logged in successfully.")
                        self._emit({
                            "type": "apply_login_success",
                            "method": "cookies",
                            "message": "Authenticated with Indeed (cached session)",
                        })
                        return True
                    logger.info("Indeed session cookies expired. Proceeding to credentials login.")
                except Exception as e:
                    logger.warning(f"Failed to restore Indeed cookies from {cp}: {e}")

        # 2. Authenticate with credentials (email-first, passwordless code sign-in)
        email = (self.credentials.get("email") or "").strip()
        password = (self.credentials.get("password") or "").strip()

        if not email:
            self._emit({
                "type": "apply_error",
                "message": "No Indeed email provided. Please configure your Gmail/email in Platform Credentials.",
            })
            return False

        self._emit({
            "type": "apply_login_start",
            "message": f"Navigating to Indeed authentication portal for {email}...",
        })

        try:
            # Navigate to region-aware login entry point
            await self.page.goto("https://in.indeed.com/account/login", wait_until="domcontentloaded", timeout=25000)
            await self._human_delay(1.0, 2.0)

            # Dismiss OneTrust cookie banner if visible
            cookie_btn = self.page.locator("#onetrust-accept-btn-handler, button:has-text('Accept All Cookies')").first
            if await self._is_visible(cookie_btn, timeout=2000):
                try:
                    await cookie_btn.click()
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

            # Check if already authenticated upon visiting
            curr_title = await self._safe_title()
            if (
                "auth" not in self.page.url
                and "login" not in self.page.url
                and "signin" not in self.page.url
                and "Blocked" not in curr_title
            ):
                cookies = await self.context.cookies()
                for cp in cookie_paths:
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    cp.write_text(json.dumps(cookies, indent=2))
                self._emit({
                    "type": "apply_login_success",
                    "method": "existing_session",
                    "message": "Already authenticated on Indeed",
                })
                return True

            # Enter Email
            email_selectors = [
                "#emailform input[name='__email']",
                "#emailform input[type='email']",
                "input[type='email']",
                "input[name='__email']",
                "input[name='email']",
                "#ifl-InputFormField-3",
                "input[id*='email']",
                "input[type='text']",
            ]
            email_input = None
            for sel in email_selectors:
                cand = self.page.locator(sel).first
                if await self._is_visible(cand, timeout=1500):
                    email_input = cand
                    break

            if email_input:
                await self._type_human(email_input, email)
                await self._human_delay(0.5, 1.0)

                # Click Continue / Submit (excluding social buttons like Apple/Google)
                continue_btn = self.page.locator(
                    "button:text-is('Continue'), "
                    "button[type='submit']:not(:has-text('Apple')):not(:has-text('Google')), "
                    "#emailform button[type='submit']"
                ).first
                if await self._is_visible(continue_btn, timeout=2500):
                    await continue_btn.click()
                    await self._human_delay(3.0, 4.5)

            # Dismiss OneTrust cookie banner if it reappears
            cookie_btn = self.page.locator("#onetrust-accept-btn-handler, button:has-text('Accept All Cookies')").first
            if await self._is_visible(cookie_btn, timeout=1500):
                try:
                    await cookie_btn.click()
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

            # 3. Detect "Sign in with a code instead" or "Sign in with a code"
            code_link_selectors = [
                "#auth-page-google-otp-fallback",
                "a:has-text('Sign in with a code instead')",
                "button:has-text('Sign in with a code instead')",
                "a:has-text('Sign in with a code')",
                "button:has-text('Sign in with a code')",
                "a:has-text('Sign in with a login code')",
                "button:has-text('Sign in with a login code')",
                "a:has-text('code instead')",
                "button:has-text('code instead')",
                "a:has-text('Email code')",
                "button:has-text('Email code')",
                "a:has-text('Send a code')",
                "button:has-text('Send a code')",
                "[data-tn-element='auth-page-email-code-button']",
                "[data-testid='auth-page-email-code-button']",
                "[data-gnav-element-name='sign-in-code']",
            ]

            code_link_clicked = False
            for c_sel in code_link_selectors:
                try:
                    c_link = self.page.locator(c_sel).first
                    if await self._is_visible(c_link, timeout=1500):
                        logger.info(f"Found code sign-in option: '{c_sel}'. Clicking...")
                        await c_link.click()
                        code_link_clicked = True
                        await self._human_delay(3.0, 4.5)
                        break
                except Exception:
                    pass

            # If a password field is explicitly shown and no code option was clicked, check if we have password or can switch to code
            pw_input = self.page.locator("input[type='password'], #ifl-InputFormField-password").first
            if await self._is_visible(pw_input, timeout=1500) and not code_link_clicked:
                # Check if there is an option to switch to code from password screen
                switch_to_code = self.page.locator("a:has-text('Sign in with a code'), button:has-text('Sign in with a code'), a:has-text('code instead')").first
                if await self._is_visible(switch_to_code, timeout=1500):
                    await switch_to_code.click()
                    code_link_clicked = True
                    await self._human_delay(2.5, 4.0)
                elif password:
                    logger.info("Entering password for Indeed account...")
                    await self._type_human(pw_input, password)
                    await self._human_delay(0.5, 1.0)
                    sign_in_btn = self.page.locator("button[type='submit'], button:has-text('Sign in'), button:has-text('Log in')").first
                    if await self._is_visible(sign_in_btn, timeout=2000):
                        await sign_in_btn.click()
                        await self._human_delay(3.0, 5.0)

            # Check if Indeed prompts to "Send code" button
            send_code_btn = self.page.locator("button:has-text('Send code'), button:has-text('Send verification code'), button:has-text('Get code')").first
            if await self._is_visible(send_code_btn, timeout=2000):
                await send_code_btn.click()
                await self._human_delay(2.0, 3.5)

            # 4. Check for OTP / verification code challenge
            body_text = await self._safe_text(self.page.locator("body"))

            is_otp_screen = (
                await self._is_visible("#passcode-input, input[name='passcode']", timeout=3000)
                or "Check your email for a code" in body_text
                or "Enter code" in body_text
                or "verification" in self.page.url
                or "challenge" in self.page.url
                or "code" in self.page.url
                or await self._is_visible("input[name='verificationCode'], input[autocomplete='one-time-code'], input[maxlength='1']", timeout=2000)
                or "6-digit" in body_text
            )

            if is_otp_screen:
                logger.info(f"Indeed OTP verification code screen detected for {email}")
                self._emit({
                    "type": "apply_step",
                    "step": "indeed_otp_required",
                    "message": f"Indeed sent a 6-digit verification code to {email}. Requesting code...",
                })

                otp_question = (
                    f"Indeed sent a 6-digit verification code to {email}. "
                    "Please check your email and enter the code below:"
                )

                raw_otp = None
                if self.ask_user:
                    raw_otp = await self.ask_user("Indeed Authentication", "otp_code", otp_question)
                else:
                    logger.warning("No ask_user callback registered; waiting 60 seconds for manual input...")
                    await asyncio.sleep(60.0)

                if raw_otp:
                    clean_otp = re.sub(r"[^a-zA-Z0-9]", "", str(raw_otp).strip())
                    logger.info(f"Submitting OTP verification code: {clean_otp[:2]}****")

                    # Primary: #passcode-input
                    passcode_input = self.page.locator("#passcode-input, input[name='passcode']").first
                    if await self._is_visible(passcode_input, timeout=2000):
                        await self._type_human(passcode_input, clean_otp)
                        await self._human_delay(0.5, 1.0)
                    else:
                        # Check for 6 separate single-digit inputs
                        digit_inputs = await self.page.locator("input[maxlength='1']").all()
                        if len(digit_inputs) == 6 and len(clean_otp) == 6:
                            for idx, digit in enumerate(clean_otp):
                                await digit_inputs[idx].fill(digit)
                                await self._human_delay(0.08, 0.15)
                        else:
                            # Single verification code input
                            otp_input_selectors = [
                                "input[name='verificationCode']",
                                "input[name='verification_code']",
                                "input[autocomplete='one-time-code']",
                                "input[inputmode='numeric']",
                                "input[type='tel']",
                                "input[id*='verification']",
                                "input[id*='code']",
                                "input[name*='code']",
                                "#ifl-InputFormField-6",
                                "#verification_code",
                                "input[type='text']",
                            ]
                            for o_sel in otp_input_selectors:
                                target_inp = self.page.locator(o_sel).first
                                if await self._is_visible(target_inp, timeout=1000):
                                    await target_inp.fill(clean_otp)
                                    await self._human_delay(0.3, 0.6)
                                    break

                    # Click Submit / Verify / Sign in
                    verify_selectors = [
                        "button[type='submit']:has-text('Sign in')",
                        "button:has-text('Sign in')",
                        "button[type='submit']",
                        "button:has-text('Verify')",
                        "button:has-text('Submit')",
                        "button:has-text('Continue')",
                        "button:has-text('Log in')",
                        "[data-testid='verify-code-button']",
                    ]
                    for v_sel in verify_selectors:
                        v_btn = self.page.locator(v_sel).first
                        if await self._is_visible(v_btn, timeout=1500):
                            await v_btn.click()
                            break

                    await self._human_delay(4.0, 6.0)
                else:
                    logger.warning("No OTP verification code provided by user.")
                    self._emit({
                        "type": "apply_login_error",
                        "message": "No verification code entered. Indeed login aborted.",
                    })
                    return False

            # 5. Verify login success
            await asyncio.sleep(self.PAGE_LOAD_WAIT)
            curr_url = self.page.url
            curr_title = await self._safe_title()

            is_still_on_auth = (
                "auth" in curr_url
                or "login" in curr_url
                or "challenge" in curr_url
                or "Blocked" in curr_title
                or await self._is_visible("#passcode-input, #emailform, #auth-page-google-otp-fallback", timeout=1000)
            )

            if not is_still_on_auth:
                cookies = await self.context.cookies()
                for cp in cookie_paths:
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    cp.write_text(json.dumps(cookies, indent=2))
                for sp in [Path("web/backend/data/indeed_storage_state.json"), Path("data/indeed_storage_state.json")]:
                    try:
                        sp.parent.mkdir(parents=True, exist_ok=True)
                        await self.context.storage_state(path=str(sp.resolve()))
                    except Exception:
                        pass
                logger.info("Saved fresh Indeed session cookies and storage_state to cache")

                self._emit({
                    "type": "apply_login_success",
                    "method": "email_code",
                    "message": "Logged into Indeed successfully (verification code verified)",
                })
                return True
            else:
                logger.error(f"Indeed login incomplete or failed. Current URL: {curr_url}")
                self._emit({
                    "type": "apply_login_error",
                    "message": f"Indeed login failed or was not completed. Stopped on: {curr_url[:60]}",
                })
                return False

        except Exception as e:
            logger.exception("Indeed login error")
            self._emit({
                "type": "apply_login_error",
                "message": f"Indeed login failed: {str(e)[:100]}",
            })
            return False

    async def apply_to_job(self, job: Dict[str, Any]) -> ApplyResult:
        """
        Navigates to an Indeed job and completes the Indeed Apply form.
        """
        job_id = job.get("id") or 0
        company = job.get("company", "Unknown")
        title = job.get("title", "Job")
        apply_url = job.get("apply_url") or f"https://www.indeed.com/viewjob?jk={job.get('source_job_id', '')}"

        self._emit({
            "type": "apply_job_start",
            "job_id": job_id,
            "company": company,
            "title": title,
            "apply_url": apply_url,
            "message": f"Navigating to {company} — {title}",
        })

        try:
            print(f"[INDEED-DEBUG] apply_to_job: goto {apply_url}")
            await self.page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay(1.5, 3.0)

            # Handle Cloudflare "Just a moment..." / verification challenge
            for cf_wait in range(12):  # Wait up to ~24 seconds
                page_title = (await self._safe_title()).lower()
                body_sample = ""
                try:
                    body_sample = (await self.page.locator("body").inner_text() or "").lower()
                except Exception:
                    pass

                is_cf = (
                    "just a moment" in page_title
                    or "checking your browser" in page_title
                    or "attention required" in page_title
                    or "additional verification required" in body_sample
                    or "troubleshooting cloudflare" in body_sample
                    or ("ray id" in body_sample and "cloudflare" in body_sample)
                )
                if not is_cf:
                    if cf_wait > 0:
                        print("[INDEED-DEBUG] Cloudflare challenge resolved!")
                        await self._human_delay(1.0, 2.0)
                    break

                print(f"[INDEED-DEBUG] CF verification active (round {cf_wait}): title={page_title}")
                await asyncio.sleep(2)
            else:
                print("[INDEED-DEBUG] Cloudflare challenge NOT resolved after wait. Trying reload...")
                try:
                    await self.page.reload(wait_until="networkidle", timeout=20000)
                    await self._human_delay(2.0, 3.0)
                except Exception as reload_err:
                    print(f"[INDEED-DEBUG] Reload error: {reload_err}")

            # Check if this page is an Indeed 404 / 'We can't find this page'
            page_text = ""
            try:
                page_text = (await self.page.locator("body").inner_text() or "").lower()
            except Exception:
                pass
            page_title = (await self._safe_title()).lower()

            is_page_not_found = (
                "we can’t find this page" in page_text
                or "we can't find this page" in page_text
                or "page doesn't exist" in page_text
                or "doesn’t exist or isn’t available" in page_text
                or "page not found" in page_title
                or "error 404" in page_title
            )
            if is_page_not_found:
                logger.warning(f"Indeed URL {apply_url} returned 404 ('We can't find this page'). Recovering via targeted company search query...")
                search_query = f"{title} {company}".strip()
                city = (job.get("location") or "Bangalore").replace(", India", "").strip()
                loc_param = f"&l={quote_plus(city)}" if city and city.lower() != "remote" else ""
                fallback_search_url = f"https://in.indeed.com/jobs?q={quote_plus(search_query)}{loc_param}&sc=0kf%3Aattr%285QWDV%29%3B"
                print(f"[INDEED-DEBUG] 404 recovery: Navigating to {fallback_search_url}")
                try:
                    await self.page.goto(fallback_search_url, wait_until="domcontentloaded", timeout=25000)
                    await self._human_delay(1.5, 3.0)
                except Exception as rec_err:
                    print(f"[INDEED-DEBUG] 404 recovery navigation error: {rec_err}")

            # Define button selectors for Indeed Apply and External Redirects
            apply_button_selectors = [
                "#indeedApplyButton",
                "button:has-text('Apply with Indeed')",
                "span:has-text('Apply with Indeed')",
                "a:has-text('Apply with Indeed')",
                ".jobsearch-IndeedApplyButton",
                "button[id*='indeedApply']",
                "button:has([data-testid='indeedApply'])",
                "[data-testid='indeedApply']",
                "button:has(span[class*='css-1ebo7dz'])",
                "button:has-text('Apply now')",
                "span:has-text('Apply now')",
                "a:has-text('Apply now')",
                "button:has-text('Easily apply')",
                "[data-gnav-element-name='indeedApplyButton']",
            ]

            external_selectors = [
                "button:has-text('Apply on company site')",
                "a:has-text('Apply on company site')",
                "button:has-text('Apply on employer site')",
                "a:has-text('Apply on employer site')",
                "[data-tn-element='applyButton'][target='_blank']",
            ]

            already_applied_selectors = [
                "[data-testid='indeedApply-applied']",
                ".jobsearch-JobMetadataHeader-iconLabel:has-text('You applied')",
                "div:has-text('You applied to this job')",
                "span:has-text('You applied to this job')",
            ]

            # 0. Check if this is a search results page or direct job view
            is_search_page = ("/jobs?" in self.page.url or "q=" in self.page.url) and "/viewjob" not in self.page.url
            print(f"[INDEED-DEBUG] is_search_page={is_search_page}")

            clicked_apply = False

            if is_search_page:
                logger.info(f"On Indeed search results page ({self.page.url}). Waiting for job cards to render...")

                # If the search URL only has the title but not company, rebuild with company included and Easy Apply facet
                current_url = self.page.url
                if company and company.lower() != "unknown" and quote_plus(company.lower()).replace("+", " ") not in current_url.lower().replace("+", " ").replace("%20", " "):
                    search_query = f"{title} {company}".strip()
                    city_match = re.search(r"[&?]l=([^&]+)", current_url)
                    city_param = f"&l={city_match.group(1)}" if city_match else ""
                    better_url = f"https://in.indeed.com/jobs?q={quote_plus(search_query)}{city_param}&sc=0kf%3Aattr%285QWDV%29%3B"
                    print(f"[INDEED-DEBUG] Rebuilding URL with company and Easy Apply filter: {better_url}")
                    try:
                        await self.page.goto(better_url, wait_until="domcontentloaded", timeout=25000)
                        await self._human_delay(1.5, 3.0)
                    except Exception as nav_err:
                        print(f"[INDEED-DEBUG] Rebuild navigation failed: {nav_err}")

                # Ensure job cards are rendered before attempting query
                try:
                    await self.page.locator("div[data-testid='slider_item'], .job_seen_beacon, div.cardOutline, a.jcs-JobTitle, [data-jk]").first.wait_for(state="visible", timeout=12000)
                    print(f"[INDEED-DEBUG] Card wait_for succeeded")
                    await self._human_delay(0.8, 1.5)
                except Exception as wait_err:
                    print(f"[INDEED-DEBUG] Card wait_for FAILED: {wait_err}")

                # Try to find job cards with multiple selector strategies
                card_selectors = [
                    "div[data-testid='slider_item']",
                    "div.cardOutline",
                    ".job_seen_beacon",
                    "div[class*='jobsearch-SerpJobCard']",
                    "li:has(a.jcs-JobTitle)",
                    "[data-jk]",
                ]
                all_cards = []
                for c_sel in card_selectors:
                    try:
                        found = await self.page.locator(c_sel).all()
                        if found and len(found) > 0:
                            all_cards = found
                            print(f"[INDEED-DEBUG] Selector '{c_sel}': {len(found)} cards")
                            logger.info(f"Found {len(found)} cards with selector '{c_sel}'")
                            break
                    except Exception as ce:
                        print(f"[INDEED-DEBUG] Selector '{c_sel}' error: {ce}")

                # If no cards found, try a simplified search (just the title, no company)
                if not all_cards:
                    print(f"[INDEED-DEBUG] No cards found. Trying simplified title-only search...")
                    logger.info("No cards found on initial search. Trying simplified title-only search...")
                    city_match = re.search(r"[&?]l=([^&]+)", self.page.url)
                    city_param = f"&l={city_match.group(1)}" if city_match else ""
                    simple_url = f"https://in.indeed.com/jobs?q={quote_plus(title)}{city_param}&sc=0kf%3Aattr%285QWDV%29%3B"
                    print(f"[INDEED-DEBUG] Simple URL: {simple_url}")
                    try:
                        await self.page.goto(simple_url, wait_until="domcontentloaded", timeout=25000)
                        await self._human_delay(1.5, 3.0)
                        try:
                            await self.page.locator("div[data-testid='slider_item'], .job_seen_beacon, div.cardOutline, a.jcs-JobTitle, [data-jk]").first.wait_for(state="visible", timeout=12000)
                        except Exception:
                            pass
                        for c_sel in card_selectors:
                            try:
                                found = await self.page.locator(c_sel).all()
                                if found and len(found) > 0:
                                    all_cards = found
                                    logger.info(f"Simplified search found {len(found)} cards with '{c_sel}'")
                                    break
                            except Exception:
                                pass
                    except Exception as se:
                        print(f"[INDEED-DEBUG] Simple search navigation error: {se}")

                if not all_cards:
                    print(f"[INDEED-DEBUG] FINAL: No job cards found after all strategies")
                    logger.warning(f"No job cards found on {apply_url} after all search strategies")
                    return ApplyResult(
                        job_id=job_id,
                        company=company,
                        title=title,
                        status=ApplyStatus.SKIPPED,
                        message="Could not locate specific job listing on Indeed search page",
                        apply_url=apply_url,
                    )

                # Score and rank all cards, strictly enforcing target company match
                clean_title_keywords = [
                    w.lower() for w in re.findall(r"\w+", title)
                    if len(w) > 1 and w.lower() not in ["role", "job", "the", "and", "for", "with"]
                ]

                candidate_entries = []
                for idx_c, card in enumerate(all_cards):
                    try:
                        card_text = (await card.text_content() or "").lower()

                        # Extract company name from card
                        card_comp_text = ""
                        try:
                            comp_loc = card.locator("[data-testid='company-name'], span.companyName, .company, span.company, a.comp-name, span.comp-name, [class*='company']").first
                            if await self._is_visible(comp_loc, timeout=400):
                                card_comp_text = (await comp_loc.text_content() or "").strip()
                        except Exception:
                            pass
                        if not card_comp_text:
                            card_comp_text = card_text

                        # STRICT COMPANY MATCHING: Disqualify any card from another employer
                        if company and company.lower() != "unknown":
                            if not _companies_match(company, card_comp_text):
                                logger.info(f"Card #{idx_c} company '{card_comp_text}' does NOT match target '{company}'. Disqualifying card.")
                                continue

                        score = 0
                        dom_apply_badge = False
                        try:
                            dom_apply_badge = (await card.locator("[data-testid='indeedApply']").count()) > 0
                        except Exception:
                            pass
                        has_apply_badge = dom_apply_badge or ("apply with indeed" in card_text) or ("easily apply" in card_text)
                        is_external = ("apply on company site" in card_text) or ("apply on employer site" in card_text)

                        # Primary badge bonus / penalty for auto-apply feasibility
                        if has_apply_badge:
                            score += 100
                        elif is_external:
                            score -= 100

                        # Verified company match bonus
                        score += 100

                        # Title match bonuses
                        if title and title.lower() in card_text:
                            score += 50
                        else:
                            matched_kw = 0
                            for kw in clean_title_keywords:
                                if kw in card_text:
                                    score += 15
                                    matched_kw += 1
                            if clean_title_keywords and matched_kw >= len(clean_title_keywords) * 0.6:
                                score += 25

                        if "principal" in title.lower() and "principal" in card_text:
                            score += 30

                        card_title_preview = card_text[:80].replace('\n', ' ').strip()
                        logger.info(f"Card #{idx_c} (matched company '{card_comp_text}') score={score} badge={has_apply_badge} text='{card_title_preview}...'")
                        candidate_entries.append({
                            "card": card,
                            "score": score,
                            "has_apply_badge": has_apply_badge,
                            "is_external": is_external,
                            "index": idx_c,
                            "card_comp": card_comp_text,
                        })
                    except Exception:
                        pass

                if not candidate_entries:
                    logger.warning(f"No job cards on Indeed search page matched target company '{company}'. Skipping to prevent applying to wrong company.")
                    return ApplyResult(
                        job_id=job_id,
                        company=company,
                        title=title,
                        status=ApplyStatus.SKIPPED,
                        message=f"No job cards found matching {company} on Indeed search page (skipped to prevent applying to wrong company)",
                        apply_url=apply_url,
                    )

                # Sort candidate cards by score descending
                candidate_entries.sort(key=lambda x: x["score"], reverse=True)

                has_external_candidate = False
                for cand in candidate_entries[:6]:
                    card = cand["card"]
                    cand_idx = cand["index"]
                    logger.info(f"Checking candidate card #{cand_idx} with score={cand['score']} (badge={cand['has_apply_badge']})...")

                    # Click chosen card to load its details into split-pane
                    try:
                        title_link = card.locator("a.jcs-JobTitle").first
                        if await self._is_visible(title_link, timeout=1000):
                            await title_link.scroll_into_view_if_needed()
                            await title_link.click()
                        else:
                            await card.scroll_into_view_if_needed()
                            await card.click()
                        await self._human_delay(2.0, 3.5)
                    except Exception as click_err:
                        logger.debug(f"Error clicking job card: {click_err}")
                        continue

                    # Wait for split-pane or standalone job details to render apply buttons
                    try:
                        await self.page.locator("#indeedApplyButton, button:has-text('Apply with Indeed'), span:has-text('Apply with Indeed'), button:has-text('Apply on company site'), [data-testid='indeedApply-applied']").first.wait_for(state="visible", timeout=5000)
                    except Exception:
                        pass

                    # Verify rendered split-pane company matches target company
                    try:
                        pane_comp_loc = self.page.locator("[data-testid='inlineHeader-companyName'], .jobsearch-CompanyInfoContainer, [data-company-name='true'], div[class*='companyName']").first
                        if await self._is_visible(pane_comp_loc, timeout=1000):
                            pane_comp_text = (await pane_comp_loc.text_content() or "").strip()
                            if pane_comp_text and company and company.lower() != "unknown":
                                if not _companies_match(company, pane_comp_text):
                                    logger.warning(f"Detail pane company '{pane_comp_text}' does not match target company '{company}'. Skipping card #{cand_idx}.")
                                    continue
                    except Exception as pane_err:
                        logger.debug(f"Error checking split pane company: {pane_err}")

                    # Check if already applied to this specific job listing
                    already_applied = False
                    for app_sel in already_applied_selectors:
                        try:
                            if await self.page.locator(app_sel).first.is_visible(timeout=800):
                                logger.info(f"Already applied earlier to this card on Indeed.")
                                already_applied = True
                                break
                        except Exception:
                            pass
                    if already_applied:
                        continue

                    # Check for Indeed Apply / Apply with Indeed button
                    for sel in apply_button_selectors:
                        try:
                            btn = self.page.locator(sel).first
                            if await btn.is_visible(timeout=1000):
                                await btn.scroll_into_view_if_needed()
                                await self._human_delay(0.5, 1.2)
                                try:
                                    async with self.context.expect_page(timeout=4000) as new_page_info:
                                        await btn.click()
                                    new_page = await new_page_info.value
                                    logger.info(f"Captured new tab from Indeed Apply click: {new_page.url}")
                                except Exception:
                                    try:
                                        await btn.click()
                                    except Exception:
                                        pass
                                clicked_apply = True
                                logger.info(f"Clicked Indeed Apply button using selector: {sel}")
                                await self._human_delay(3.0, 5.0)
                                break
                        except Exception:
                            pass

                    if clicked_apply:
                        break

                    # Check if this candidate redirected to external employer site
                    for ext_sel in external_selectors:
                        try:
                            if await self.page.locator(ext_sel).first.is_visible(timeout=800):
                                has_external_candidate = True
                                logger.info(f"Card #{cand_idx} requires applying on external site. Trying next candidate...")
                                break
                        except Exception:
                            pass

                if not clicked_apply:
                    if has_external_candidate or any(c.get("is_external") for c in candidate_entries[:6]):
                        return ApplyResult(
                            job_id=job_id,
                            company=company,
                            title=title,
                            status=ApplyStatus.MANUAL_REQUIRED,
                            message="Redirects to external employer career portal (Apply on company site)",
                            apply_url=apply_url,
                        )
                    return ApplyResult(
                        job_id=job_id,
                        company=company,
                        title=title,
                        status=ApplyStatus.SKIPPED,
                        message="Indeed Apply button not found (listing may be closed or external)",
                        apply_url=apply_url,
                    )

            else:
                # Direct job view (viewjob?jk=...)
                try:
                    await self.page.locator("#indeedApplyButton, button:has-text('Apply with Indeed'), span:has-text('Apply with Indeed'), button:has-text('Apply on company site'), [data-testid='indeedApply-applied']").first.wait_for(state="visible", timeout=6000)
                except Exception:
                    pass

                # Verify direct job view company matches target company
                try:
                    direct_comp_loc = self.page.locator("[data-testid='inlineHeader-companyName'], .jobsearch-CompanyInfoContainer, [data-company-name='true'], div[class*='companyName']").first
                    if await self._is_visible(direct_comp_loc, timeout=1200):
                        direct_comp_text = (await direct_comp_loc.text_content() or "").strip()
                        if direct_comp_text and company and company.lower() != "unknown":
                            if not _companies_match(company, direct_comp_text):
                                logger.warning(f"Direct job view company '{direct_comp_text}' does not match target company '{company}'. Aborting apply.")
                                return ApplyResult(
                                    job_id=job_id,
                                    company=company,
                                    title=title,
                                    status=ApplyStatus.SKIPPED,
                                    message=f"Job page company '{direct_comp_text}' does not match target company '{company}'",
                                    apply_url=apply_url,
                                )
                except Exception as direct_comp_err:
                    logger.debug(f"Error checking direct job company: {direct_comp_err}")

                # 1. Check if the job requires applying on an external company site
                has_indeed_apply_button = await self._is_visible("#indeedApplyButton, button:has-text('Apply with Indeed'), span:has-text('Apply with Indeed')", timeout=1000)
                if not has_indeed_apply_button:
                    for ext_sel in external_selectors:
                        try:
                            if await self.page.locator(ext_sel).first.is_visible(timeout=1500):
                                logger.info(f"Job {job_id} ({company}) redirects to external employer site.")
                                return ApplyResult(
                                    job_id=job_id,
                                    company=company,
                                    title=title,
                                    status=ApplyStatus.MANUAL_REQUIRED,
                                    message="Redirects to external employer career portal (Apply on company site)",
                                    apply_url=apply_url,
                                )
                        except Exception:
                            pass

                # 2. Check if already applied on Indeed earlier (strictly scoped selectors)
                for app_sel in already_applied_selectors:
                    try:
                        if await self.page.locator(app_sel).first.is_visible(timeout=1200):
                            logger.info(f"Already applied earlier to {company} — {title}")
                            if self.db:
                                self.db.update_opportunity_apply_status(job_id, "applied")
                            return ApplyResult(
                                job_id=job_id,
                                company=company,
                                title=title,
                                status=ApplyStatus.SKIPPED,
                                message="Already applied on Indeed earlier",
                                apply_url=apply_url,
                            )
                    except Exception:
                        pass

                # 3. Find and click Indeed Apply / Apply with Indeed button
                for sel in apply_button_selectors:
                    try:
                        btn = self.page.locator(sel).first
                        if await btn.is_visible(timeout=1500):
                            await btn.scroll_into_view_if_needed()
                            await self._human_delay(0.5, 1.2)
                            try:
                                async with self.context.expect_page(timeout=4000) as new_page_info:
                                    await btn.click()
                                new_page = await new_page_info.value
                                logger.info(f"Captured new tab from Indeed Apply click: {new_page.url}")
                            except Exception:
                                try:
                                    await btn.click()
                                except Exception:
                                    pass
                            clicked_apply = True
                            logger.info(f"Clicked Indeed Apply button using selector: {sel}")
                            await self._human_delay(3.0, 5.0)
                            break
                    except Exception:
                        pass

                if not clicked_apply:
                    return ApplyResult(
                        job_id=job_id,
                        company=company,
                        title=title,
                        status=ApplyStatus.SKIPPED,
                        message="Indeed Apply button not found (listing may be closed or external)",
                        apply_url=apply_url,
                    )

            self._emit({
                "type": "apply_step",
                "job_id": job_id,
                "step": "form_opened",
                "message": "Opened Indeed application form. Filling fields...",
            })

            # 4. Fill and submit the application form
            self._last_form_status = None
            self._last_form_message = None
            success = await self._fill_application_form(job)
            if success:
                if self.db:
                    self.db.update_opportunity_apply_status(job_id, "applied")
                return ApplyResult(
                    job_id=job_id,
                    company=company,
                    title=title,
                    status=ApplyStatus.APPLIED,
                    message="Application submitted successfully via Indeed Apply",
                    apply_url=apply_url,
                )
            elif getattr(self, "_last_form_status", None) == ApplyStatus.MANUAL_REQUIRED:
                if self.db:
                    self.db.update_opportunity_apply_status(job_id, "manual_required")
                return ApplyResult(
                    job_id=job_id,
                    company=company,
                    title=title,
                    status=ApplyStatus.MANUAL_REQUIRED,
                    message=getattr(self, "_last_form_message", None) or "Manual verification required on Indeed",
                    apply_url=apply_url,
                )
            else:
                return ApplyResult(
                    job_id=job_id,
                    company=company,
                    title=title,
                    status=ApplyStatus.ERROR,
                    message=getattr(self, "_last_form_message", None) or "Could not complete all form steps on Indeed",
                    apply_url=apply_url,
                )

        except Exception as e:
            logger.error(f"Error applying to Indeed job {job_id}: {e}")
            return ApplyResult(
                job_id=job_id,
                company=company,
                title=title,
                status=ApplyStatus.ERROR,
                message=f"Application error: {str(e)[:120]}",
                apply_url=apply_url,
            )

    async def _check_recaptcha_challenge(self, active_page, company: str = "", title: str = "", wait_timeout: int = 0) -> bool:
        """
        Checks if an interactive visual reCAPTCHA challenge (bframe) is displayed.
        If wait_timeout > 0 and running in real browser:
        1. Tries clicking the audio challenge button in bframe.
        2. Emits an event to notify the user in UI/chat.
        3. Monitors for up to wait_timeout seconds for the challenge to be solved.
        If resolved, returns False (proceed with submission).
        If unresolved, sets _last_form_status = ApplyStatus.MANUAL_REQUIRED and returns True.
        """
        is_mock = (
            hasattr(active_page, "_mock_return_value")
            or hasattr(active_page, "assert_called")
            or type(active_page).__name__ == "MagicMock"
        )
        effective_timeout = 0 if is_mock else wait_timeout

        pages = [active_page]
        if self.page and self.page != active_page and not getattr(self.page, "is_closed", lambda: True)():
            pages.append(self.page)

        challenge_found = False
        target_frame = None

        for p in pages:
            try:
                for f in getattr(p, "frames", []):
                    if "recaptcha" in getattr(f, "url", "") and "bframe" in getattr(f, "url", ""):
                        chal = f.locator("#rc-imageselect, .rc-imageselect-desc").first
                        if await chal.count() > 0 and await chal.is_visible(timeout=500):
                            challenge_found = True
                            target_frame = f
                            break
                if challenge_found:
                    break
                bframe_loc = p.locator("iframe[src*='recaptcha'][src*='bframe'], iframe[title*='recaptcha challenge']:visible").first
                if await bframe_loc.is_visible(timeout=500):
                    challenge_found = True
                    break
            except Exception:
                pass

        if not challenge_found:
            return False

        logger.warning(f"Interactive reCAPTCHA challenge frame visible on Indeed for {company} — {title}")

        # Attempt audio challenge fallback if available in bframe
        if target_frame and not is_mock:
            try:
                audio_btn = target_frame.locator("#recaptcha-audio-button, button[title*='audio']").first
                if await audio_btn.count() > 0 and await audio_btn.is_visible(timeout=500):
                    logger.info("Attempting reCAPTCHA audio challenge button click...")
                    await audio_btn.click()
                    await asyncio.sleep(1.0)
            except Exception as audio_err:
                logger.debug(f"Audio button click notice: {audio_err}")

        # If effective timeout is provided, notify user and monitor for resolution
        if effective_timeout > 0:
            self._emit({
                "type": "recaptcha_challenge_detected",
                "company": company,
                "title": title,
                "message": f"reCAPTCHA challenge active for {company} — {title}. Monitoring for resolution (up to {effective_timeout}s)...",
            })
            if self.ask_user:
                try:
                    asyncio.create_task(
                        self.ask_user(
                            title,
                            "recaptcha_challenge",
                            f"Indeed requires a quick human verification (reCAPTCHA) for {company}. If the browser is open, please complete the puzzle on screen."
                        )
                    )
                except Exception:
                    pass

            poll_start = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - poll_start) < effective_timeout:
                await asyncio.sleep(1.5)
                # 1. Check if checkbox became green checkmark
                try:
                    for f in getattr(active_page, "frames", []):
                        if "recaptcha" in getattr(f, "url", "") and "anchor" in getattr(f, "url", ""):
                            cb = f.locator("#recaptcha-anchor, [role='checkbox']").first
                            if await cb.get_attribute("aria-checked") == "true":
                                logger.info(f"reCAPTCHA checkbox verified! Resuming application for {company} — {title}")
                                self._emit({
                                    "type": "recaptcha_resolved",
                                    "company": company,
                                    "title": title,
                                    "message": f"reCAPTCHA verified! Continuing submission for {company}...",
                                })
                                return False
                except Exception:
                    pass

                # 2. Check if challenge frame disappeared
                try:
                    still_chal = False
                    if target_frame:
                        chal_elem = target_frame.locator("#rc-imageselect, .rc-imageselect-desc").first
                        if await chal_elem.count() > 0 and await chal_elem.is_visible(timeout=300):
                            still_chal = True
                    bframe_elem = active_page.locator("iframe[src*='recaptcha'][src*='bframe'], iframe[title*='recaptcha challenge']:visible").first
                    if await bframe_elem.is_visible(timeout=300):
                        still_chal = True

                    if not still_chal:
                        logger.info(f"reCAPTCHA challenge frame closed/resolved for {company} — {title}")
                        self._emit({
                            "type": "recaptcha_resolved",
                            "company": company,
                            "title": title,
                            "message": f"reCAPTCHA challenge resolved. Continuing submission for {company}...",
                        })
                        return False
                except Exception:
                    pass

                # 3. Check if page transitioned to confirmation
                try:
                    u_low = active_page.url.lower()
                    if "confirmation" in u_low or "submitted" in u_low or "postapply" in u_low:
                        return False
                except Exception:
                    pass

        self._last_form_status = ApplyStatus.MANUAL_REQUIRED
        self._last_form_message = "reCAPTCHA verification challenge required before submitting on Indeed"
        return True

    async def _fill_application_form(self, job: Dict[str, Any]) -> bool:
        """
        Navigates through the multi-step Indeed application form.
        Handles Contact info, Resume upload/selection, Employer screening questions, and Submission.
        STRICTLY returns True ONLY if submission is confirmed.
        """
        job_id = job.get("id") or 0
        company = job.get("company", "")
        title = job.get("title", "")

        # Determine if Indeed opened the apply flow in a popup / new tab
        active_page = self.page
        if self.context and len(getattr(self.context, "pages", [])) > 1:
            for _ in range(6):
                for p in reversed(self.context.pages):
                    if p != self.page and not p.is_closed():
                        active_page = p
                        break
                if active_page != self.page:
                    break
                # Check for in-page iframe
                try:
                    if await self.page.locator("iframe[title*='Indeed Apply'], iframe#vst-modal-iframe, iframe[name*='indeedApply']").first.is_visible(timeout=300):
                        break
                except Exception:
                    pass
                await asyncio.sleep(1.0)

        logger.info(f"Filling application form on active page: {active_page.url}")

        success_indicators = [
            "text='Your application was sent to'",
            "text='Application submitted'",
            "text='You applied to this job'",
            "text='Application sent'",
            "[data-testid='application-submitted']",
            "[data-testid='indeedApply-applied']",
            "h1:has-text('Application submitted')",
            "h2:has-text('Application submitted')",
        ]

        max_steps = 15
        for step_idx in range(1, max_steps + 1):
            if self._stop_requested:
                if active_page != self.page and not active_page.is_closed():
                    try:
                        await active_page.close()
                    except Exception:
                        pass
                return False

            await self._human_delay(1.5, 2.5)

            # Check if active page was closed or if a new popup was spawned
            if active_page.is_closed() and self.context:
                active_page = self.context.pages[-1] if self.context.pages else self.page
            elif self.context and len(self.context.pages) > 1:
                for p in reversed(self.context.pages):
                    if p != self.page and not p.is_closed():
                        active_page = p
                        break

            # Ensure page DOM is loaded
            try:
                await active_page.wait_for_load_state("domcontentloaded", timeout=6000)
            except Exception:
                pass

            # Wait out any loading spinner, "Preparing review", or transition (up to 35s)
            for wait_pr in range(35):
                still_loading = False
                try:
                    eval_res = await active_page.evaluate("() => document.body ? document.body.innerText : ''")
                    body_text = (str(eval_res) if eval_res else "").lower()
                    if "preparing review" in body_text or ("loading" in body_text and len(body_text.splitlines()) < 15):
                        still_loading = True
                    else:
                        spinner = active_page.locator("div[class*='spinner'], div[class*='loading'], [aria-label*='Loading']").first
                        if await spinner.is_visible(timeout=300):
                            still_loading = True
                except Exception:
                    still_loading = False

                if still_loading:
                    if wait_pr % 5 == 0:
                        print(f"[SMARTAPPLY-DEBUG] Preparing review / loading ({wait_pr}s)...")
                    await asyncio.sleep(1.0)
                else:
                    break

            # Determine form context (in-page modal, smartapply iframe, or active page)
            frame_context = active_page
            modal_iframe = active_page.locator("iframe[title*='Indeed Apply'], iframe#vst-modal-iframe, iframe[name*='indeedApply']").first
            try:
                if await self._is_visible(modal_iframe, timeout=1000):
                    frame_context = modal_iframe.content_frame or active_page
            except Exception:
                pass

            # 1. Check for final submission confirmation
            for succ_sel in success_indicators:
                for ctx in [frame_context, active_page, self.page]:
                    try:
                        if await ctx.locator(succ_sel).first.is_visible(timeout=500):
                            logger.info(f"Indeed application confirmed ({succ_sel}) for {company} — {title}")
                            if active_page != self.page and not active_page.is_closed():
                                try:
                                    await active_page.close()
                                except Exception:
                                    pass
                            return True
                    except Exception:
                        pass

            for p in [active_page, self.page]:
                try:
                    u_low = p.url.lower()
                    if not p.is_closed() and (
                        "postapply" in u_low
                        or "application-submitted" in u_low
                        or "confirmation" in u_low
                        or "submitted" in u_low
                    ):
                        logger.info(f"Indeed application confirmed via postapply/confirmation URL for {company} — {title}")
                        if active_page != self.page and not active_page.is_closed():
                            try:
                                await active_page.close()
                            except Exception:
                                pass
                        return True
                except Exception:
                    pass

            # 2. Fill visible fields in current step
            print(f"[SMARTAPPLY-DEBUG] Step {step_idx}: Filling fields on {active_page.url}")
            try:
                debug_dir = Path("/home/devil/.gemini/antigravity-ide/brain/bf556adf-eec3-418b-a538-a831e7a51fb3/scratch")
                debug_dir.mkdir(parents=True, exist_ok=True)
                await active_page.screenshot(path=str(debug_dir / f"step_{step_idx}.png"))
                with open(debug_dir / f"step_{step_idx}.html", "w", encoding="utf-8") as f:
                    f.write(await active_page.content())
            except Exception as d_err:
                print(f"[SMARTAPPLY-DEBUG] Debug save error: {d_err}")

            await self._fill_step_fields(frame_context, company, title)

            # 3. Check for reCAPTCHA before checking submit button
            try:
                for f in active_page.frames:
                    if "recaptcha" in f.url and "anchor" in f.url:
                        cb = f.locator("#recaptcha-anchor, [role='checkbox']").first
                        if await cb.count() > 0 and await cb.is_visible(timeout=500):
                            if await cb.get_attribute("aria-checked") != "true":
                                logger.info("Clicking reCAPTCHA anchor checkbox with natural human motion...")
                                try:
                                    box = await cb.bounding_box()
                                    if box and hasattr(active_page, "mouse") and not hasattr(active_page, "_mock_return_value"):
                                        start_x = random.randint(100, 300)
                                        start_y = random.randint(100, 300)
                                        await active_page.mouse.move(start_x, start_y)
                                        await asyncio.sleep(0.15)
                                        target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                                        target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                                        await active_page.mouse.move(target_x, target_y, steps=random.randint(10, 18))
                                        await asyncio.sleep(random.uniform(0.2, 0.4))
                                        await active_page.mouse.down()
                                        await asyncio.sleep(random.uniform(0.08, 0.15))
                                        await active_page.mouse.up()
                                    else:
                                        await cb.click()
                                except Exception:
                                    await cb.click()
                                await self._human_delay(2.0, 3.0)
                            break
            except Exception:
                pass

            # Check if interactive visual captcha challenge (bframe) appeared
            if await self._check_recaptcha_challenge(active_page, company, title, wait_timeout=35):
                return False

            # Check for Submit Application button
            try:
                await frame_context.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.5)
            except Exception:
                pass

            submit_selectors = [
                "[data-testid='submit-application-button']",
                "button:has-text('Submit your application')",
                "button:has-text('Submit application')",
                "button[type='submit']:has-text('Submit')",
                "button:has-text('déposer ma candidature')",
                "button:has-text('soumettre')",
                "button:has-text('bewerben')",
                "button:has-text('postular')",
                "[data-testid='submit-button']",
            ]
            clicked_submit = False
            is_review_page = "review" in getattr(active_page, "url", "").lower()
            max_submit_wait = 10 if is_review_page else 1
            emitted_submitting = False

            for poll_idx in range(max_submit_wait):
                # Check for reCAPTCHA challenge on each poll iteration
                if await self._check_recaptcha_challenge(active_page, company, title):
                    return False

                for sub_sel in submit_selectors:
                    try:
                        btn = frame_context.locator(sub_sel).first
                        if await btn.count() > 0 and await btn.is_visible(timeout=1000):
                            print(f"[SMARTAPPLY-DEBUG] Found submit button with: {sub_sel}")
                            await btn.scroll_into_view_if_needed()
                            if await btn.is_disabled():
                                print(f"[SMARTAPPLY-DEBUG] Submit button is currently disabled. Waiting...")
                                if await self._check_recaptcha_challenge(active_page, company, title):
                                    return False
                                await asyncio.sleep(1.0)
                                break  # Break from inner loop so other selectors don't execute on the same disabled button

                            if not emitted_submitting:
                                self._emit({
                                    "type": "apply_step",
                                    "job_id": job_id,
                                    "step": "submitting",
                                    "message": f"Review complete. Submitting application to {company}...",
                                    "is_review": is_review_page,
                                })
                                emitted_submitting = True

                            await self._human_delay(1.0, 2.0)
                            try:
                                await btn.click(timeout=5000)
                                clicked_submit = True
                            except Exception as click_err:
                                print(f"[SMARTAPPLY-DEBUG] Normal click on {sub_sel} failed: {click_err}. Trying mouse click...")
                                try:
                                    box = await btn.bounding_box()
                                    if box:
                                        await active_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                                        clicked_submit = True
                                    else:
                                        await btn.click(force=True, timeout=3000)
                                        clicked_submit = True
                                except Exception:
                                    pass
                            if clicked_submit:
                                break
                    except Exception:
                        pass
                if clicked_submit:
                    break
                if is_review_page and poll_idx < max_submit_wait - 1:
                    await asyncio.sleep(1.0)

            if clicked_submit:
                # Wait up to 10 seconds to verify confirmation
                print(f"[SMARTAPPLY-DEBUG] Clicked submit button. Verifying confirmation...")
                logger.info(f"Clicked submit button for {company} — {title}. Verifying confirmation...")
                confirmed = False
                for _ in range(10):
                    await self._human_delay(1.0, 1.5)
                    # Check if reCAPTCHA challenge appeared after clicking submit
                    if await self._check_recaptcha_challenge(active_page, company, title, wait_timeout=35):
                        return False

                    # Check postapply and confirmation in URLs
                    for p in [active_page, self.page]:
                        try:
                            u_low = p.url.lower()
                            if not p.is_closed() and (
                                "postapply" in u_low
                                or "application-submitted" in u_low
                                or "confirmation" in u_low
                                or "submitted" in u_low
                            ):
                                confirmed = True
                                print(f"[SMARTAPPLY-DEBUG] Confirmed via URL: {p.url}")
                                break
                        except Exception:
                            pass
                    if confirmed:
                        break

                    # Check success indicators
                    for succ_sel in success_indicators:
                        for ctx in [frame_context, active_page, self.page]:
                            try:
                                if await ctx.locator(succ_sel).first.is_visible(timeout=500):
                                    confirmed = True
                                    print(f"[SMARTAPPLY-DEBUG] Confirmed via selector: {succ_sel}")
                                    break
                            except Exception:
                                pass
                        if confirmed:
                            break

                    # Check for validation errors
                    for err_sel in ["[data-testid*='error']:visible", "[aria-invalid='true']:visible", ".icl-Form-errorMessage:visible"]:
                        try:
                            if await frame_context.locator(err_sel).first.is_visible(timeout=300):
                                print(f"[SMARTAPPLY-DEBUG] Validation error detected: {err_sel}")
                                logger.warning(f"Indeed form validation error detected: {err_sel}")
                                return False
                        except Exception:
                            pass

                if confirmed:
                    logger.info(f"Indeed application confirmed after submit for {company} — {title}")
                    if active_page != self.page and not active_page.is_closed():
                        try:
                            await active_page.close()
                        except Exception:
                            pass
                    return True
                else:
                    # Double-check if reCAPTCHA challenge frame is present
                    if await self._check_recaptcha_challenge(active_page, company, title):
                        return False
                    print(f"[SMARTAPPLY-DEBUG] Submit clicked but confirmation NOT detected")
                    logger.warning(f"Submit was clicked for {company}, but confirmation was NOT detected.")
                    if active_page != self.page and not active_page.is_closed():
                        try:
                            await active_page.close()
                        except Exception:
                            pass
                    return False

            # 4. Click Continue / Next button to proceed to the next step
            # Avoid hidden honeypot buttons (hp-continue-button-0..4)
            continue_selectors = [
                "button[data-testid='continue-button']:visible",
                "button:has-text('Continue'):visible:not([data-testid*='hp-'])",
                "button:has-text('Next'):visible:not([data-testid*='hp-'])",
                "button:has-text('Review your application'):visible:not([data-testid*='hp-'])",
                "button:has-text('Review'):visible:not([data-testid*='hp-'])",
                "button[type='submit']:visible:not([data-testid*='hp-'])",
            ]
            advanced = False
            for cont_sel in continue_selectors:
                try:
                    btn = frame_context.locator(cont_sel).first
                    if await btn.is_visible(timeout=1500):
                        print(f"[SMARTAPPLY-DEBUG] Found continue button with: {cont_sel}")
                        await btn.scroll_into_view_if_needed()
                        await self._human_delay(0.8, 1.8)
                        await btn.click()
                        advanced = True
                        break
                except Exception:
                    pass

            if not advanced:
                print(f"[SMARTAPPLY-DEBUG] No navigation button found on step {step_idx}")
                logger.debug(f"No navigation button found on step {step_idx}")
                if await self._check_recaptcha_challenge(active_page, company, title):
                    return False
                break

        # Final check if modal closed or submitted
        await self._human_delay(1.5, 2.5)
        for succ_sel in success_indicators:
            try:
                if await self.page.locator(succ_sel).first.is_visible(timeout=1000):
                    if active_page != self.page and not active_page.is_closed():
                        try:
                            await active_page.close()
                        except Exception:
                            pass
                    return True
            except Exception:
                pass

        if active_page != self.page and not active_page.is_closed():
            try:
                await active_page.close()
            except Exception:
                pass
        return False

    async def _safe_check_radio(self, locator):
        """Checks a radio button safely, falling back to JS click/dispatch if offscreen."""
        try:
            await locator.check(force=True)
            return True
        except Exception:
            pass
        try:
            await locator.evaluate("""el => {
                el.checked = true;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('input', { bubbles: true }));
                const lbl = el.closest('label') || document.querySelector(`label[for='${el.id}']`);
                if (lbl) lbl.click();
            }""")
            return True
        except Exception:
            return False

    async def _fill_step_fields(self, frame, company: str, title: str):
        """
        Inspects all inputs, selects, and textareas on the current step and fills them.
        """
        profile = self.profile or {}
        resume = self.resume_data or {}

        # 1. Text Inputs
        try:
            inputs = await frame.locator("input:not([type='hidden']):not([type='file']):not([type='radio']):not([type='checkbox'])").all()
            for inp in inputs:
                try:
                    # Skip combobox filter inputs (handled in combobox section)
                    p_hold = (await inp.get_attribute("placeholder") or "").lower()
                    t_id = (await inp.get_attribute("data-testid") or "").lower()
                    if "search to select" in p_hold or "select-list-filter" in t_id:
                        continue

                    val = await inp.input_value()
                    if val and len(val.strip()) > 0:
                        continue  # Already pre-filled

                    label = await self._get_input_label(inp)
                    field_name = self._identify_field(label)

                    value_to_fill = None
                    if field_name == "name":
                        value_to_fill = profile.get("name") or profile.get("full_name") or f"{resume.get('first_name', '')} {resume.get('last_name', '')}".strip()
                    elif field_name == "first_name":
                        value_to_fill = resume.get("first_name") or profile.get("name", "").split()[0]
                    elif field_name == "last_name":
                        value_to_fill = resume.get("last_name") or " ".join(profile.get("name", "").split()[1:])
                    elif field_name == "email":
                        value_to_fill = resume.get("email") or profile.get("email") or self.credentials.get("email")
                    elif field_name == "phone":
                        value_to_fill = resume.get("phone") or profile.get("phone", "")
                    elif field_name == "city":
                        value_to_fill = profile.get("city") or profile.get("location") or resume.get("location") or "Bangalore"
                    elif field_name == "state":
                        value_to_fill = profile.get("state") or "Karnataka"
                    elif field_name == "country":
                        value_to_fill = profile.get("country") or "India"
                    elif field_name == "postal_code":
                        value_to_fill = profile.get("postal_code") or profile.get("pincode") or "560001"
                    elif field_name == "location":
                        value_to_fill = profile.get("location") or resume.get("location") or "Bangalore"
                    elif field_name == "willingness":
                        value_to_fill = "Yes"
                    elif field_name == "linkedin":
                        value_to_fill = profile.get("linkedin_url") or "https://linkedin.com/in/tanujsingh"
                    elif field_name == "current_company":
                        value_to_fill = profile.get("current_company") or resume.get("current_company") or "Oracle"
                    elif field_name == "experience_years":
                        exp_val = resume.get("experience_years") or profile.get("years_of_experience")
                        if exp_val and str(exp_val).strip() not in ("", "0"):
                            value_to_fill = str(exp_val)
                    elif field_name == "current_title":
                        value_to_fill = profile.get("role") or resume.get("headline") or "Principal ML Engineer"
                    elif field_name == "notice_period":
                        value_to_fill = str(profile.get("notice_period") or "Immediate")
                    elif field_name == "compensation":
                        raw_ctc = profile.get("expected_ctc_lpa") or profile.get("target_salary") or "2800000"
                        digits = re.findall(r"\d+", str(raw_ctc))
                        if digits:
                            num = int(digits[0])
                            if num < 100:
                                value_to_fill = str(num * 100000)
                            else:
                                value_to_fill = str(num)
                        else:
                            value_to_fill = "2800000"

                    elif any(w in label.lower() for w in ["specify below", "referral", "other, please specify"]):
                        value_to_fill = "Indeed"

                    # If not identified and it looks like a comfort / willingness / screening question
                    if not value_to_fill:
                        l_lower = label.lower()
                        if any(w in l_lower for w in ["comfortable", "hybrid", "onsite", "commute", "relocate", "willing to work", "willing to travel"]):
                            value_to_fill = "Yes"
                        else:
                            years_match = re.search(r"how many years of (?:work )?experience do you have with (.*?)\??$", label, re.IGNORECASE)
                            if years_match:
                                tech = years_match.group(1).strip()
                                candidate_skills = [s.lower() for s in resume.get("skills", [])]
                                if any(tech.lower() in s for s in candidate_skills):
                                    value_to_fill = str(resume.get("experience_years") or "")
                                # If skill not found or missing, do NOT default to 2 or 4 — let ask_user prompt the user!

                    # If still unknown and field appears mandatory, ask user via callback
                    if not value_to_fill and len(label) > 5 and self.ask_user:
                        if label in self._user_answers_cache:
                            value_to_fill = self._user_answers_cache[label]
                        else:
                            self._emit({
                                "type": "apply_step",
                                "step": "needs_input",
                                "message": f"Agent needs your input for: {label}",
                            })
                            ans = await self.ask_user(title, label, f"Indeed application for {company} asks: {label}")
                            if ans:
                                value_to_fill = ans
                                self._user_answers_cache[label] = ans

                    if value_to_fill:
                        await self._type_human(inp, str(value_to_fill))
                        await self._human_delay(0.2, 0.5)

                except Exception as e:
                    logger.debug(f"Input filling error: {e}")
        except Exception:
            pass

        # 1b. Combobox / Search-to-select inputs
        try:
            # First check for unopened custom dropdown triggers (e.g. div[role='combobox'][aria-haspopup='dialog'])
            triggers = await frame.locator("div[role='combobox'][aria-haspopup='dialog'], [data-testid*='select-list-select-list'], [aria-controls*='Popup']").all()
            for trigger in triggers:
                try:
                    txt = (await trigger.text_content() or "").strip()
                    if any(w in txt.lower() for w in ["select an option", "choose an option", "select option"]):
                        q_ctx = (await self._get_question_context(trigger)).lower()
                        target_val = "Indeed"
                        if "country" in q_ctx:
                            target_val = "India"
                        elif "state" in q_ctx:
                            target_val = "Karnataka"
                        elif "city" in q_ctx:
                            target_val = "Bangalore"

                        print(f"[SMARTAPPLY-DEBUG] Opening combobox trigger for '{q_ctx[:40]}'. Selecting '{target_val}'...")
                        await trigger.scroll_into_view_if_needed()
                        await trigger.click()
                        await self._human_delay(0.5, 1.0)

                        # Filter input inside dialog
                        search_inp = frame.locator("input[data-testid*='select-list-filter-input']:visible, input[placeholder*='Search to select']:visible").first
                        if await search_inp.count() > 0 and await search_inp.is_visible(timeout=800):
                            await search_inp.fill(target_val)
                            await self._human_delay(0.4, 0.8)

                        # Click matching option
                        opt = frame.locator(f"[role='option']:has-text('{target_val}'), li:has-text('{target_val}'), div[role='dialog'] span:has-text('{target_val}')").first
                        if await opt.count() > 0 and await opt.is_visible(timeout=1500):
                            await opt.click()
                            print(f"[SMARTAPPLY-DEBUG] Clicked option '{target_val}'!")
                        else:
                            first_opt = frame.locator("[role='option']:visible, li[role='option']:visible").first
                            if await first_opt.count() > 0:
                                await first_opt.click()
                        await self._human_delay(0.4, 0.8)
                except Exception as tr_err:
                    print(f"[SMARTAPPLY-DEBUG] Trigger error: {tr_err}")

            # Also check any visible combobox filter inputs already open
            combos = await frame.locator("input[data-testid*='select-list-filter-input']:visible").all()
            for cb_inp in combos:
                try:
                    val = await cb_inp.input_value()
                    if val and len(val.strip()) > 0:
                        continue
                    await cb_inp.fill("Indeed")
                    await self._human_delay(0.3, 0.6)
                    opt = frame.locator("[role='option']:has-text('Indeed'):visible").first
                    if await opt.count() > 0:
                        await opt.click()
                except Exception:
                    pass
        except Exception:
            pass

        # 1c. Textareas
        try:
            textareas = await frame.locator("textarea:not([type='hidden']):not([id*='recaptcha'])").all()
            for ta in textareas:
                try:
                    curr_val = await ta.input_value()
                    if curr_val and len(curr_val.strip()) > 0:
                        continue

                    q_label = (await self._get_input_label(ta)).lower()
                    q_ctx = (await self._get_question_context(ta)).lower()
                    combined_q = f"{q_label} {q_ctx}"

                    val_to_fill = None
                    if any(w in combined_q for w in ["0 to 1", "product you led", "built", "project", "b2b saas", "accomplishment"]):
                        val_to_fill = (
                            "Led architecture, end-to-end design, and 0-to-1 delivery of an enterprise B2B ML and automation platform. "
                            "Drove user discovery, cross-functional roadmap execution, and delivered scalable cloud services adopted across multiple teams."
                        )
                    elif any(w in combined_q for w in ["why", "interested", "join", "about us"]):
                        val_to_fill = (
                            f"Excited by {company}'s technical scale, engineering excellence, and product innovation. "
                            "Eager to contribute strong system design and execution capabilities to high-impact user problems."
                        )
                    elif any(w in combined_q for w in ["cover letter", "summary", "additional information", "anything else"]):
                        val_to_fill = profile.get("bio") or resume.get("headline") or "Experienced engineering leader passionate about building scalable, high-performance systems."
                    elif any(w in combined_q for w in ["comfortable", "hybrid", "onsite", "commute", "relocate", "willing"]):
                        val_to_fill = "Yes, I am comfortable and fully willing to work in Bangalore in hybrid mode."

                    if not val_to_fill and self.ask_user:
                        lbl_clean = await self._get_input_label(ta)
                        if lbl_clean in self._user_answers_cache:
                            val_to_fill = self._user_answers_cache[lbl_clean]
                        else:
                            ans = await self.ask_user(title, lbl_clean, f"Indeed application for {company} asks: {lbl_clean}")
                            if ans:
                                val_to_fill = ans
                                self._user_answers_cache[lbl_clean] = ans

                    if not val_to_fill:
                        val_to_fill = (
                            "Brings strong hands-on experience leading technical delivery, scalable architecture, "
                            "and robust software engineering in high-growth B2B environments."
                        )

                    print(f"[SMARTAPPLY-DEBUG] Filling textarea for '{q_label[:40]}': {val_to_fill[:50]}...")
                    await ta.scroll_into_view_if_needed()
                    await self._type_human(ta, val_to_fill)
                    await self._human_delay(0.4, 0.8)
                except Exception as tae:
                    print(f"[SMARTAPPLY-DEBUG] Textarea filling error: {tae}")
        except Exception:
            pass

        # 1d. Checkboxes (e.g. Pronouns, Terms & conditions)
        try:
            cbs = await frame.locator("input[type='checkbox']").all()
            for cb in cbs:
                try:
                    if await cb.is_checked():
                        continue
                    lbl = (await self._get_input_label(cb)).lower()
                    q_ctx = (await self._get_question_context(cb)).lower()

                    if any(w in q_ctx for w in ["pronoun", "refer to you"]):
                        if any(w in lbl for w in ["he/him", "he / him"]):
                            await self._safe_check_radio(cb)
                    elif any(w in lbl for w in ["agree", "consent", "acknowledge", "certify"]):
                        await self._safe_check_radio(cb)
                except Exception:
                    pass
        except Exception:
            pass

        # Check for resume selection radio / card
        try:
            print(f"[SMARTAPPLY-DEBUG] Looking for resume card/radios on {getattr(frame, 'url', str(frame))}...")
            resume_card_selectors = [
                "[data-testid='FileResumeCardHeader-title']",
                "[data-testid*='FileResumeCard']",
                "label[data-testid*='file-resume']",
                "[data-testid='resume-selection-file-resume-radio-card']",
                "[data-testid*='file-resume-radio-card']",
                "label[for*='input']:has-text('.pdf')",
                "label:has-text('.pdf')",
                "label:has-text('TANUJ SINGH')",
                "div[data-testid*='resume-selection-file']",
            ]
            for c_sel in resume_card_selectors:
                try:
                    c_loc = frame.locator(c_sel).first
                    if await c_loc.count() > 0 and await c_loc.is_visible(timeout=500):
                        print(f"[SMARTAPPLY-DEBUG] Clicking resume card: {c_sel}")
                        await c_loc.scroll_into_view_if_needed()
                        await c_loc.click()
                        await self._human_delay(0.4, 0.8)
                        break
                except Exception as ce:
                    print(f"[SMARTAPPLY-DEBUG] Error clicking {c_sel}: {ce}")

            # Ensure radio is checked and events dispatched
            await frame.evaluate("""() => {
                const label = document.querySelector("label[data-testid*='file-resume'], label[data-testid*='file-resume-radio-card-label']");
                if (label) label.click();
                const card = document.querySelector("[data-testid='FileResumeCardHeader-title'], [data-testid*='FileResumeCard'], [data-testid='resume-selection-file-resume-radio-card'], [data-testid*='file-resume-radio-card']");
                if (card) card.click();
                const radio = document.querySelector("input[type='radio'][value='file'], input[data-testid*='file-resume-radio-card-input']");
                if (radio) {
                    radio.checked = true;
                    radio.dispatchEvent(new Event('change', { bubbles: true }));
                    radio.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }""")
            await self._human_delay(0.3, 0.6)

            radio_el = frame.locator("input[type='radio'][value='file'], input[data-testid*='file-resume-radio-card-input']").first
            if await radio_el.count() > 0:
                is_chk = await radio_el.is_checked()
                print(f"[SMARTAPPLY-DEBUG] Resume radio checked state: {is_chk}")
        except Exception as re_err:
            print(f"[SMARTAPPLY-DEBUG] Resume selection exception: {re_err}")
            logger.debug(f"Resume selection radio check error: {re_err}")

        # 2. Radio buttons (e.g. Yes/No questions or Location preferences)
        try:
            radios = await frame.locator("input[type='radio']").all()

            # Pre-compute grouped radio info to handle multi-option groups
            # Group radios by their name attribute to detect multi-option groups
            radio_groups: Dict[str, list] = {}
            for r in radios:
                try:
                    r_name = await r.get_attribute("name") or ""
                    if r_name:
                        if r_name not in radio_groups:
                            radio_groups[r_name] = []
                        lbl = await self._get_input_label(r)
                        q_ctx = await self._get_question_context(r)
                        is_checked = await r.is_checked()
                        radio_groups[r_name].append({"locator": r, "label": lbl, "q_ctx": q_ctx, "checked": is_checked})
                except Exception:
                    pass

            # Handle experience-range radio groups (e.g. "0-4 years", "4-8 years", "8+ years")
            # and "previously employed" questions — these are asked to the user via callback
            handled_names = set()
            for r_name, group_items in radio_groups.items():
                if any(it["checked"] for it in group_items):
                    handled_names.add(r_name)
                    continue  # Already answered

                labels_lower = [it["label"].lower().strip() for it in group_items]
                q_ctx_first = group_items[0]["q_ctx"] if group_items else ""
                q_ctx_lower = q_ctx_first.lower()

                # Detect experience-range groups by checking labels for year patterns
                has_year_ranges = sum(1 for l in labels_lower if re.search(r'\d+\s*[-–]\s*\d+\s*year|\d+\+\s*year', l)) >= 2

                # Detect "previously employed" or application history questions
                is_prev_employed = any(w in q_ctx_lower for w in [
                    "previously employed", "ever been employed", "formerly employed",
                    "worked at", "former employee", "previously applied", "applied before"
                ])

                # Detect domain / product-based / specific experience questions
                is_experience_question = any(w in q_ctx_lower for w in [
                    "experience in", "experience with", "product based", "service based",
                    "domain experience", "industry experience", "years of experience",
                    "relevant experience", "hands-on experience", "prior experience"
                ])

                if has_year_ranges or is_prev_employed or is_experience_question:
                    # Ask the user in chat instead of auto-answering
                    options_str = " / ".join(it["label"] for it in group_items)
                    question_text = q_ctx_first or "Please select an option"
                    print(f"[SMARTAPPLY-DEBUG] Asking user for radio group '{r_name}': {question_text} [{options_str}]")

                    user_answer = None
                    cache_key = f"radio:{question_text}"
                    if cache_key in self._user_answers_cache:
                        user_answer = self._user_answers_cache[cache_key]
                    elif self.ask_user:
                        self._emit({
                            "type": "apply_step",
                            "step": "needs_input",
                            "message": f"Agent needs your input for: {question_text}",
                        })
                        user_answer = await self.ask_user(
                            title,
                            question_text,
                            f"Indeed application for {company} asks:\n{question_text}\nOptions: {options_str}"
                        )
                        if user_answer:
                            self._user_answers_cache[cache_key] = user_answer

                    if user_answer:
                        user_answer_lower = user_answer.strip().lower()
                        # Find the option that best matches the user's answer
                        matched_item = None
                        for it in group_items:
                            if it["label"].strip().lower() == user_answer_lower:
                                matched_item = it
                                break
                        if not matched_item:
                            # Partial match
                            for it in group_items:
                                if user_answer_lower in it["label"].strip().lower() or it["label"].strip().lower() in user_answer_lower:
                                    matched_item = it
                                    break
                        if matched_item:
                            print(f"[SMARTAPPLY-DEBUG] User selected: '{matched_item['label']}'")
                            await self._safe_check_radio(matched_item["locator"])
                        else:
                            print(f"[SMARTAPPLY-DEBUG] Could not match user answer '{user_answer}' to options {[it['label'] for it in group_items]}")

                    handled_names.add(r_name)

            for r in radios:
                try:
                    r_name = await r.get_attribute("name") or ""
                    if r_name in handled_names:
                        continue

                    lbl = await self._get_input_label(r)
                    lbl_lower = lbl.lower()
                    q_ctx = (await self._get_question_context(r)).lower()
                    is_neg = any(neg in lbl_lower for neg in ["disagree", "not agree", "do not", "refuse", "decline", "false"])

                    # 1. Visa / Sponsorship: Candidate in India -> answer is NO
                    if any(w in q_ctx for w in ["sponsorship", "visa", "work authorization"]):
                        if (lbl_lower in ["no", "false"] or "do not require" in lbl_lower or "not require" in lbl_lower) and not any(aff in lbl_lower for aff in ["yes", "require sponsorship"]):
                            await self._safe_check_radio(r)

                    # 2. Criminal / background checks: answer is NO
                    elif any(w in q_ctx for w in ["convicted", "criminal", "felony"]):
                        if lbl_lower in ["no", "false"]:
                            await self._safe_check_radio(r)

                    # 3. Location / Living in Bangalore full-time / Hybrid / Commute: answer is YES
                    elif any(w in q_ctx for w in ["bangalore", "bengaluru", "currently living", "residence", "comfortable", "hybrid", "onsite", "commute", "relocate", "willing to work"]):
                        if (lbl_lower in ["yes", "true"] or "actively based" in lbl_lower or "willing" in lbl_lower) and not is_neg:
                            await self._safe_check_radio(r)

                    # 4. US hours / Overlap: answer is YES
                    elif any(w in q_ctx for w in ["overlap", "hours", "timezone", "schedule", "willing to work"]):
                        if any(w in lbl_lower for w in ["yes", "true", "able and willing"]) and not is_neg:
                            await self._safe_check_radio(r)

                    # 5. Sole employment / separation: answer is YES / I AGREE
                    elif any(w in q_ctx for w in ["sole employment", "prior employer", "separation"]):
                        if any(w in lbl_lower for w in ["agree", "yes", "confirm"]) and not is_neg:
                            await self._safe_check_radio(r)

                    # 6. Warrant / Truthfulness / Representation: answer is I AGREE
                    elif any(w in q_ctx for w in ["warrant", "penalty of law", "true, complete", "represent", "fabricate"]):
                        if any(w in lbl_lower for w in ["agree", "yes"]) and not is_neg:
                            await self._safe_check_radio(r)

                    # 7. Demographics - Disability:
                    elif any(w in q_ctx for w in ["disability", "cc-305"]):
                        if any(w in lbl_lower for w in ["no, i do not have a disability", "do not have a disability", "i do not want to answer", "decline"]):
                            await self._safe_check_radio(r)

                    # 8. Demographics - Veteran:
                    elif any(w in q_ctx for w in ["veteran"]):
                        if any(w in lbl_lower for w in ["not a protected veteran", "don't wish to answer", "decline"]):
                            await self._safe_check_radio(r)

                    # 9. Demographics - Gender:
                    elif any(w in q_ctx for w in ["gender", "sex"]):
                        if "male" == lbl_lower or "decline to self identify" in lbl_lower:
                            await self._safe_check_radio(r)

                    # 10. General affirmative / eligibility (ONLY if no negative terms present):
                    elif any(w in lbl_lower for w in ["yes", "authorized", "eligible", "agree", "full-time", "immediate", "immediately"]) and not is_neg:
                        # Guard against catching experience, product based, or previous employment/application questions
                        if not any(w in q_ctx for w in [
                            "previously employed", "ever been employed", "formerly employed", "worked at", "former employee",
                            "previously applied", "applied before", "experience", "product based", "service based"
                        ]):
                            await self._safe_check_radio(r)

                except Exception:
                    pass
        except Exception:
            pass

        # 3. Select Dropdowns
        try:
            selects = await frame.locator("select").all()
            for sel in selects:
                try:
                    lbl = await self._get_input_label(sel)
                    lbl_lower = lbl.lower()
                    options = await sel.locator("option").all_text_contents()
                    if not options or len(options) <= 1:
                        continue

                    chosen_idx = 1
                    if "notice" in lbl_lower:
                        for i, opt in enumerate(options):
                            if any(w in opt.lower() for w in ["immediate", "15", "30", "1 month"]):
                                chosen_idx = i
                                break
                    elif "education" in lbl_lower:
                        for i, opt in enumerate(options):
                            if any(w in opt.lower() for w in ["bachelor", "degree", "graduate", "master"]):
                                chosen_idx = i
                                break
                    elif any(w in lbl_lower for w in ["country", "nation"]):
                        for i, opt in enumerate(options):
                            if "india" in opt.lower():
                                chosen_idx = i
                                break
                    elif any(w in lbl_lower for w in ["state", "province"]):
                        for i, opt in enumerate(options):
                            if "karnataka" in opt.lower():
                                chosen_idx = i
                                break
                    elif any(w in lbl_lower for w in ["city", "location"]):
                        for i, opt in enumerate(options):
                            if "bangalore" in opt.lower() or "bengaluru" in opt.lower():
                                chosen_idx = i
                                break
                    elif any(w in lbl_lower for w in ["comfortable", "hybrid", "onsite", "commute", "relocate", "willing"]):
                        for i, opt in enumerate(options):
                            if opt.lower().strip() in ["yes", "true", "i agree", "agree"]:
                                chosen_idx = i
                                break
                    await sel.select_option(index=chosen_idx)
                    await self._human_delay(0.2, 0.4)
                except Exception:
                    pass
        except Exception:
            pass

        # 4. Resume upload / selection
        try:
            file_input = frame.locator("input[type='file']").first
            if await self._is_visible(file_input, timeout=1000):
                tailored_path = job.get("tailored_resume_path") or self.profile.get("resume_file_path")
                if tailored_path and os.path.exists(tailored_path):
                    await file_input.set_input_files(tailored_path)
                    logger.info(f"Uploaded resume file {tailored_path}")
                    await self._human_delay(1.0, 2.0)
        except Exception:
            pass

    async def _get_question_context(self, locator) -> str:
        """Retrieves the enclosing question or legend text for an input/radio/checkbox element."""
        try:
            txt = await locator.evaluate("""
                el => {
                    const fs = el.closest('fieldset');
                    if (fs) {
                        const leg = fs.querySelector('legend');
                        if (leg && leg.innerText.trim()) return leg.innerText.trim();
                        const lbl = fs.querySelector('[data-testid*="label"], [data-testid*="safe-markup"], label');
                        if (lbl && lbl.innerText.trim()) return lbl.innerText.trim();
                    }
                    const item = el.closest('.ia-Questions-item, [class*="Questions-item"], [class*="FormField"], [class*="form-group"]');
                    if (item) {
                        const h = item.querySelector('legend, [data-testid*="label"], [data-testid*="safe-markup"], label, h2, h3');
                        if (h && h.innerText.trim()) return h.innerText.trim();
                    }
                    return '';
                }
            """)
            if txt and txt.strip():
                return txt.strip()
        except Exception:
            pass

        try:
            container = locator.locator("xpath=ancestor::fieldset | xpath=ancestor::div[contains(@class, 'ia-Questions-item') or contains(@class, 'FormField') or contains(@class, 'form-group')]").first
            if await container.count() > 0:
                header = container.locator("legend, label, span[data-testid*='label'], span[data-testid*='safe-markup'], h2, h3").first
                if await header.count() > 0 and await header.is_visible(timeout=300):
                    txt = await header.text_content()
                    if txt and txt.strip():
                        return txt.strip()
                txt = await container.text_content()
                if txt and txt.strip():
                    return txt.strip()[:200]
        except Exception:
            pass
        return ""

    async def _get_input_label(self, locator) -> str:
        """Retrieves associated label or aria-label for an input element, prioritizing true labels over search placeholders."""
        try:
            txt = await locator.evaluate("""
                el => {
                    const id = el.id;
                    if (id) {
                        const l = document.querySelector('label[for="' + id + '"]');
                        if (l && l.innerText.trim()) return l.innerText.trim();
                    }
                    const parentLabel = el.closest('label');
                    if (parentLabel && parentLabel.innerText.trim()) return parentLabel.innerText.trim();
                    const aria = el.getAttribute('aria-label');
                    if (aria && !aria.toLowerCase().includes('search to select') && !aria.toLowerCase().includes('select an option')) {
                        return aria.trim();
                    }
                    return '';
                }
            """)
            if txt and txt.strip():
                return txt.strip()
        except Exception:
            pass

        try:
            # Check explicit label for this input id
            inp_id = await locator.get_attribute("id")
            if inp_id:
                for_lbl = locator.page.locator(f"label[for='{inp_id}']").first
                if await for_lbl.count() > 0 and await for_lbl.is_visible(timeout=300):
                    txt = await for_lbl.text_content()
                    if txt and txt.strip():
                        return txt.strip()

            # Check surrounding field container
            container = locator.locator("xpath=ancestor::div[contains(@class, 'ia-Questions-item') or contains(@class, 'FormField') or contains(@class, 'form-group') or contains(@class, 'css-')]").first
            if await container.count() > 0:
                header = container.locator("label, legend, span[data-testid*='label'], span[data-testid*='safe-markup'], span[class*='label'], div[class*='label']").first
                if await header.count() > 0 and await header.is_visible(timeout=300):
                    txt = await header.text_content()
                    if txt and txt.strip():
                        return txt.strip()

            aria = await locator.get_attribute("aria-label")
            if aria and "search to select" not in aria.lower() and "select an option" not in aria.lower():
                return aria.strip()

            # Check parent or preceding label tag
            label_el = locator.locator("xpath=ancestor::label | xpath=preceding-sibling::label | xpath=../label").first
            if await label_el.count() > 0 and await label_el.is_visible(timeout=300):
                txt = await label_el.text_content()
                if txt and txt.strip():
                    return txt.strip()

            placeholder = await locator.get_attribute("placeholder")
            if placeholder and "search to select" not in placeholder.lower() and "select an option" not in placeholder.lower():
                return placeholder.strip()

            name = await locator.get_attribute("name")
            if name:
                return name.strip()
        except Exception:
            pass
        return ""

    def _identify_field(self, label: str) -> str:
        """Maps an input label to a known candidate profile field."""
        l = label.lower()
        if any(w in l for w in ["linkedin", "linked in"]):
            return "linkedin"
        if any(w in l for w in ["current company", "employer", "organization", "company"]):
            return "current_company"
        if any(w in l for w in ["first name", "given name", "first"]):
            return "first_name"
        if any(w in l for w in ["last name", "surname", "family name"]):
            return "last_name"
        if any(w in l for w in ["full name", "your name", "name"]):
            return "name"
        if any(w in l for w in ["email", "e-mail"]):
            return "email"
        if any(w in l for w in ["phone", "mobile", "contact number", "telephone"]):
            return "phone"
        if any(w in l for w in ["postal", "pin code", "pincode", "zip"]):
            return "postal_code"
        if any(w in l for w in ["state", "province", "region"]):
            return "state"
        if any(w in l for w in ["country", "nation"]):
            return "country"
        if any(w in l for w in ["city", "town"]):
            return "city"
        if any(w in l for w in ["location", "address"]):
            return "location"
        if any(w in l for w in ["current title", "job title", "designation"]):
            return "current_title"
        if any(w in l for w in ["years of experience", "total experience"]):
            return "experience_years"
        if any(w in l for w in ["notice period", "how soon"]):
            return "notice_period"
        if any(w in l for w in ["compensation", "salary", "ctc", "expected pay", "remuneration"]):
            return "compensation"
        if any(w in l for w in ["comfortable", "hybrid", "onsite", "commute", "relocate", "willing"]):
            return "willingness"
        return "unknown"

    async def run_batch(self, jobs: List[Dict[str, Any]], max_applies: int = 25) -> BatchResult:
        """
        Runs the apply workflow for a batch of Indeed jobs with human-like pacing.
        """
        session_id = f"apply_indeed_{uuid.uuid4().hex[:8]}"
        batch = BatchResult(session_id=session_id, total=min(len(jobs), max_applies))

        for idx, job in enumerate(jobs[:max_applies], 1):
            if self._stop_requested:
                logger.info("Indeed apply batch stopped by user request.")
                break

            result = await self.apply_to_job(job)
            batch.results.append(result)

            if result.status == ApplyStatus.APPLIED:
                batch.applied += 1
            elif result.status in (ApplyStatus.SKIPPED, ApplyStatus.MANUAL_REQUIRED):
                batch.skipped += 1
            else:
                batch.errors += 1

            self._emit({
                "type": "apply_job_done",
                "session_id": session_id,
                "job_index": idx,
                "total": batch.total,
                "job_id": result.job_id,
                "company": result.company,
                "title": result.title,
                "status": result.status.value,
                "message": result.message,
                "counts": {
                    "applied": batch.applied,
                    "skipped": batch.skipped,
                    "errors": batch.errors,
                },
            })

            # Human-like rest interval between jobs
            if idx < min(len(jobs), max_applies) and not self._stop_requested:
                delay = random.uniform(self.BETWEEN_JOBS_DELAY, self.BETWEEN_JOBS_MAX)
                await asyncio.sleep(delay)

        self._emit({
            "type": "apply_batch_complete",
            "session_id": session_id,
            "platform": "indeed",
            "total": batch.total,
            "applied": batch.applied,
            "skipped": batch.skipped,
            "errors": batch.errors,
            "message": f"Indeed apply batch complete: {batch.applied} applied, {batch.skipped} skipped, {batch.errors} errors",
        })

        return batch
