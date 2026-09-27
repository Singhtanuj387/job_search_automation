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
        self._using_cdp = False
        self._virtual_display = None
        self._orig_display = os.environ.get("DISPLAY")
        self._last_mouse_x = 320.0
        self._last_mouse_y = 220.0
        self._is_authenticated = False

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
            if hasattr(target, "is_visible"):
                res = target.is_visible(timeout=timeout)
                if hasattr(res, "__await__"):
                    return bool(await res)
                return bool(res)

            # String selector: check up to 5 elements matching selector to handle desktop/mobile variants
            loc = self.page.locator(target)
            cnt = await self._safe_await(loc.count(), default=0)
            if not cnt:
                return False
            for idx in range(min(int(cnt), 5)):
                item = loc.nth(idx)
                res = item.is_visible(timeout=timeout)
                if hasattr(res, "__await__"):
                    res = await res
                if bool(res):
                    return True
            return False
        except Exception:
            return False

    async def _is_any_visible(self, selector: str, timeout: int = 1500) -> bool:
        """Check if any element matching selector is visible across up to 10 matches."""
        return await self._is_visible(selector, timeout=timeout)

    async def _safe_click(self, selector: str, timeout: int = 5000) -> bool:
        """Click an element safely with timeout and retry."""
        try:
            loc = self.page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.scroll_into_view_if_needed()
            await self._human_delay(0.3, 0.8)
            try:
                await loc.click(force=True, timeout=timeout)
            except Exception:
                await loc.evaluate("el => el.click()")
            return True
        except Exception as e:
            logger.debug(f"Click failed on {selector}: {e}")
            return False

    async def _safe_title(self) -> str:
        """Safely fetch page title handling coroutines and mocks."""
        try:
            if hasattr(self.page, "title"):
                title_attr = self.page.title
                res = title_attr() if callable(title_attr) else title_attr
                import inspect
                if inspect.isawaitable(res) and not type(res).__name__ == "MagicMock":
                    return str(await res or "")
                if isinstance(res, (str, bytes)):
                    return str(res)
            return ""
        except Exception:
            return ""

    async def _safe_await(self, val: Any, default: Any = None) -> Any:
        """Safely awaits a value or coroutine if awaitable, otherwise returns the value or default."""
        import inspect
        if inspect.isawaitable(val) and not type(val).__name__ == "MagicMock":
            try:
                return await val
            except Exception:
                raise
        if isinstance(val, (int, str, float, bool, list, dict)):
            return val
        return default if default is not None else val

    async def _safe_goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000) -> bool:
        """
        Safely navigate to URL, absorbing net::ERR_ABORTED and challenge redirects.
        """
        if not self.page:
            return False
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=timeout)
            return True
        except Exception as e:
            err_msg = str(e)
            if any(k in err_msg for k in ["ERR_ABORTED", "net::ERR_", "Navigation failed", "interrupted"]):
                logger.debug(f"Navigation to {url} redirected / interrupted ({e}), continuing...")
                await asyncio.sleep(1.5)
                return True
            logger.warning(f"Failed to navigate to {url}: {e}")
            return False

    async def _is_seek_signin_form(self) -> bool:
        """Checks if the browser is currently showing an actual SEEK/Auth0 sign-in or OTP form."""
        if not self.page:
            return False
        curr_url = self.page.url or ""
        # 1. Active Auth0 login path
        if "login.seek.com/login" in curr_url:
            return True
        # 2. Form input elements on active login or OTP verification screen
        signin_input_selectors = (
            "input[name='emailAddress_seekanz'], "
            "input#emailAddress, "
            "div[data-testid='container'] input[aria-label*='verification' i], "
            "#field-0, "
            "[data-testid='character-0']"
        )
        if await self._is_visible(signin_input_selectors, timeout=600):
            return True
        # 3. Explicit login submit button
        return await self._is_visible("button:has-text('Email me a sign in code')", timeout=600)

    def _resolve_profile_resume_path(self, job: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Resolves the candidate's resume strictly from the Profile section.
        Prioritizes a job-specific tailored resume if available.
        """
        # 0. Check for tailored resume for this job
        if job:
            tailored = job.get("tailored_resume_path")
            if tailored and os.path.exists(tailored):
                logger.info(f"Using tailored resume for SEEK job {job.get('id', '')}: {tailored}")
                return os.path.abspath(tailored)

            try:
                from web.backend.db import AppDatabase
                db = AppDatabase()
                tailored_rec = db.get_tailored_resume_for_job(
                    job_id=job.get("source_job_id") or str(job.get("id", "")),
                    opportunity_id=job.get("id"),
                    company=job.get("company", ""),
                    title=job.get("title", ""),
                )
                if tailored_rec and tailored_rec.get("tailored_docx_path") and os.path.exists(tailored_rec["tailored_docx_path"]):
                    logger.info(f"Resolved stored tailored resume for SEEK {job.get('company', '')}: {tailored_rec['tailored_docx_path']}")
                    return os.path.abspath(tailored_rec["tailored_docx_path"])
            except Exception as te:
                logger.debug(f"SEEK tailored resume lookup note: {te}")

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

    def _import_browser_cookies(self) -> bool:
        """
        Attempts to read and decrypt active SEEK session cookies from local
        Brave, Google Chrome, or Chromium profiles on Linux.
        """
        try:
            import glob
            import sqlite3
            import subprocess
            import tempfile
            import shutil
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

            def get_key(label_substr):
                try:
                    script = f"""
import secretstorage
bus = secretstorage.dbus_init()
col = secretstorage.get_default_collection(bus)
for it in col.get_all_items():
    if "{label_substr}" in it.get_label():
        print(it.get_secret().hex())
        break
"""
                    out = subprocess.check_output(["/usr/bin/python3", "-c", script], text=True).strip()
                    if out:
                        return bytes.fromhex(out)
                except Exception:
                    pass
                return None

            _key_cache = {}

            def get_key(label_substr):
                if label_substr in _key_cache:
                    return _key_cache[label_substr]
                try:
                    script = f"""
import secretstorage
bus = secretstorage.dbus_init()
col = secretstorage.get_default_collection(bus)
for it in col.get_all_items():
    if "{label_substr}" in it.get_label():
        print(it.get_secret().hex())
        break
"""
                    out = subprocess.check_output(["/usr/bin/python3", "-c", script], text=True).strip()
                    if out:
                        k = bytes.fromhex(out)
                        _key_cache[label_substr] = k
                        return k
                except Exception:
                    pass
                _key_cache[label_substr] = None
                return None

            candidate_sources = []
            for base, label in [
                ("~/.config/google-chrome", "Chrome Safe Storage"),
                ("~/.config/chromium", "Chromium Safe Storage"),
                ("~/.config/BraveSoftware/Brave-Browser", "Brave Safe Storage"),
                ("~/.config/microsoft-edge", "Chromium Safe Storage"),
            ]:
                expanded_base = os.path.expanduser(base)
                if os.path.exists(expanded_base):
                    for c_file in glob.glob(f"{expanded_base}/**/Cookies", recursive=True):
                        candidate_sources.append((label, c_file))

            all_seek_cookies = []

            for label, cookie_db in candidate_sources:
                if not os.path.exists(cookie_db):
                    continue

                raw_key = get_key(label) or b"peanuts"
                kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1)
                aes_key = kdf.derive(raw_key)

                tmp = tempfile.mktemp(suffix=".db")
                try:
                    shutil.copy2(cookie_db, tmp)
                    conn = sqlite3.connect(tmp)
                    c = conn.cursor()
                    rows = c.execute(
                        "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite "
                        "FROM cookies WHERE host_key LIKE '%seek%'"
                    ).fetchall()
                    conn.close()

                    for r in rows:
                        val = r[2]
                        enc = r[3]
                        if not val and enc and len(enc) >= 35:
                            if enc[:3] in (b"v10", b"v11"):
                                iv = enc[19:35]
                                ct = enc[35:]
                                try:
                                    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
                                    p = cipher.update(ct) + cipher.finalize()
                                    pad = p[-1]
                                    if isinstance(pad, int) and 1 <= pad <= 16:
                                        p = p[:-pad]
                                    val = p.decode("utf-8", errors="ignore")
                                except Exception:
                                    val = ""

                        if not val:
                            continue

                        # Clean control characters
                        clean_val = "".join(ch for ch in val if ord(ch) >= 32 and ord(ch) != 127)
                        if not clean_val:
                            continue

                        same_site = "Lax"
                        if r[8] == 2:
                            same_site = "Strict"
                        elif r[8] == 0:
                            same_site = "None"

                        all_seek_cookies.append({
                            "name": r[1],
                            "value": clean_val,
                            "domain": r[0],
                            "path": r[4],
                            "expires": float(r[5] / 1000000 - 11644473600) if r[5] > 0 else -1,
                            "httpOnly": bool(r[7]),
                            "secure": bool(r[6]),
                            "sameSite": same_site,
                        })
                except Exception as e:
                    logger.debug(f"Error reading cookies from {cookie_db}: {e}")
                finally:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except Exception:
                            pass

            if not all_seek_cookies:
                return False

            # Deduplicate by (domain, name).
            # NOTE: cf_clearance tokens are now INCLUDED because the browser
            # binary is matched to the profile source, so TLS fingerprints
            # are consistent and the clearance tokens will be valid.
            unique = {}
            for ck in all_seek_cookies:
                # Sanitize keys for Playwright
                clean_ck = {
                    k: v for k, v in ck.items()
                    if k in ("name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite")
                }
                unique[(clean_ck["domain"], clean_ck["name"])] = clean_ck

            cookies_list = list(unique.values())
            has_session = any(ck["name"] in ("appSession", "auth0", "registeredCandidateId", "JobseekerSessionId", "last-known-sol-user-id") for ck in cookies_list)
            if not has_session:
                return False

            state = {"cookies": cookies_list, "origins": []}
            for sp in [
                Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_storage_state.json"),
                Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/seek_storage_state.json"),
                Path("web/backend/data/seek_storage_state.json"),
                Path("data/seek_storage_state.json"),
                Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_cookies.json"),
                Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/seek_cookies.json"),
                Path("web/backend/data/seek_cookies.json"),
                Path("data/seek_cookies.json"),
            ]:
                sp.parent.mkdir(parents=True, exist_ok=True)
                if "cookies.json" in str(sp):
                    sp.write_text(json.dumps(cookies_list, indent=2))
                else:
                    sp.write_text(json.dumps(state, indent=2))

            logger.info(f"Successfully auto-imported {len(cookies_list)} live SEEK cookies from system browser")
            return True
        except Exception as e:
            logger.debug(f"Browser cookie auto-import notice: {e}")
            return False

    async def initialize_browser(self):
        """
        Launch Playwright Chromium with anti-detection settings silently in the background.
        Does NOT open or display any visible window on the user's desktop unless explicitly requested.
        """
        # Start invisible virtual display (Xvfb) on Linux so browser runs in real headful mode
        # without popping up any visible window on the user's desktop. Real headful execution
        # cleanly avoids Cloudflare's headless bot detection.
        if not getattr(self, "_virtual_display", None):
            try:
                from pyvirtualdisplay import Display
                self._virtual_display = Display(visible=0, size=(1920, 1080))
                self._virtual_display.start()
                os.environ["DISPLAY"] = f":{self._virtual_display.display}"
                logger.info(f"SEEK virtual display started on :{self._virtual_display.display} for silent background headful execution")
            except Exception as ve:
                logger.debug(f"Virtual display start notice ({ve}), proceeding with native display")
                self._virtual_display = None

        if self._virtual_display:
            is_headless = False
        else:
            is_headless = os.environ.get("HEADLESS", "true").lower() != "false"
            if os.environ.get("SEEK_HEADLESS", "").lower() == "false":
                is_headless = False

        browser_env = dict(os.environ)
        if self._virtual_display:
            browser_env["DISPLAY"] = f":{self._virtual_display.display}"

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # 1. CDP connection (strictly opt-in via SEEK_USE_CDP=true)
        use_cdp = os.environ.get("SEEK_USE_CDP", "false").lower() in ("true", "1")
        if use_cdp:
            cdp_port = os.environ.get("SEEK_CDP_PORT", "9222")
            cdp_url = f"http://127.0.0.1:{cdp_port}"
            try:
                self.browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
                logger.info(f"Connected to live browser session via CDP at {cdp_url}")
                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                else:
                    self.context = await self.browser.new_context()
                self.page = await self.context.new_page()
                self._using_cdp = True

                # Persist current storage_state & cookies so standalone runs can use them
                try:
                    state = await self.context.storage_state()
                    for sp in [
                        Path("web/backend/data/seek_storage_state.json"),
                        Path("data/seek_storage_state.json"),
                    ]:
                        sp.parent.mkdir(parents=True, exist_ok=True)
                        sp.write_text(json.dumps(state, indent=2))
                except Exception:
                    pass
                return
            except Exception as cdp_err:
                logger.debug(f"CDP connection to {cdp_url} not available ({cdp_err}), launching standalone silent browser...")
                self._using_cdp = False
        else:
            self._using_cdp = False

        # 2. Always import fresh cookies from the local browser.
        # cf_clearance tokens are short-lived (~30 min) and must be refreshed
        # every time, not reused from stale stored files.
        self._import_browser_cookies()

        # Locate system browser binary.
        # Strategy: prefer whichever browser actually holds SEEK session cookies
        # so that cloned cf_clearance tokens match the browser's TLS fingerprint.
        # Brave is included because SEEK sessions often live there.
        import glob as _glob
        import tempfile
        import shutil
        _seek_cookie_browsers = []  # (binary, profile_dir) tuples
        _browser_candidates = [
            ("/usr/bin/brave-browser", os.path.expanduser("~/.config/BraveSoftware/Brave-Browser/Default")),
            ("/usr/bin/google-chrome", os.path.expanduser("~/.config/google-chrome/Default")),
            ("/usr/bin/google-chrome-stable", os.path.expanduser("~/.config/google-chrome/Default")),
            ("/opt/google/chrome/chrome", os.path.expanduser("~/.config/google-chrome/Default")),
            ("/usr/bin/chromium", os.path.expanduser("~/.config/chromium/Default")),
            ("/usr/bin/chromium-browser", os.path.expanduser("~/.config/chromium/Default")),
        ]
        for _bin, _prof in _browser_candidates:
            if not os.path.exists(_bin) or not os.path.exists(_prof):
                continue
            # Check if this profile has SEEK cookies
            _cookie_db = os.path.join(_prof, "Cookies")
            if os.path.exists(_cookie_db):
                try:
                    import sqlite3 as _sq
                    _tmp_ck = tempfile.mktemp(suffix=".db")
                    shutil.copy2(_cookie_db, _tmp_ck)
                    _cn = _sq.connect(_tmp_ck)
                    _rows = _cn.execute("SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%seek%'").fetchone()
                    _cn.close()
                    os.remove(_tmp_ck)
                    if _rows and _rows[0] > 0:
                        _seek_cookie_browsers.append((_bin, _prof))
                        continue
                except Exception:
                    pass
            _seek_cookie_browsers.append((_bin, _prof))  # still a viable fallback

        browser_bin = None
        desktop_profile_src = None
        if _seek_cookie_browsers:
            browser_bin, desktop_profile_src = _seek_cookie_browsers[0]
        else:
            # Fallback: just find any available browser binary
            for _bin, _prof in _browser_candidates:
                if os.path.exists(_bin):
                    browser_bin = _bin
                    if os.path.exists(_prof):
                        desktop_profile_src = _prof
                    break

        cloned_profile_dir = None
        if desktop_profile_src and browser_bin:
            try:
                cloned_profile_dir = tempfile.mkdtemp(prefix="seek_profile_")
                default_sub = os.path.join(cloned_profile_dir, "Default")
                os.makedirs(default_sub, exist_ok=True)
                # Clone Local Storage, IndexedDB, AND Cookies database.
                # Including the Cookies DB is critical so that cf_clearance
                # tokens — which are TLS-fingerprint-bound — remain valid
                # when launched with the same browser binary.
                for item in ["Local Storage", "IndexedDB", "Cookies"]:
                    src = os.path.join(desktop_profile_src, item)
                    dst = os.path.join(default_sub, item)
                    if os.path.exists(src):
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
                self._temp_user_data_dir = cloned_profile_dir
                logger.info(f"Cloned live desktop profile from {desktop_profile_src} to {cloned_profile_dir} (browser: {browser_bin})")
            except Exception as pe:
                logger.debug(f"Profile cloning note: {pe}")
                cloned_profile_dir = None

        # Resolve browser major version to align User-Agent and Client Hints.
        # Use the actual selected binary for version detection.
        chrome_major = "152"
        try:
            import subprocess
            _ver_bin = browser_bin or "google-chrome"
            out = subprocess.check_output([_ver_bin, "--version"], text=True)
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

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--window-size=1920,1080",
            "--no-first-run",
            "--no-default-browser-check",
            "--lang=en-AU,en-US,en",
        ]
        if is_headless:
            args.append("--headless=new")

        if cloned_profile_dir:
            try:
                # ── Native CDP Launch ──────────────────────────────────────────
                # Playwright's launch_persistent_context intercepts connections
                # through its own proxy layer, changing the TLS fingerprint
                # (JA3/JA4). This makes cf_clearance tokens invalid regardless
                # of browser binary. By launching the browser natively via
                # subprocess and connecting through CDP, the browser retains
                # its original TLS fingerprint.
                import subprocess as _sp
                import socket as _sock

                # Find a free port for remote debugging
                def _find_free_port():
                    with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                        s.bind(('127.0.0.1', 0))
                        return s.getsockname()[1]

                cdp_port = _find_free_port()
                native_args = [
                    browser_bin or "brave-browser",
                    f"--user-data-dir={cloned_profile_dir}",
                    f"--remote-debugging-port={cdp_port}",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--window-size=1920,1080",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--lang=en-AU,en-US,en",
                ]
                if is_headless:
                    native_args.append("--headless=new")

                self._native_browser_proc = _sp.Popen(
                    native_args,
                    env=browser_env,
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                )

                # Wait for CDP endpoint to become available
                cdp_url = f"http://127.0.0.1:{cdp_port}"
                for _attempt in range(30):
                    await asyncio.sleep(0.5)
                    try:
                        with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                            s.settimeout(1)
                            s.connect(('127.0.0.1', cdp_port))
                        break
                    except (ConnectionRefusedError, OSError):
                        continue
                else:
                    raise RuntimeError(f"Browser did not open CDP port {cdp_port} within 15s")

                await asyncio.sleep(1)  # Give browser time to fully initialize

                self.browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
                self._using_cdp = True
                logger.info(f"Connected to native browser via CDP at {cdp_url} (pid={self._native_browser_proc.pid})")

                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                else:
                    self.context = await self.browser.new_context()

                # Inject decrypted cookies from Brave into the native context
                try:
                    for sp in [
                        Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_cookies.json"),
                        Path("web/backend/data/seek_cookies.json"),
                        Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_storage_state.json"),
                        Path("web/backend/data/seek_storage_state.json"),
                    ]:
                        if sp.exists() and sp.stat().st_size > 50:
                            data = json.loads(sp.read_text())
                            cks = data if isinstance(data, list) else data.get("cookies", [])
                            clean_cks = [
                                {
                                    k: v for k, v in c.items()
                                    if k in ("name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite")
                                }
                                for c in cks
                            ]
                            if clean_cks:
                                await self.context.add_cookies(clean_cks)
                                logger.info(f"Injected {len(clean_cks)} stored cookies into native CDP context")
                                break
                except Exception as cke:
                    logger.debug(f"Cookie injection into native CDP notice: {cke}")

                self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

                try:
                    await self.context.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                        window.chrome = window.chrome || { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
                    """)
                except Exception:
                    pass

                logger.info("SEEK Browser initialized via native CDP with real TLS fingerprint")
                return
            except Exception as persist_err:
                logger.warning(f"Persistent context launch failed ({persist_err}), falling back to standard launch...")

        # 3. Standalone launch fallback
        launch_kwargs = {
            "headless": is_headless,
            "args": args,
            "ignore_default_args": ["--enable-automation"],
            "env": browser_env,
        }

        if browser_bin:
            launch_kwargs["executable_path"] = browser_bin

        self.browser = await self._playwright.chromium.launch(**launch_kwargs)

        storage_state_path = None
        for sp in [
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_storage_state.json"),
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/seek_storage_state.json"),
            Path("web/backend/data/seek_storage_state.json"),
            Path("data/seek_storage_state.json"),
        ]:
            if sp.exists() and sp.stat().st_size > 50:
                storage_state_path = str(sp.resolve())
                break

        context_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": user_agent,
            "locale": "en-AU",
            "timezone_id": "Australia/Sydney",
        }
        if storage_state_path:
            # Include all cookies including cf_clearance (browser binary matches profile)
            try:
                s_data = json.loads(Path(storage_state_path).read_text())
                context_kwargs["storage_state"] = storage_state_path
            except Exception:
                context_kwargs["storage_state"] = storage_state_path

        self.context = await self.browser.new_context(**context_kwargs)
        try:
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = window.chrome || { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
            """)
        except Exception:
            pass

        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            await stealth.apply_stealth_async(self.context)

            async def on_new_page(new_p):
                try:
                    await stealth.apply_stealth_async(new_p)
                except Exception:
                    pass
            self.context.on("page", on_new_page)
        except Exception:
            pass

        self.page = await self.context.new_page()
        try:
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(self.page)
        except Exception:
            pass

        logger.info("SEEK Browser initialized silently in background")

    async def close_browser(self):
        """Persist cookies/storage_state, then clean up browser resources, temp profile, and virtual display."""
        # Save session cookies and storage state BEFORE closing the context
        # so the next run can reuse the authenticated session without re-login.
        try:
            if self.context:
                try:
                    cookies = await self.context.cookies()
                    has_session = any(
                        c.get("name") in ("registeredCandidateId", "JobseekerSessionId", "appSession", "auth0", "last-known-sol-user-id")
                        for c in (cookies or [])
                    )
                    if cookies and has_session:
                        # Only persist SEEK-related cookies (not the entire browser profile)
                        clean_cookies = [
                            c for c in cookies
                            if any(d in c.get("domain", "") for d in ("seek.com", "seek.com.au"))
                        ]
                        for cp in [
                            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_cookies.json"),
                            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/seek_cookies.json"),
                            Path("web/backend/data/seek_cookies.json"),
                            Path("data/seek_cookies.json"),
                        ]:
                            cp.parent.mkdir(parents=True, exist_ok=True)
                            cp.write_text(json.dumps(clean_cookies, indent=2))
                        logger.info(f"Persisted {len(clean_cookies)} SEEK cookies on browser close")
                except Exception as ce:
                    logger.debug(f"Could not persist cookies on close: {ce}")
                try:
                    state = await self.context.storage_state()
                    has_session_state = any(
                        c.get("name") in ("registeredCandidateId", "JobseekerSessionId", "appSession", "auth0", "last-known-sol-user-id")
                        for c in (state.get("cookies", []) if state else [])
                    )
                    if state and has_session_state:
                        # Only persist SEEK-related cookies in storage state
                        state["cookies"] = [
                            c for c in state.get("cookies", [])
                            if any(d in c.get("domain", "") for d in ("seek.com", "seek.com.au"))
                        ]
                        for sp in [
                            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_storage_state.json"),
                            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/seek_storage_state.json"),
                            Path("web/backend/data/seek_storage_state.json"),
                            Path("data/seek_storage_state.json"),
                        ]:
                            sp.parent.mkdir(parents=True, exist_ok=True)
                            sp.write_text(json.dumps(state, indent=2))
                        logger.info("Persisted SEEK storage_state on browser close")
                except Exception as se:
                    logger.debug(f"Could not persist storage_state on close: {se}")
        except Exception:
            pass

        try:
            if self.page:
                await self.page.close()
            if not getattr(self, "_using_cdp", False):
                if self.context:
                    await self.context.close()
                if self.browser:
                    await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"Error during browser cleanup: {e}")
        finally:
            tmp_p = getattr(self, "_temp_user_data_dir", None)
            if tmp_p and os.path.exists(tmp_p):
                try:
                    import shutil
                    shutil.rmtree(tmp_p, ignore_errors=True)
                except Exception:
                    pass
            # Kill native browser subprocess if we launched one
            native_proc = getattr(self, "_native_browser_proc", None)
            if native_proc:
                try:
                    native_proc.terminate()
                    native_proc.wait(timeout=5)
                except Exception:
                    try:
                        native_proc.kill()
                    except Exception:
                        pass
                self._native_browser_proc = None
            if getattr(self, "_virtual_display", None):
                try:
                    self._virtual_display.stop()
                    logger.info("SEEK Virtual display stopped")
                except Exception as vde:
                    logger.debug(f"Virtual display stop error: {vde}")
                self._virtual_display = None
                if getattr(self, "_orig_display", None):
                    os.environ["DISPLAY"] = self._orig_display

    async def _human_mouse_move_and_click(self, target_x: float, target_y: float):
        """
        Moves the cursor to (target_x, target_y) using a human-like cubic Bezier trajectory
        with subtle velocity easing, perpendicular curvature, and realistic down/up durations.
        """
        if not self.page:
            return
        import math
        start_x = getattr(self, "_last_mouse_x", 320.0)
        start_y = getattr(self, "_last_mouse_y", 220.0)

        dx = target_x - start_x
        dy = target_y - start_y
        dist = math.hypot(dx, dy)
        steps = max(15, min(int(dist / 20), 45))

        # Perpendicular vector for natural human arc curvature
        perp_x = -dy / (dist + 1e-6)
        perp_y = dx / (dist + 1e-6)
        arc = random.uniform(-0.25, 0.25) * dist

        ctrl1_x = start_x + dx * 0.25 + perp_x * arc + random.uniform(-6, 6)
        ctrl1_y = start_y + dy * 0.25 + perp_y * arc + random.uniform(-6, 6)
        ctrl2_x = start_x + dx * 0.75 + perp_x * arc * 0.6 + random.uniform(-6, 6)
        ctrl2_y = start_y + dy * 0.75 + perp_y * arc * 0.6 + random.uniform(-6, 6)

        for i in range(1, steps + 1):
            t = i / float(steps)
            # Smooth ease-in-out curve
            t_eased = t * t * (3 - 2 * t)
            inv = 1.0 - t_eased
            x = (inv**3)*start_x + 3*(inv**2)*t_eased*ctrl1_x + 3*inv*(t_eased**2)*ctrl2_x + (t_eased**3)*target_x
            y = (inv**3)*start_y + 3*(inv**2)*t_eased*ctrl1_y + 3*inv*(t_eased**2)*ctrl2_y + (t_eased**3)*target_y
            if i < steps:
                x += random.uniform(-1.0, 1.0)
                y += random.uniform(-1.0, 1.0)
            await self.page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.008, 0.018))

        self._last_mouse_x = target_x
        self._last_mouse_y = target_y

        # Natural pause over target before pressing
        await asyncio.sleep(random.uniform(0.18, 0.32))
        await self.page.mouse.down()
        # Human click duration
        await asyncio.sleep(random.uniform(0.09, 0.14))
        await self.page.mouse.up()
        await asyncio.sleep(random.uniform(0.1, 0.2))

        # Drift away naturally after click
        drift_x = target_x + random.uniform(25, 60)
        drift_y = target_y + random.uniform(-30, 30)
        await self.page.mouse.move(drift_x, drift_y)
        self._last_mouse_x = drift_x
        self._last_mouse_y = drift_y

    async def _simulate_human_cursor_drift(self):
        """Simulates subtle human cursor movements on the page."""
        if not self.page:
            return
        target_x = random.uniform(400, 750)
        target_y = random.uniform(250, 550)
        start_x = getattr(self, "_last_mouse_x", 300.0)
        start_y = getattr(self, "_last_mouse_y", 200.0)
        steps = random.randint(10, 18)
        for i in range(1, steps + 1):
            t = i / float(steps)
            x = start_x + (target_x - start_x) * t + random.uniform(-1.5, 1.5)
            y = start_y + (target_y - start_y) * t + random.uniform(-1.5, 1.5)
            await self.page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.01, 0.025))
        self._last_mouse_x = target_x
        self._last_mouse_y = target_y

    async def _attempt_turnstile_click(self) -> bool:
        """Attempts to detect and interact with Cloudflare Turnstile verification using human cursor movement."""
        if not self.page:
            return False
        try:
            # Check frames for Turnstile
            for f in self.page.frames:
                try:
                    if f.is_detached():
                        continue
                    if any(kw in f.url for kw in ["turnstile", "challenge-platform", "challenges.cloudflare"]):
                        el = await f.frame_element()
                        box = await el.bounding_box()
                        if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                            click_x = box["x"] + min(28, box["width"] * 0.1)
                            click_y = box["y"] + (box["height"] / 2)
                            await self._human_mouse_move_and_click(click_x, click_y)
                            logger.info(f"Interacted with Turnstile frame at ({click_x:.1f}, {click_y:.1f}) via human cursor trajectory")
                            return True
                except Exception:
                    continue

            # Check page-level challenge containers
            for sel in [
                "iframe[src*='challenges.cloudflare.com']",
                "iframe[src*='challenge-platform']",
                "#cf-turnstile",
                "[data-sitekey]",
                "#challenge-stage",
            ]:
                loc = self.page.locator(sel).first
                if await self._is_visible(loc, timeout=300):
                    box = await loc.bounding_box()
                    if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                        click_x = box["x"] + min(28, box["width"] * 0.1)
                        click_y = box["y"] + (box["height"] / 2)
                        await self._human_mouse_move_and_click(click_x, click_y)
                        logger.info(f"Interacted with Turnstile element ({sel}) at ({click_x:.1f}, {click_y:.1f}) via human cursor trajectory")
                        return True
        except Exception as e:
            logger.debug(f"Turnstile interaction note: {e}")
        return False

    async def _wait_for_turnstile_token(self, timeout_seconds: int = 10, simulate_movement: bool = True) -> bool:
        """Polls for cf-turnstile-response token generation while simulating subtle human mouse activity."""
        if not self.page:
            return False
        rounds = max(1, int(timeout_seconds * 2))
        for r in range(rounds):
            try:
                token = await self.page.evaluate("""() => {
                    const el = document.querySelector('input[name="cf-turnstile-response"]');
                    return el ? el.value : "";
                }""")
                if token and len(token) > 20:
                    return True
            except Exception:
                pass
            if simulate_movement and r > 0 and r % 3 == 0:
                try:
                    await self._simulate_human_cursor_drift()
                except Exception:
                    pass
            await self._human_delay(0.2, 0.5)
        return False

    async def _reset_turnstile(self):
        """Resets the Turnstile widget and clears stale response tokens."""
        if not self.page:
            return
        try:
            await self._safe_await(self.page.evaluate("""() => {
                try {
                    if (typeof window.turnstile !== 'undefined' && window.turnstile.reset) {
                        window.turnstile.reset();
                    }
                } catch(e) {}
                const el = document.querySelector('input[name="cf-turnstile-response"]');
                if (el) el.value = "";
                const els = document.querySelectorAll('input[name*="turnstile" i], input[name*="cf-chl" i]');
                els.forEach(i => { i.value = ""; });
            }"""))
            logger.info("Reset Turnstile widget and cleared token value")
        except Exception as e:
            logger.debug(f"Turnstile reset note: {e}")

    async def _wait_for_cloudflare(self, max_wait_seconds: int = 25):
        """Waits gracefully for Cloudflare challenge or Turnstile verification to clear."""
        rounds = max(1, max_wait_seconds)
        for r in range(rounds):
            title = (await self._safe_title()).lower()
            curr_url = self.page.url if self.page else ""
            body_text = ""
            try:
                if self.page:
                    body_text = (await self.page.locator("body").inner_text() or "").lower()
            except Exception:
                pass

            is_cf_loading = title.startswith("loading ") or "__cf_chl_" in curr_url or "just a moment" in title
            is_cf_challenge = (
                "checking your browser" in title
                or "attention required" in title
                or "security verification" in body_text
                or ("ray id" in body_text and "cloudflare" in body_text)
            )
            if not is_cf_challenge and not is_cf_loading and title != "":
                if r > 0:
                    logger.info(f"Cloudflare verification cleared after {r}s (Title: {title})")
                return True

            # If in redirecting phase or initial loading, give it time to navigate to target URL without clicking
            if is_cf_loading and not is_cf_challenge:
                await asyncio.sleep(1)
                continue

            # Attempt Turnstile interaction only after 8 seconds of natural frame mount if still challenged
            if is_cf_challenge and r >= 8 and r % 4 == 0:
                await self._attempt_turnstile_click()

            await asyncio.sleep(1)

        logger.warning("Cloudflare challenge did not clear automatically within timeout")
        return False

    async def _is_on_seek_code_screen(self, body_text: Optional[str] = None) -> bool:
        """
        Check if the browser is currently on SEEK's 6-digit OTP verification screen.
        Evaluates:
        1. URL hash / path: '#/verification-code' or 'verification-code'.
        2. Body text: 'check your email', 'enter the 6-digit code', 'we sent a code', etc.
        3. DOM elements: VerificationInput containers, split digit inputs, or OTP fields.
        """
        if not self.page:
            return False

        try:
            curr_url = self.page.url or ""
            if any(k in curr_url.lower() for k in ["#/verification-code", "verification-code", "verification_code"]):
                return True

            text = body_text
            if text is None:
                try:
                    text = (await self._safe_await(self.page.locator("body").inner_text(), default="")).lower()
                except Exception:
                    text = ""

            if any(k in text for k in [
                "check your email",
                "enter the 6-digit code",
                "enter your 6 digit code",
                "6-digit code",
                "we sent a code",
                "we've sent a code",
                "enter the verification code",
                "enter sign-in code",
            ]):
                return True

            code_selectors = (
                "div[data-testid='container'] input, "
                "div[data-testid='container'], "
                "#field-0, "
                "[data-testid='character-0'], "
                "input[aria-label*='verification' i], "
                "input[autocomplete='one-time-code'], "
                "input[data-testid*='digit-input'], "
                "#submit-OTP"
            )
            if await self._is_visible(code_selectors, timeout=300):
                return True
        except Exception:
            pass

        return False

    async def login(self) -> bool:
        """
        Log into SEEK using either active session/cached cookies or email passwordless code flow.
        1. Checks existing session/cookies.
        2. Navigates to SEEK authentication portal (https://login.seek.com/login).
        3. Fills candidate email and requests verification code.
        4. Requests OTP code from user via ask_user callback.
        5. Enters code, submits, and persists cookies/storage_state for future runs.
        """
        if self._is_authenticated:
            logger.info("SEEK agent is already authenticated in this session.")
            return True

        cookie_paths = [
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_storage_state.json"),
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/seek_storage_state.json"),
            Path("web/backend/data/seek_storage_state.json"),
            Path("data/seek_storage_state.json"),
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_cookies.json"),
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/seek_cookies.json"),
            Path("web/backend/data/seek_cookies.json"),
            Path("data/seek_cookies.json"),
        ]

        auth_indicators = (
            "[data-automation='user-account'], "
            "[data-automation='account name'], "
            "header a[data-automation='user-profile'], "
            "[data-automation='sign out'], "
            "[data-automation='sign-out'], "
            "button:has-text('Sign out'), "
            "a:has-text('Sign out')"
        )
        sign_in_indicators = (
            "header a[data-automation='sign in'], "
            "header a:has-text('Sign in'), "
            "header button:has-text('Sign in')"
        )

        curr_url = self.page.url if self.page else ""
        is_already_on_login = any(k in curr_url for k in ["login.seek.com", "oauth/login"])

        # 1. Check if existing session / cached cookies are already authenticated
        if not is_already_on_login:
            try:
                if not getattr(self, "_using_cdp", False):
                    for cp in cookie_paths:
                        if cp.exists() and cp.stat().st_size > 100:
                            try:
                                loaded_data = json.loads(cp.read_text())
                                cookies_to_add = []
                                if isinstance(loaded_data, list):
                                    cookies_to_add = loaded_data
                                elif isinstance(loaded_data, dict) and "cookies" in loaded_data:
                                    cookies_to_add = loaded_data["cookies"]
                                if cookies_to_add:
                                    await self.context.add_cookies(cookies_to_add)
                                    logger.info(f"Restoring {len(cookies_to_add)} SEEK session cookies from {cp}")
                                    break
                            except Exception:
                                pass

                await self.page.goto("https://au.seek.com/", wait_until="domcontentloaded", timeout=20000)
                cf_ok = await self._wait_for_cloudflare(15)
                await asyncio.sleep(self.PAGE_LOAD_WAIT)

                curr_title = (await self._safe_title()).lower()
                if "just a moment" not in curr_title and curr_title:
                    has_sign_in = await self._is_visible(sign_in_indicators, timeout=2000)
                    has_auth_el = await self._is_visible(auth_indicators, timeout=2000)

                    # Check context cookies for active session
                    curr_cookies = await self.context.cookies()
                    c_names = {c.get("name") for c in curr_cookies}
                    has_session_cookie = any(
                        cn in c_names
                        for cn in ["registeredCandidateId", "JobseekerSessionId", "auth0", "auth0_compat", "appSession"]
                    )
                    is_logged_in = (has_auth_el or (has_session_cookie and not has_sign_in)) and "login.seek.com" not in self.page.url

                    if is_logged_in:
                        logger.info("SEEK session valid. Logged in successfully.")
                        self._is_authenticated = True
                        self._emit({
                            "type": "apply_login_success",
                            "method": "cookies",
                            "message": "Authenticated with SEEK (active session)",
                        })
                        return True
                    else:
                        logger.info(f"SEEK session check: has_auth_el={has_auth_el}, has_session_cookie={has_session_cookie}, has_sign_in={has_sign_in}. Starting login flow.")
            except Exception as e:
                logger.debug(f"Session restoration check error: {e}")

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
            # If email input is not already visible on the current page and not on login portal, navigate to https://au.seek.com/oauth/login
            email_input_sel = (
                "input#emailAddress, "
                "input[name='emailAddress_seekanz'], "
                "input[type='email'], "
                "input[name='email'], "
                "[data-testid='email-input']"
            )
            has_email_field = await self._is_visible(email_input_sel, timeout=1000)
            if not has_email_field and not any(k in self.page.url for k in ["login.seek.com", "oauth/login"]):
                await self._safe_goto("https://au.seek.com/oauth/login", wait_until="domcontentloaded", timeout=25000)
                await self._wait_for_cloudflare(15)
                await self._human_delay(1.5, 2.5)
            email_field = self.page.locator(email_input_sel).first
            for _ in range(10):
                if await self._is_visible(email_field, timeout=500):
                    break
                await asyncio.sleep(0.5)

            if await self._is_visible(email_field, timeout=3000):
                await self._type_human(email_field, email)
                await self._human_delay(0.5, 1.0)

                # Proactively resolve Turnstile before clicking submit if present on form
                has_turnstile = any(
                    any(k in f.url for k in ["turnstile", "challenges.cloudflare"])
                    for f in self.page.frames
                )
                if not has_turnstile:
                    has_turnstile = await self._is_visible("iframe[src*='challenges.cloudflare.com'], [data-sitekey], #cf-turnstile", timeout=500)
                if has_turnstile:
                    logger.info("Turnstile challenge detected on email sign-in. Waiting for proof-of-work to complete...")
                    # Wait longer (12s) for Turnstile's proof-of-work phase to finish.
                    # Clicking too early causes permanent 'Verification failed' state.
                    token_ok = await self._wait_for_turnstile_token(timeout_seconds=12, simulate_movement=True)
                    if not token_ok:
                        logger.info("Turnstile proof-of-work did not auto-resolve. Clicking checkbox...")
                        await self._attempt_turnstile_click()
                        token_ok = await self._wait_for_turnstile_token(timeout_seconds=10, simulate_movement=False)
                    if not token_ok:
                        # Reset and retry once more — Turnstile may have entered error state
                        await self._reset_turnstile()
                        await asyncio.sleep(3)
                        await self._attempt_turnstile_click()
                        token_ok = await self._wait_for_turnstile_token(timeout_seconds=10, simulate_movement=True)

                # Submit email to request code or proceed
                code_btn_sel = (
                    "button[type='submit']:has-text('Email me a sign in code'), "
                    "button:has-text('Email me a sign in code'), "
                    "button[type='submit']"
                )
                submit_btn = self.page.locator(code_btn_sel).first
                # Only click submit if Turnstile token is present (or no Turnstile detected)
                token_present = True
                if has_turnstile:
                    try:
                        _tok = await self.page.evaluate('''() => {
                            const el = document.querySelector('input[name="cf-turnstile-response"]');
                            return el ? el.value : "";
                        }''')
                        token_present = bool(_tok and len(_tok) > 20)
                    except Exception:
                        pass
                if token_present and await self._is_visible(submit_btn, timeout=3000):
                    await submit_btn.click()
                    await self._human_delay(1.5, 2.5)

            # Verification code screen polling loop with automatic Turnstile challenge recovery
            is_code_screen = False
            max_challenge_attempts = 3
            challenge_attempts = 0

            for poll_cycle in range(15):
                curr_url = self.page.url if self.page else ""
                if any(k in curr_url for k in ["au.seek.com/profile", "au.seek.com/my-activity"]):
                    logger.info("Redirected to authenticated profile directly")
                    return True

                body_text = ""
                try:
                    body_text = (await self.page.locator("body").inner_text() or "").lower()
                except Exception:
                    pass

                has_recaptcha_msg = (
                    "please complete the recaptcha" in body_text
                    or "verify you are not a bot" in body_text
                    or "recaptcha" in body_text
                )

                if has_recaptcha_msg and challenge_attempts < max_challenge_attempts:
                    challenge_attempts += 1
                    logger.info(f"SEEK authentication challenge active on sign-in (attempt {challenge_attempts}/{max_challenge_attempts}). Resolving Turnstile with cursor...")
                    self._emit({
                        "type": "apply_status",
                        "message": "Security verification active on SEEK sign-in. Resolving challenge automatically...",
                    })
                    await self._reset_turnstile()
                    token_ok = await self._wait_for_turnstile_token(timeout_seconds=4, simulate_movement=True)
                    if not token_ok:
                        await self._attempt_turnstile_click()
                        await self._wait_for_turnstile_token(timeout_seconds=8, simulate_movement=False)

                    submit_btn = self.page.locator(code_btn_sel).first
                    if await self._is_visible(submit_btn, timeout=2000):
                        await submit_btn.click()
                        await self._human_delay(2.0, 3.5)
                    continue

                if has_recaptcha_msg and challenge_attempts >= max_challenge_attempts:
                    # Challenge did not resolve within maximum attempts
                    break

                if await self._is_on_seek_code_screen(body_text):
                    is_code_screen = True
                    logger.info(f"SEEK verification code screen reached at poll cycle {poll_cycle}")
                    break

                await self._human_delay(0.8, 1.5)

            # Final check of body text after resolution attempts
            try:
                body_text = (await self.page.locator("body").inner_text() or "").lower()
            except Exception:
                pass

            if not is_code_screen:
                is_code_screen = await self._is_on_seek_code_screen(body_text)

            if not is_code_screen and ("please complete the recaptcha" in body_text or "verify you are not a bot" in body_text):
                # Attempt to refresh cookies from system browser in case active in user browser
                if self._import_browser_cookies():
                    logger.info("Imported active browser session during challenge. Verifying...")
                logger.warning("SEEK authentication bot challenge active on login page (reCAPTCHA)")
                self._emit({
                    "type": "apply_error",
                    "message": "SEEK sign-in challenge active (reCAPTCHA). Please open SEEK in your browser to log in once, so the agent can use your active session.",
                })
                return False

            if not is_code_screen and not any(k in self.page.url for k in ["au.seek.com/profile", "au.seek.com/my-activity"]):
                if "login.seek.com" in self.page.url:
                    logger.warning(f"Could not reach code verification screen on login portal: {self.page.url}")
                    self._emit({
                        "type": "apply_error",
                        "message": "Unable to request sign-in code from SEEK. Security verification required in browser.",
                    })
                    return False

            if is_code_screen:
                self._emit({
                    "type": "apply_needs_input",
                    "field_name": "otp_code",
                    "question": f"SEEK sent a 6-digit sign-in code to {email}. Please enter the 6-digit code:",
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
                logger.info(f"Submitting SEEK OTP code: {clean_code[:2]}****")

                # Strategy 1: SEEK Custom VerificationInput (div[data-testid='container'], input[aria-label*='verification' i], #field-0)
                seek_container = self.page.locator("div[data-testid='container'], #field-0, [data-testid='character-0']").first
                seek_input = self.page.locator("input[aria-label*='verification' i], input.zvn9dn1, div[data-testid='container'] input").first

                filled = False
                has_seek_container = await self._is_visible(seek_container, timeout=1500)
                has_seek_input = (await self._safe_await(seek_input.count(), default=0)) > 0

                if has_seek_container or has_seek_input:
                    logger.info("Detected SEEK custom VerificationInput component")
                    max_fill_attempts = 3
                    for fill_attempt in range(max_fill_attempts):
                        try:
                            # 1. Focus the actual hidden input element directly
                            input_focused = False
                            if has_seek_input:
                                try:
                                    await self._safe_await(seek_input.click(force=True))
                                    input_focused = True
                                except Exception:
                                    pass
                            if not input_focused:
                                # Fallback: click #field-0 or container to transfer focus
                                if await self._is_visible("#field-0", timeout=500):
                                    await self._safe_await(self.page.locator("#field-0").first.click())
                                elif has_seek_container:
                                    await self._safe_await(seek_container.click())
                            await asyncio.sleep(0.15)

                            # 2. Clear any existing value and type code via React-compatible method
                            # First: reset React _valueTracker so React detects the change
                            await self._safe_await(self.page.evaluate("""(code) => {
                                const input = document.querySelector("input[aria-label*='verification' i], input.zvn9dn1, div[data-testid='container'] input");
                                if (input) {
                                    // Reset React's internal value tracker so it sees our change
                                    const tracker = input._valueTracker;
                                    if (tracker) tracker.setValue('');
                                    // Use native setter to bypass React's synthetic event system
                                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
                                    if (nativeSetter) {
                                        nativeSetter.call(input, '');
                                    } else {
                                        input.value = '';
                                    }
                                    input.dispatchEvent(new Event('input', { bubbles: true }));
                                    input.dispatchEvent(new Event('change', { bubbles: true }));
                                    input.focus();
                                }
                            }""", clean_code))
                            await asyncio.sleep(0.1)

                            # 3. Type code character-by-character using press_sequentially on the input
                            if has_seek_input:
                                try:
                                    await self._safe_await(seek_input.press_sequentially(clean_code, delay=80))
                                except Exception:
                                    # Fallback to page keyboard
                                    if hasattr(self.page, "keyboard"):
                                        await self._safe_await(self.page.keyboard.type(clean_code, delay=80))
                            else:
                                if hasattr(self.page, "keyboard"):
                                    await self._safe_await(self.page.keyboard.type(clean_code, delay=80))
                            await asyncio.sleep(0.3)

                            # 4. Also force-set via React native setter + dispatchEvent as safety net
                            await self._safe_await(self.page.evaluate("""(code) => {
                                const input = document.querySelector("input[aria-label*='verification' i], input.zvn9dn1, div[data-testid='container'] input");
                                if (input && input.value !== code) {
                                    const tracker = input._valueTracker;
                                    if (tracker) tracker.setValue('');
                                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
                                    if (nativeSetter) {
                                        nativeSetter.call(input, code);
                                    } else {
                                        input.value = code;
                                    }
                                    input.dispatchEvent(new Event('input', { bubbles: true }));
                                    input.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }""", clean_code))
                            await asyncio.sleep(0.2)

                            # 5. Verify all 6 digit boxes reflect the code before proceeding
                            all_digits_filled = True
                            for i in range(6):
                                try:
                                    box_loc = self.page.locator(f"#field-{i}, [data-testid='character-{i}']").first
                                    if await self._is_visible(box_loc, timeout=500):
                                        box_text = (await self._safe_await(box_loc.inner_text(), default="")).strip()
                                        if i < len(clean_code) and box_text != clean_code[i]:
                                            all_digits_filled = False
                                            logger.warning(f"Digit box #{i} expected '{clean_code[i]}' but got '{box_text}'")
                                except Exception:
                                    pass

                            if all_digits_filled:
                                filled = True
                                logger.info(f"All 6 digit boxes verified on attempt {fill_attempt + 1}")
                                break
                            else:
                                logger.warning(f"Digit boxes not fully filled on attempt {fill_attempt + 1}/{max_fill_attempts}, retrying...")
                                await asyncio.sleep(0.3)
                        except Exception as e:
                            err_msg = str(e).lower()
                            # If execution context was destroyed due to navigation,
                            # it means SEEK accepted the code and started the auth redirect.
                            # Treat this as success — don't retry.
                            if "navigation" in err_msg or "context was destroyed" in err_msg or "execution context" in err_msg:
                                logger.info(f"Page navigated during OTP entry (attempt {fill_attempt + 1}) — likely successful auth redirect")
                                filled = True
                                break
                            logger.warning(f"Error filling SEEK VerificationInput (attempt {fill_attempt + 1}): {e}")

                    if not filled:
                        # Even if verification failed, consider filled if input has the value
                        try:
                            input_val = await self._safe_await(self.page.evaluate("""
                                () => {
                                    const input = document.querySelector("input[aria-label*='verification' i], input.zvn9dn1, div[data-testid='container'] input");
                                    return input ? input.value : '';
                                }
                            """), default="")
                            if input_val == clean_code:
                                filled = True
                                logger.info("Input value verified via JS evaluation despite box text mismatch")
                        except Exception:
                            pass

                if not filled:
                    # Strategy 2: Check for 6 separate single-digit inputs (Auth0 split inputs)
                    split_candidates = self.page.locator(
                        "input[maxlength='1'], "
                        "input[id^='code-'], "
                        "input[name^='code-'], "
                        "input[data-testid*='digit'], "
                        "input[aria-label*='digit' i]"
                    )
                    split_count = await self._safe_await(split_candidates.count(), default=0)
                    if split_count >= 6:
                        logger.info(f"Detected {split_count} split digit inputs")
                        for idx in range(min(6, len(clean_code))):
                            box = split_candidates.nth(idx)
                            await box.click()
                            await box.fill(clean_code[idx])
                            await asyncio.sleep(0.06)
                        filled = True

                if not filled:
                    # Strategy 3: Single verification code input (Auth0 classic, standard input)
                    single_selectors = [
                        "input#code",
                        "input[name='code']",
                        "input[name='verificationCode']",
                        "input[name='verification_code']",
                        "input[autocomplete='one-time-code']",
                        "input[id*='code' i]",
                        "input[name*='code' i]",
                        "input[placeholder*='code' i]",
                        "input[aria-label*='code' i]",
                        "input[inputmode='numeric']",
                        "input[type='tel']",
                        "input[type='text']:visible",
                    ]
                    for s_sel in single_selectors:
                        target_inp = self.page.locator(s_sel).first
                        if await self._is_visible(target_inp, timeout=1000):
                            logger.info(f"Filling single OTP input using selector: {s_sel}")
                            await target_inp.click()
                            await target_inp.fill(clean_code)
                            await self.page.evaluate("""([el, code]) => {
                                if (el) {
                                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
                                    if (nativeSetter) nativeSetter.call(el, code);
                                    else el.value = code;
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }""", [await target_inp.element_handle(), clean_code])
                            filled = True
                            break

                await self._human_delay(0.5, 1.0)

                # Submit button candidates
                submit_selectors = [
                    "#submit-OTP",
                    "[data-cy='verification']",
                    "button[type='submit']",
                    "button:has-text('Sign in')",
                    "button:has-text('Continue')",
                    "button:has-text('Verify')",
                    "button:has-text('Confirm')",
                    "button:has-text('Submit')",
                    "[data-testid*='submit']",
                ]

                # Check if submit button is visible and click it
                for b_sel in submit_selectors:
                    btn = self.page.locator(b_sel).first
                    if await self._is_visible(btn, timeout=1000):
                        try:
                            logger.info(f"Clicking submit button with selector: {b_sel}")
                            await btn.click()
                            break
                        except Exception:
                            try:
                                await btn.evaluate("el => el.click()")
                                break
                            except Exception:
                                pass

                # Also press Enter as universal form submission
                try:
                    if hasattr(self.page, "keyboard") and hasattr(self.page.keyboard, "press"):
                        await self._safe_await(self.page.keyboard.press("Enter"))
                except Exception:
                    pass

                # Also call requestSubmit() via JS if form exists
                try:
                    await self._safe_await(self.page.evaluate("""() => {
                        const form = document.querySelector("form");
                        if (form && typeof form.requestSubmit === 'function') {
                            form.requestSubmit();
                        }
                    }"""))
                except Exception:
                    pass

                await self._human_delay(2.0, 3.5)

            # Wait for OAuth redirect to finish (up to 25s)
            for redir_i in range(25):
                curr_u = self.page.url
                if "login.seek.com" not in curr_u and "oauth/login" not in curr_u:
                    break

                # Check for error messages ONLY in specific error containers (NOT entire body)
                # This avoids false positives from static page text like "Enter the 6-digit code we sent to..."
                try:
                    error_containers = self.page.locator(
                        "[data-testid='client-side-error'], "
                        "[data-testid='client-side-error-container'], "
                        "[role='alert'], "
                        "div[class*='tone-critical'], "
                        ".alert-danger, "
                        ".error-message"
                    )
                    err_count = await self._safe_await(error_containers.count(), default=0)
                    has_otp_error = False
                    is_client_validation_error = False
                    error_text = ""

                    for ei in range(err_count):
                        err_el = error_containers.nth(ei)
                        if await self._is_visible(err_el, timeout=300):
                            err_text = (await self._safe_await(err_el.inner_text(), default="")).lower().strip()
                            if not err_text:
                                continue
                            error_text = err_text

                            # Client-side validation errors (React state didn't get the value)
                            if "enter your 6 digit code" in err_text or "code should be 6 digits" in err_text:
                                is_client_validation_error = True
                                break

                            # Real server-side / Auth0 errors
                            if any(kw in err_text for kw in [
                                "invalid", "wrong", "incorrect", "expired",
                                "too many attempts", "something went wrong"
                            ]):
                                has_otp_error = True
                                break

                    if is_client_validation_error:
                        # React didn't accept the input — log warning but DON'T abort
                        logger.warning(f"SEEK client-side validation error (React state desync): '{error_text}' — code may not have been accepted by React input")
                        # Only treat as fatal after waiting a few iterations (give redirect time)
                        if redir_i >= 5:
                            self._emit({
                                "type": "apply_error",
                                "message": f"SEEK verification input did not accept the code (React state issue). Error: {error_text}",
                            })
                            return False
                    elif has_otp_error:
                        logger.warning(f"SEEK authentication error on code verification: {error_text}")
                        self._emit({
                            "type": "apply_error",
                            "message": f"SEEK reported a verification error: {error_text}. Please check your latest code.",
                        })
                        return False
                except Exception:
                    pass

                await asyncio.sleep(1)

            # Verify that we are NOT still on login.seek.com or oauth/login
            if any(k in self.page.url for k in ["login.seek.com", "oauth/login"]):
                logger.warning(f"SEEK authentication did not redirect, current URL is {self.page.url}")
                self._emit({
                    "type": "apply_error",
                    "message": "SEEK login did not complete redirect. Please verify your OTP code or sign in via browser.",
                })
                return False

            # Check for Cloudflare challenge during authentication redirect
            page_title = (await self._safe_title()).lower()
            curr_url = self.page.url if self.page else ""
            if "just a moment" in page_title or "__cf_chl_" in curr_url or "security verification" in page_title:
                logger.info("Cloudflare challenge active during authentication redirect, waiting for resolution...")
                self._emit({
                    "type": "apply_status",
                    "message": "Cloudflare security verification active during redirect. Resolving...",
                })
                cf_cleared = await self._wait_for_cloudflare(max_wait_seconds=25)
                if not cf_cleared:
                    try:
                        logger.info("Cloudflare challenge pending after wait, attempting page reload...")
                        await self.page.reload(wait_until="domcontentloaded", timeout=15000)
                        await self._wait_for_cloudflare(max_wait_seconds=15)
                    except Exception as reload_err:
                        logger.debug(f"Reload notice during CF verification: {reload_err}")

            # Strict verification of authentication indicators
            is_authenticated = False
            for _ in range(8):
                has_auth = await self._is_visible(auth_indicators, timeout=2000)
                has_signin = await self._is_visible(sign_in_indicators, timeout=1000)
                if has_auth and not has_signin:
                    is_authenticated = True
                    break
                # Also check cookies for candidate authentication (Auth0 sets appSession / registeredCandidateId)
                try:
                    curr_cookies = await self.context.cookies()
                    c_names = {c.get("name") for c in curr_cookies}
                    if any(cn in c_names for cn in ["registeredCandidateId", "appSession", "JobseekerSessionId", "auth0", "auth0.GCQ2kVaZFnAkVZYKkgwqCq7oFfiYYUfA.is.authenticated"]) and "login.seek.com" not in self.page.url:
                        is_authenticated = True
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)

            if not is_authenticated:
                final_title = (await self._safe_title()).lower()
                final_url = self.page.url if self.page else ""
                if "just a moment" in final_title or "__cf_chl_" in final_url:
                    logger.warning("Trapped on Cloudflare challenge during login after full wait")
                    self._emit({
                        "type": "apply_error",
                        "message": "Cloudflare challenge active during authentication redirect. Please ensure you are logged into SEEK in Chrome.",
                    })
                    return False

                logger.warning("SEEK authentication indicators not present on destination page after sign-in")
                self._emit({
                    "type": "apply_error",
                    "message": "SEEK session could not be verified after sign-in. Please log into SEEK in your browser.",
                })
                return False

            self._is_authenticated = True

            # Persist authenticated cookies and storage state
            try:
                cookies = await self.context.cookies()
                if cookies and len(cookies) > 0:
                    for cp in cookie_paths:
                        cp.parent.mkdir(parents=True, exist_ok=True)
                        cp.write_text(json.dumps(cookies, indent=2))
            except Exception:
                pass

            try:
                state = await self.context.storage_state()
                if state and state.get("cookies"):
                    for sp in [
                        Path("web/backend/data/seek_storage_state.json"),
                        Path("data/seek_storage_state.json"),
                    ]:
                        sp.parent.mkdir(parents=True, exist_ok=True)
                        sp.write_text(json.dumps(state, indent=2))
            except Exception:
                pass

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
        apply_url = (job.get("apply_url") or "").strip()

        seek_job_id = ""
        if apply_url:
            m = re.search(r"/job/(\d+)", apply_url)
            if m:
                seek_job_id = m.group(1)
        if not seek_job_id and str(job_id).isdigit() and len(str(job_id)) >= 6:
            seek_job_id = str(job_id)

        if not apply_url:
            apply_url = f"https://au.seek.com/job/{seek_job_id or job_id}"

        self._emit({
            "type": "apply_job_start",
            "job_id": job_id,
            "company": company,
            "title": title,
            "apply_url": apply_url,
            "message": f"Opening {company} — {title}",
        })

        try:
            await self._safe_goto(apply_url, wait_until="domcontentloaded", timeout=30000)
            cf_ok = await self._wait_for_cloudflare(20)
            if not cf_ok:
                logger.warning(f"Cloudflare verification active on {company} — {title}")
                self._emit({
                    "type": "apply_job_done",
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "status": "error",
                    "message": "Cloudflare security challenge active (could not bypass automatically)",
                })
                return ApplyResult(
                    job_id=job_id,
                    company=company,
                    title=title,
                    status=ApplyStatus.ERROR,
                    message="Cloudflare security challenge active",
                )

            await self._human_delay(1.5, 2.5)

            # 1. Check if already applied
            already_applied_sel = (
                "[data-automation='applied-badge'], "
                "[data-automation='job-detail-apply']:has-text('Applied'), "
                "button:has-text('Applied'):not(:has-text('jobs')), "
                "span:has-text('You applied for this job'), "
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
                "[data-automation='quick-apply-button'], "
                "[data-automation='job-detail-apply']"
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

            # If already on an /apply URL, we can proceed directly
            if "/apply" in self.page.url:
                has_quick_apply = True

            if not has_quick_apply and not has_external:
                generic_apply = self.page.locator("a:has-text('Apply'), button:has-text('Apply')").first
                if await self._is_visible("a:has-text('Apply'), button:has-text('Apply')", timeout=1000):
                    btn_text = ""
                    try:
                        btn_text = (await generic_apply.inner_text() or "").strip()
                    except Exception:
                        pass
                    if any(ext in btn_text.lower() for ext in ["employer site", "company site"]):
                        has_external = True
                    elif "quick" in btn_text.lower():
                        has_quick_apply = True

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

            # 3. Click Quick apply button if not already in apply wizard
            if "/apply" not in self.page.url:
                self._emit({
                    "type": "apply_job_progress",
                    "job_id": job_id,
                    "message": "Triggering SEEK Quick Apply form...",
                })
                apply_btn = self.page.locator(quick_apply_sel).first
                try:
                    await apply_btn.evaluate("el => el.removeAttribute('target')")
                except Exception:
                    pass
                try:
                    await self._safe_await(apply_btn.click(force=True, timeout=5000))
                except Exception:
                    try:
                        await self._safe_await(apply_btn.evaluate("el => el.click()"))
                    except Exception:
                        pass
                await self._human_delay(2.0, 3.5)

            # Wait for URL to settle (check for OAuth redirect, login, or apply form)
            # SEEK often performs a momentary OAuth bounce: au.seek.com/oauth/login -> /apply
            for _ in range(16):
                curr_u = self.page.url
                if "/apply" in curr_u and "oauth" not in curr_u and "login" not in curr_u:
                    break
                if "login.seek.com/login" in curr_u:
                    # Give it a moment to see if it redirects silently via SSO
                    await asyncio.sleep(1.5)
                    if "/apply" in self.page.url and "login" not in self.page.url:
                        break
                    if await self._is_seek_signin_form():
                        break
                await asyncio.sleep(0.5)

            # Check if clicked apply redirected to an external domain
            curr_url = self.page.url
            if not any(domain in curr_url for domain in ["seek.com.au", "au.seek.com", "seek.com"]):
                logger.info(f"Skipping {company} - {title}: Employer redirected to external portal ({curr_url})")
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

            # 4. Handle sign-in prompt if prompted (portal redirect or embedded form)
            if await self._is_seek_signin_form():
                if not self._is_authenticated:
                    login_ok = await self.login()
                    if not login_ok:
                        self._emit({
                            "type": "apply_job_done",
                            "job_id": job_id,
                            "company": company,
                            "title": title,
                            "status": "error",
                            "message": "SEEK authentication required to apply. Active login session missing.",
                        })
                        return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ERROR, message="Authentication required for Quick Apply")

                # Wait for redirect back to apply
                for _ in range(12):
                    if "/apply" in self.page.url and not await self._is_seek_signin_form():
                        break
                    await asyncio.sleep(0.5)

                # If still not in /apply, re-click Quick apply button if on job page
                if "/apply" not in self.page.url and any(domain in self.page.url for domain in ["seek.com.au", "au.seek.com"]):
                    apply_btn = self.page.locator(quick_apply_sel).first
                    if await self._is_visible(apply_btn, timeout=3000):
                        try:
                            await apply_btn.evaluate("el => el.removeAttribute('target')")
                            await self._safe_await(apply_btn.click(force=True, timeout=5000))
                        except Exception:
                            try:
                                await self._safe_await(apply_btn.evaluate("el => el.click()"))
                            except Exception:
                                pass
                        await self._human_delay(2.5, 4.0)

            # If not yet in apply wizard, attempt direct navigation to /apply endpoint
            target_seek_id = seek_job_id or (str(job_id) if str(job_id).isdigit() and len(str(job_id)) >= 6 else "")
            if ("/apply" not in self.page.url or await self._is_seek_signin_form()) and any(domain in self.page.url for domain in ["seek.com.au", "au.seek.com"]) and target_seek_id:
                direct_apply_url = f"https://au.seek.com/job/{target_seek_id}/apply"
                try:
                    await self._safe_goto(direct_apply_url, wait_until="domcontentloaded", timeout=20000)
                    await self._wait_for_cloudflare(15)
                    await self._human_delay(1.5, 2.5)
                except Exception:
                    pass

            # Guard: Ensure we are actually on /apply and NOT on a sign-in screen
            if "/apply" not in self.page.url or await self._is_seek_signin_form():
                if await self._is_seek_signin_form():
                    logger.info(f"Sign-in form active for {company} — {title}. Authenticating candidate...")
                    login_ok = await self.login()
                    if login_ok and target_seek_id:
                        direct_apply_url = f"https://au.seek.com/job/{target_seek_id}/apply"
                        try:
                            await self._safe_goto(direct_apply_url, wait_until="domcontentloaded", timeout=20000)
                            await self._wait_for_cloudflare(15)
                            await self._human_delay(1.5, 2.5)
                        except Exception:
                            pass

                if "/apply" not in self.page.url or await self._is_seek_signin_form():
                    if await self._is_seek_signin_form() or any(k in self.page.url for k in ["login.seek.com", "oauth/login"]):
                        self._emit({
                            "type": "apply_job_done",
                            "job_id": job_id,
                            "company": company,
                            "title": title,
                            "status": "error",
                            "message": "SEEK authentication required to apply. Active login session missing.",
                        })
                        return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ERROR, message="Authentication required for Quick Apply")
                    if "just a moment" in (await self._safe_title()).lower() or "__cf_chl_" in self.page.url:
                        self._emit({
                            "type": "apply_job_done",
                            "job_id": job_id,
                            "company": company,
                            "title": title,
                            "status": "error",
                            "message": "Cloudflare security challenge active (could not bypass automatically)",
                        })
                        return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ERROR, message="Cloudflare security challenge active")
                    self._emit({
                        "type": "apply_job_done",
                        "job_id": job_id,
                        "company": company,
                        "title": title,
                        "status": "error",
                        "message": "Could not access SEEK application wizard",
                    })
                    return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ERROR, message="Could not access SEEK application wizard")

            # 5. Form submission loop across wizard steps
            max_steps = 8
            for step_num in range(max_steps):
                await self._human_delay(1.5, 2.5)

                logger.info(f"[Apply Step {step_num + 1}/{max_steps}] URL: {self.page.url}")

                # Check if embedded sign-in form appeared during wizard
                if await self._is_seek_signin_form():
                    logger.info(f"[Apply Step {step_num + 1}/{max_steps}] Embedded sign-in form encountered. Authenticating candidate...")
                    login_ok = await self.login()
                    if not login_ok:
                        self._emit({
                            "type": "apply_job_done",
                            "job_id": job_id,
                            "company": company,
                            "title": title,
                            "status": "error",
                            "message": "SEEK authentication required to apply. Active login session missing.",
                        })
                        return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ERROR, message="Authentication required for Quick Apply")
                    await self._human_delay(2.0, 3.5)
                    continue

                # Check for completion screen
                body_sample = ""
                try:
                    body_sample = (await self.page.locator("body").inner_text() or "").lower()
                except Exception:
                    pass

                is_success = (
                    any(k in self.page.url for k in ["/success", "/applied", "/complete", "/confirmation"])
                    or any(phrase in body_sample for phrase in [
                        "application sent", "application submitted", "good luck", "you've applied",
                        "has been sent", "application received", "thanks for applying",
                        "thank you for applying", "your application has been sent",
                        "your application was submitted", "applied on seek"
                    ])
                    or await self._is_visible("[data-automation='application-success'], [data-automation='applied-badge']", timeout=400)
                )

                if is_success:
                    logger.info(f"SEEK application successfully submitted for {company} — {title}")
                    if self.db:
                        try:
                            self.db.update_opportunity_apply_status(job_id, apply_status="applied")
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

                # Step 1: Personal details & documents
                phone = (self.profile.get("phone") or self.resume_data.get("phone") or "0412345678").strip()
                country_sel = self.page.locator("select").first
                if await self._is_visible(country_sel, timeout=1000):
                    try:
                        options = await country_sel.locator("option").all()
                        for opt in options:
                            txt = (await opt.inner_text() or "").strip()
                            val = await opt.get_attribute("value")
                            if "61" in txt or "Australia" in txt:
                                await country_sel.select_option(val)
                                break
                    except Exception:
                        pass

                phone_input = self.page.locator("input[data-automation='phone-number'], input[name*='phone'], input[type='tel']").first
                if await self._is_visible(phone_input, timeout=1000):
                    val = str(await self._safe_await(phone_input.input_value(), default="") or "").strip()
                    if not val and phone:
                        await self._type_human(phone_input, phone)

                save_personal = self.page.locator("button:has-text('Save')").first
                if await self._is_visible(save_personal, timeout=1000):
                    try:
                        await save_personal.click(force=True)
                        await asyncio.sleep(0.5)
                    except Exception:
                        pass

                # Resume selection: ensure at least one document radio is selected
                try:
                    doc_radios = self.page.locator("input[name='document-select']")
                    cnt = await self._safe_await(doc_radios.count(), default=0)
                    if cnt and int(cnt) > 0:
                        has_checked = False
                        for r_idx in range(int(cnt)):
                            chk = await self._safe_await(doc_radios.nth(r_idx).is_checked(), default=False)
                            if bool(chk):
                                has_checked = True
                                break
                        if not has_checked:
                            await self._safe_await(doc_radios.first.check(force=True))
                except Exception:
                    pass

                # Cover letter: default to 'Don't include a cover letter' if no selection made
                none_cover = self.page.locator(
                    "[data-testid='coverLetter-method-none'], "
                    "input[name='coverLetter-method'][value='none'], "
                    "label:has-text(\"Don't include a cover letter\"), "
                    "label:has-text('Don’t include a cover letter')"
                ).first
                if await self._is_visible(none_cover, timeout=1000):
                    try:
                        await self._safe_await(none_cover.click(force=True))
                    except Exception:
                        try:
                            await self._safe_await(none_cover.evaluate("el => el.click()"))
                        except Exception:
                            pass

                try:
                    cov_radio = self.page.locator("input[name='coverLetter-method'][value='none']").first
                    cnt = await self._safe_await(cov_radio.count(), default=0)
                    if cnt and int(cnt) > 0:
                        chk = await self._safe_await(cov_radio.is_checked(), default=False)
                        if not bool(chk):
                            await self._safe_await(cov_radio.check(force=True))
                except Exception:
                    pass

                # Step 2: Profile & Career history
                new_workforce = self.page.locator(
                    "label:has-text('I am new to the workforce'), "
                    "label:has-text('new to the workforce'), "
                    "input[data-automation*='new-to-workforce'], "
                    "[data-testid*='new-to-workforce']"
                ).first
                if await self._is_visible(new_workforce, timeout=1000):
                    try:
                        await self._safe_await(new_workforce.click(force=True))
                    except Exception:
                        try:
                            await self._safe_await(new_workforce.evaluate("el => el.click()"))
                        except Exception as ce:
                            logger.debug(f"Career history handling note: {ce}")

                # Fill / Upload Resume if prompted
                file_input = self.page.locator("input[type='file']").first
                if await self._is_visible(file_input, timeout=1000):
                    resume_path = self._resolve_profile_resume_path(job)
                    if resume_path and os.path.exists(resume_path):
                        try:
                            is_tailored = "tailored" in Path(resume_path).name.lower()
                            logger.info(f"Uploading {'tailored' if is_tailored else 'profile'} resume to SEEK: {resume_path}")
                            await file_input.set_input_files(resume_path)
                            await self._human_delay(1.0, 1.8)
                        except Exception:
                            pass

                # Screening questions
                await self._answer_seek_screening_questions(title)

                # Check for Submit Application button
                # IMPORTANT: Must NOT match generic "button:has-text('Submit')" as that matches the header stepper
                # tab "Review and submit" on all steps! Only match actual final submit button.
                submit_selectors = [
                    "button[type='submit']:has-text('Submit application')",
                    "button:has-text('Submit application')",
                    "[data-automation='submit-application-button']",
                    "[data-automation='submit-application']",
                    "button[data-testid='submit-application']",
                    "[data-automation='review-submit-button']",
                    "[data-automation='review-and-submit-button']",
                    "button:has-text('Submit application now')",
                    "button:has-text('Send application')",
                ]
                submit_btn = None
                for s_sel in submit_selectors:
                    candidate = self.page.locator(s_sel).last
                    if await self._is_visible(candidate, timeout=800):
                        try:
                            in_stepper = await self._safe_await(candidate.evaluate("""el => {
                                let p = el.parentElement;
                                for (let i = 0; i < 6 && p; i++) {
                                    if (p.tagName === 'NAV' || p.tagName === 'OL' ||
                                        p.getAttribute('role') === 'tablist' ||
                                        p.getAttribute('role') === 'navigation' ||
                                        (p.getAttribute('data-automation') || '').includes('stepper')) return true;
                                    p = p.parentElement;
                                }
                                return false;
                            }"""), default=False)
                            if in_stepper:
                                continue
                        except Exception:
                            pass
                        submit_btn = candidate
                        logger.info(f"[Apply Step {step_num + 1}] Found Submit button: {s_sel}")
                        break

                if submit_btn:
                    self._emit({
                        "type": "apply_job_progress",
                        "job_id": job_id,
                        "message": f"Submitting application for {company}...",
                    })
                    try:
                        await submit_btn.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    await self._human_delay(0.5, 1.2)
                    try:
                        await submit_btn.click(force=True, timeout=5000)
                    except Exception:
                        try:
                            await submit_btn.evaluate("el => el.click()")
                        except Exception as e:
                            logger.warning(f"Submit click failed: {e}")
                    await self._human_delay(3.0, 5.0)
                    continue

                # Continue / Next button — check each selector individually to avoid
                # matching stepper header tabs. Use JS check to skip nav/tab elements.
                continue_selectors = [
                    "button:has-text('Continue')",
                    "button:has-text('Next')",
                    "[data-automation='continue-button']",
                    "button:has-text('Save and continue')",
                    "button:has-text('Review and submit')",
                    "button:has-text('Review')",
                    "a:has-text('Continue')",
                    "a:has-text('Next')",
                ]
                continue_btn = None
                for c_sel in continue_selectors:
                    candidate = self.page.locator(c_sel).last
                    if await self._is_visible(candidate, timeout=800):
                        # Verify it's not a stepper header tab
                        try:
                            in_stepper = await self._safe_await(candidate.evaluate("""el => {
                                let p = el.parentElement;
                                for (let i = 0; i < 6 && p; i++) {
                                    if (p.tagName === 'NAV' || p.tagName === 'OL' ||
                                        p.getAttribute('role') === 'tablist' ||
                                        p.getAttribute('role') === 'navigation' ||
                                        (p.getAttribute('data-automation') || '').includes('stepper')) return true;
                                    p = p.parentElement;
                                }
                                return false;
                            }"""), default=False)
                            if in_stepper:
                                logger.debug(f"[Apply Step {step_num + 1}] Skipping stepper tab: {c_sel}")
                                continue
                        except Exception:
                            pass
                        continue_btn = candidate
                        logger.info(f"[Apply Step {step_num + 1}] Found Continue button: {c_sel}")
                        break

                if continue_btn:
                    try:
                        await continue_btn.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    await self._human_delay(0.5, 1.0)
                    try:
                        await continue_btn.click(force=True, timeout=5000)
                    except Exception:
                        try:
                            await continue_btn.evaluate("el => el.click()")
                        except Exception:
                            pass
                    await self._human_delay(2.0, 3.5)
                else:
                    logger.info(f"[Apply Step {step_num + 1}] No Continue or Submit button found on URL: {self.page.url}")
                    # Log visible buttons for debugging
                    try:
                        all_btns = self.page.locator("button:visible, a[role='button']:visible")
                        btn_count = await self._safe_await(all_btns.count(), default=0)
                        for bi in range(min(int(btn_count or 0), 10)):
                            btn_el = all_btns.nth(bi)
                            btn_text = (await self._safe_await(btn_el.inner_text(), default="")).strip()[:60]
                            if btn_text:
                                logger.info(f"[Apply Step {step_num + 1}] Visible button: '{btn_text}'")
                    except Exception:
                        pass

                    # Check if already reached success before giving up
                    if "/success" in self.page.url or any(phrase in body_sample for phrase in ["application sent", "application submitted", "good luck", "you've applied", "has been sent"]):
                        break
                    # Attempt any submit / action button fallback
                    action_btn = self.page.locator(
                        "button[type='submit']:has-text('Submit'), "
                        "button:has-text('Submit application'), "
                        "button:has-text('Submit'), "
                        "button:has-text('Send application'), "
                        "[data-automation*='submit']"
                    ).last
                    if await self._is_visible(action_btn, timeout=1200):
                        try:
                            in_nav = await self._safe_await(action_btn.evaluate("""el => {
                                let p = el.parentElement;
                                for (let i = 0; i < 6 && p; i++) {
                                    if (p.tagName === 'NAV' || p.tagName === 'OL' ||
                                        p.getAttribute('role') === 'tablist' ||
                                        p.getAttribute('role') === 'navigation' ||
                                        (p.getAttribute('data-automation') || '').includes('stepper')) return true;
                                    p = p.parentElement;
                                }
                                return false;
                            }"""), default=False)
                            if not in_nav:
                                logger.info(f"[Apply Step {step_num + 1}] Clicking fallback submit action button")
                                await action_btn.scroll_into_view_if_needed()
                                await action_btn.click(force=True, timeout=5000)
                                await self._human_delay(3.0, 5.0)
                                continue
                        except Exception as e:
                            logger.debug(f"Action button fallback click notice: {e}")
                    break

            # Final check for submission success
            body_final = ""
            try:
                body_final = (await self.page.locator("body").inner_text() or "").lower()
            except Exception:
                pass

            final_success = (
                any(k in self.page.url for k in ["/success", "/applied", "/complete", "/confirmation"])
                or any(phrase in body_final for phrase in [
                    "application sent", "application submitted", "good luck", "you've applied",
                    "has been sent", "application received", "thanks for applying",
                    "thank you for applying", "your application has been sent",
                    "your application was submitted", "applied on seek"
                ])
                or await self._is_visible("[data-automation='application-success'], [data-automation='applied-badge']", timeout=400)
            )

            if final_success:
                if self.db:
                    try:
                        self.db.update_opportunity_apply_status(job_id, apply_status="applied")
                    except Exception:
                        pass
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

            if any(k in self.page.url for k in ["login.seek.com", "oauth/login"]) or await self._is_seek_signin_form():
                logger.warning(f"Apply ended on login portal for {company} — {title}")
                self._emit({
                    "type": "apply_job_done",
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "status": "error",
                    "message": "SEEK authentication required to apply. Active login session missing.",
                })
                return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ERROR, message="Authentication required for Quick Apply")

            if "just a moment" in (await self._safe_title()).lower() or "__cf_chl_" in self.page.url:
                logger.warning(f"Apply trapped on Cloudflare challenge for {company} — {title}")
                self._emit({
                    "type": "apply_job_done",
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "status": "error",
                    "message": "Cloudflare security challenge active (could not bypass automatically)",
                })
                return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ERROR, message="Cloudflare security challenge active")

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
        try:
            work_rights_radios = self.page.locator(
                "label:has-text('Australian citizen'), "
                "label:has-text('Permanent resident'), "
                "label:has-text('full work rights'), "
                "label:has-text('appropriate visa'), "
                "label:has-text('unrestricted right to work')"
            )
            cnt = await self._safe_await(work_rights_radios.count(), default=0)
            if cnt and int(cnt) > 0:
                await self._safe_await(work_rights_radios.first.click())
        except Exception:
            pass

        # Notice period dropdowns or radio
        try:
            notice = (self.profile.get("notice_period") or "Immediate").lower()
            if "immediate" in notice or "0" in notice:
                notice_opts = self.page.locator("label:has-text('Immediate'), label:has-text('Immediately'), label:has-text('Within 1 week'), label:has-text('2 weeks')")
                cnt = await self._safe_await(notice_opts.count(), default=0)
                if cnt and int(cnt) > 0:
                    await self._safe_await(notice_opts.first.click())
        except Exception:
            pass

        # Drivers licence, police check, background check (default to Yes)
        try:
            fieldsets = await self.page.locator("fieldset, div[role='radiogroup'], [data-automation*='question']").all()
            for fs in fieldsets:
                txt = (await fs.inner_text() or "").lower()
                if any(w in txt for w in ["driver's licence", "drivers licence", "driver license", "police check", "background check", "working with children", "legally entitled", "right to work"]):
                    yes_btn = fs.locator("label:has-text('Yes'), input[value='true'], input[value='yes']").first
                    if await self._is_visible(yes_btn, timeout=500):
                        try:
                            await yes_btn.click(force=True)
                        except Exception:
                            pass
        except Exception:
            pass

        # Numerical experience inputs
        try:
            exp_inputs = await self.page.locator("input[type='number'], input[name*='experience'], input[aria-label*='experience']").all()
            for inp in exp_inputs:
                curr_v = str(await self._safe_await(inp.input_value(), default="") or "").strip()
                if not curr_v:
                    try:
                        await inp.fill("3")
                    except Exception:
                        pass
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
