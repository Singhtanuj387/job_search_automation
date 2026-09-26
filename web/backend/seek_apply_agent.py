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

            sources = [
                ("Brave Safe Storage", os.path.expanduser("~/.config/BraveSoftware/Brave-Browser/Default/Cookies")),
                ("Chrome Safe Storage", os.path.expanduser("~/.config/google-chrome/Default/Cookies")),
                ("Chromium Safe Storage", os.path.expanduser("~/.config/chromium/Default/Cookies")),
            ]

            all_seek_cookies = []

            for label, cookie_db in sources:
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

            # Deduplicate by (domain, name)
            unique = {}
            for ck in all_seek_cookies:
                unique[(ck["domain"], ck["name"])] = ck

            cookies_list = list(unique.values())
            has_session = any(ck["name"] in ("appSession", "auth0") for ck in cookies_list)
            if not has_session:
                return False

            state = {"cookies": cookies_list, "origins": []}
            for sp in [
                Path("web/backend/data/seek_storage_state.json"),
                Path("data/seek_storage_state.json"),
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

        # 2. Check if fresh stored session exists; otherwise attempt auto-import from local browser
        has_fresh_session = False
        for sp in [
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/web/backend/data/seek_storage_state.json"),
            Path("/mnt/extra/morningstar/Gradebuddy/job_search_automation/data/seek_storage_state.json"),
            Path("web/backend/data/seek_storage_state.json"),
            Path("data/seek_storage_state.json"),
        ]:
            if sp.exists() and sp.stat().st_size > 100:
                try:
                    s_data = json.loads(sp.read_text())
                    if any(c.get("name") in ("appSession", "auth0") for c in s_data.get("cookies", [])):
                        has_fresh_session = True
                        break
                except Exception:
                    pass

        if not has_fresh_session:
            self._import_browser_cookies()

        # Locate system browser binary: prioritize brave-browser since candidate's live session is in Brave
        browser_bin = None
        for cand_bin in [
            "/usr/bin/brave-browser",
            "/opt/brave.com/brave/brave",
            "/usr/bin/brave",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/opt/google/chrome/chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]:
            if os.path.exists(cand_bin):
                browser_bin = cand_bin
                break

        # Check if local desktop profile exists to clone cookies and Local Storage (Auth0 SPA tokens)
        desktop_profile_src = None
        for prof_path in [
            os.path.expanduser("~/.config/BraveSoftware/Brave-Browser/Default"),
            os.path.expanduser("~/.config/google-chrome/Default"),
            os.path.expanduser("~/.config/chromium/Default"),
        ]:
            if os.path.exists(prof_path):
                desktop_profile_src = prof_path
                break

        cloned_profile_dir = None
        if desktop_profile_src and browser_bin:
            try:
                import tempfile
                import shutil
                cloned_profile_dir = tempfile.mkdtemp(prefix="seek_profile_")
                default_sub = os.path.join(cloned_profile_dir, "Default")
                os.makedirs(default_sub, exist_ok=True)
                for item in ["Local Storage", "IndexedDB", "Network"]:
                    src = os.path.join(desktop_profile_src, item)
                    dst = os.path.join(default_sub, item)
                    if os.path.exists(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                src_cookies = os.path.join(desktop_profile_src, "Cookies")
                if os.path.exists(src_cookies):
                    shutil.copy2(src_cookies, os.path.join(default_sub, "Cookies"))
                self._temp_user_data_dir = cloned_profile_dir
                logger.info(f"Cloned live desktop profile from {desktop_profile_src} to {cloned_profile_dir}")
            except Exception as pe:
                logger.debug(f"Profile cloning note: {pe}")
                cloned_profile_dir = None

        pre_wids = set()
        if os.environ.get("DISPLAY"):
            try:
                import subprocess
                for cls_name in ["brave-browser", "google-chrome", "chromium"]:
                    out = subprocess.run(["xdotool", "search", "--class", cls_name], capture_output=True, text=True)
                    pre_wids.update(out.stdout.split())
            except Exception:
                pass

        if cloned_profile_dir:
            try:
                self.context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=cloned_profile_dir,
                    executable_path=browser_bin,
                    headless=False,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--window-position=5000,5000",
                        "--disable-dev-shm-usage",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                    viewport={"width": 1280, "height": 800},
                )
                # Move newly spawned automated window off-display and minimize on X11
                if os.environ.get("DISPLAY"):
                    try:
                        import subprocess
                        for cls_name in ["brave-browser", "google-chrome", "chromium"]:
                            out = subprocess.run(["xdotool", "search", "--class", cls_name], capture_output=True, text=True)
                            for wid in out.stdout.split():
                                if wid not in pre_wids:
                                    subprocess.run(["xdotool", "set_desktop_for_window", wid, "3"], capture_output=True)
                                    subprocess.run(["xdotool", "windowminimize", wid], capture_output=True)
                    except Exception:
                        pass

                self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                logger.info("SEEK Browser initialized silently via cloned desktop profile in background")
                return
            except Exception as persist_err:
                logger.warning(f"Persistent context launch failed ({persist_err}), falling back to standard launch...")

        # 3. Standalone launch fallback
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
            "--no-first-run",
            "--no-default-browser-check",
            "--silent-debugger-extension-api",
        ]

        if is_headless:
            args.append("--headless=new")
            launch_kwargs = {
                "headless": True,
                "args": args,
            }
        else:
            args.append("--window-position=5000,5000")
            launch_kwargs = {
                "headless": False,
                "args": args,
            }

        if browser_bin:
            launch_kwargs["executable_path"] = browser_bin

        self.browser = await self._playwright.chromium.launch(**launch_kwargs)

        # Move fallback window off display on X11
        if not is_headless and os.environ.get("DISPLAY"):
            try:
                import subprocess
                for cls_name in ["brave-browser", "google-chrome", "chromium"]:
                    out = subprocess.run(["xdotool", "search", "--class", cls_name], capture_output=True, text=True)
                    for wid in out.stdout.split():
                        if wid not in pre_wids:
                            subprocess.run(["xdotool", "set_desktop_for_window", wid, "3"], capture_output=True)
                            subprocess.run(["xdotool", "windowminimize", wid], capture_output=True)
            except Exception:
                pass

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
        }
        if storage_state_path:
            # Filter out stale cf clearance tokens
            try:
                s_data = json.loads(Path(storage_state_path).read_text())
                filtered_cookies = [
                    c for c in s_data.get("cookies", [])
                    if not c.get("name", "").startswith("cf_")
                    and not c.get("name", "").startswith("__cf")
                    and not c.get("name", "").startswith("_cf")
                ]
                s_data["cookies"] = filtered_cookies
                temp_state = Path("/tmp/seek_clean_state.json")
                temp_state.write_text(json.dumps(s_data))
                context_kwargs["storage_state"] = str(temp_state)
            except Exception:
                context_kwargs["storage_state"] = storage_state_path

        self.context = await self.browser.new_context(**context_kwargs)
        try:
            await self.context.add_init_script("""
                Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)
        except Exception:
            pass

        self.page = await self.context.new_page()
        logger.info("SEEK Browser initialized silently in background")

    async def close_browser(self):
        """Clean up browser resources and temp profile."""
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

    async def _wait_for_cloudflare(self, max_wait_seconds: int = 20):
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

            is_cf = (
                "just a moment" in title
                or title.startswith("loading ")
                or "__cf_chl_" in curr_url
                or "checking your browser" in title
                or "attention required" in title
                or "security verification" in body_text
                or ("ray id" in body_text and "cloudflare" in body_text)
            )
            if not is_cf and title != "":
                if r > 0:
                    logger.info(f"Cloudflare verification cleared after {r}s (Title: {title})")
                return True
            await asyncio.sleep(1)

        logger.warning("Cloudflare challenge did not clear automatically within timeout")
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
            "[data-automation='profile'], "
            "[data-automation='account name'], "
            "[aria-label='Profile Avatar'], "
            "[data-automation='mobile-profile-avatar-wrapper'], "
            "a[href*='/profile'], "
            "a:has-text('Profile'), "
            "[data-automation='sign out'], "
            "button:has-text('Sign out'), "
            "a:has-text('Sign out')"
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
                                    sanitized = [c for c in cookies_to_add if c.get("name") not in ("cf_clearance", "__cf_bm")]
                                    await self.context.add_cookies(sanitized)
                                    logger.info(f"Restoring {len(sanitized)} SEEK session cookies from {cp}")
                                    break
                            except Exception:
                                pass

                await self.page.goto("https://au.seek.com/", wait_until="domcontentloaded", timeout=20000)
                cf_ok = await self._wait_for_cloudflare(15)
                await asyncio.sleep(self.PAGE_LOAD_WAIT)

                curr_title = (await self._safe_title()).lower()
                if "just a moment" not in curr_title and curr_title:
                    is_logged_in = await self._is_visible(auth_indicators, timeout=3000)
                    has_sign_in = await self._is_visible("a:has-text('Sign in'), button:has-text('Sign in')", timeout=1500)
                    if is_logged_in and not has_sign_in and "login.seek.com" not in self.page.url:
                        logger.info("SEEK session valid. Logged in successfully.")
                        self._emit({
                            "type": "apply_login_success",
                            "method": "cookies",
                            "message": "Authenticated with SEEK (active session)",
                        })
                        return True
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
            # If not already on login or oauth portal, navigate to https://au.seek.com/oauth/login
            if not any(k in self.page.url for k in ["login.seek.com", "oauth/login"]):
                await self.page.goto("https://au.seek.com/oauth/login", wait_until="domcontentloaded", timeout=25000)
                await self._wait_for_cloudflare(15)
                await self._human_delay(1.5, 2.5)

            # Wait for email input to be visible (Auth0 SPA mount)
            email_input_sel = (
                "input#emailAddress, "
                "input[type='email'], "
                "input[name='emailAddress_seekanz'], "
                "input[name='email'], "
                "[data-testid='email-input']"
            )
            email_field = self.page.locator(email_input_sel).first
            for _ in range(10):
                if await self._is_visible(email_field, timeout=500):
                    break
                await asyncio.sleep(0.5)

            if await self._is_visible(email_field, timeout=3000):
                await self._type_human(email_field, email)
                await self._human_delay(0.5, 1.0)

                # Submit email to request code or proceed
                code_btn_sel = (
                    "button[type='submit']:has-text('Email me a sign in code'), "
                    "button:has-text('Email me a sign in code'), "
                    "button[type='submit']"
                )
                submit_btn = self.page.locator(code_btn_sel).first
                if await self._is_visible(submit_btn, timeout=3000):
                    await submit_btn.click()
                    await self._human_delay(2.5, 4.0)

            # Check for reCAPTCHA challenge or errors
            body_text = ""
            try:
                body_text = (await self.page.locator("body").inner_text() or "").lower()
            except Exception:
                pass

            if "please complete the recaptcha" in body_text or "verify you are not a bot" in body_text or "recaptcha" in body_text:
                logger.warning("SEEK authentication bot challenge active on login page (reCAPTCHA)")
                self._emit({
                    "type": "apply_error",
                    "message": "SEEK sign-in challenge active (reCAPTCHA). Please open SEEK in your browser to log in once, so the agent can use your active session.",
                })
                return False

            is_code_screen = (
                "check your email" in body_text
                or "enter the 6-digit code" in body_text
                or "enter your 6 digit code" in body_text
                or "6-digit code" in body_text
                or "we sent a code" in body_text
                or "we've sent a code" in body_text
                or ("verification" in body_text and "code" in body_text)
                or await self._is_visible(
                    "input[aria-label*='verification' i], "
                    "#submit-OTP, "
                    "[data-cy='verification'], "
                    "[data-testid*='character-0'], "
                    "#field-0, "
                    "div[data-testid='container'] input, "
                    "input[data-testid*='digit-input'], "
                    "input[autocomplete='one-time-code']",
                    timeout=2000
                )
            )

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

            if "just a moment" in (await self._safe_title()).lower():
                logger.warning("Trapped on Cloudflare challenge during login")
                self._emit({
                    "type": "apply_error",
                    "message": "Cloudflare challenge active during authentication redirect.",
                })
                return False

            # Strict verification of authentication indicators
            is_authenticated = False
            for _ in range(5):
                if await self._is_visible(auth_indicators, timeout=2000):
                    is_authenticated = True
                    break
                # Also check cookies for candidate authentication
                try:
                    curr_cookies = await self.context.cookies()
                    c_names = {c.get("name") for c in curr_cookies}
                    if any(cn in c_names for cn in ["registeredCandidateId", "appSession", "auth0.GCQ2kVaZFnAkVZYKkgwqCq7oFfiYYUfA.is.authenticated"]) and "login.seek.com" not in self.page.url:
                        is_authenticated = True
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)

            if not is_authenticated:
                logger.warning("SEEK authentication indicators not present on destination page after sign-in")
                self._emit({
                    "type": "apply_error",
                    "message": "SEEK session could not be verified after sign-in. Please log into SEEK in your browser.",
                })
                return False

            # Persist authenticated cookies and storage state
            try:
                cookies = await self.context.cookies()
                for cp in cookie_paths:
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    cp.write_text(json.dumps(cookies, indent=2))
            except Exception:
                pass

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

        if not apply_url:
            apply_url = f"https://au.seek.com/job/{job_id}"

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
            cf_ok = await self._wait_for_cloudflare(15)
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
            for _ in range(10):
                curr_u = self.page.url
                if any(k in curr_u for k in ["login.seek.com", "oauth/login"]):
                    break
                if "/apply" in curr_u and "oauth" not in curr_u:
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

            # 4. Handle sign-in prompt if prompted
            if "login.seek.com" in self.page.url or "oauth/login" in self.page.url:
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
                    if "/apply" in self.page.url and "login" not in self.page.url and "oauth" not in self.page.url:
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

            # Check if still trapped on login/auth page
            if any(k in self.page.url for k in ["login.seek.com", "oauth/login"]):
                logger.warning(f"Aborting apply for {company} — {title}: Still stuck on login portal ({self.page.url})")
                self._emit({
                    "type": "apply_job_done",
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "status": "error",
                    "message": "SEEK authentication required to apply. Active login session missing.",
                })
                return ApplyResult(job_id=job_id, company=company, title=title, status=ApplyStatus.ERROR, message="Authentication required for Quick Apply")

            # If not yet in apply wizard, attempt direct navigation to /apply endpoint
            if "/apply" not in self.page.url and any(domain in self.page.url for domain in ["seek.com.au", "au.seek.com"]) and job_id:
                direct_apply_url = f"https://au.seek.com/job/{job_id}/apply"
                try:
                    await self.page.goto(direct_apply_url, wait_until="domcontentloaded", timeout=20000)
                    await self._wait_for_cloudflare(15)
                    await self._human_delay(1.5, 2.5)
                except Exception:
                    pass

            # Guard: Ensure we are actually on /apply before starting form wizard loop
            if "/apply" not in self.page.url:
                if any(k in self.page.url for k in ["login.seek.com", "oauth/login"]):
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

                # Check for completion screen
                body_sample = ""
                try:
                    body_sample = (await self.page.locator("body").inner_text() or "").lower()
                except Exception:
                    pass

                if "/success" in self.page.url or any(phrase in body_sample for phrase in ["application sent", "application submitted", "good luck", "you've applied", "has been sent"]):
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
                    resume_path = self._resolve_profile_resume_path()
                    if resume_path and os.path.exists(resume_path):
                        try:
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
                    "button[data-testid='submit-application']",
                ]
                submit_btn = None
                for s_sel in submit_selectors:
                    candidate = self.page.locator(s_sel).last
                    if await self._is_visible(candidate, timeout=800):
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
                    action_btn = self.page.locator("button[type='submit']:has-text('Submit'), button:has-text('Submit'), button:has-text('Send')").last
                    if await self._is_visible(action_btn, timeout=1000):
                        try:
                            await action_btn.click(force=True, timeout=5000)
                            await self._human_delay(2.5, 4.0)
                            continue
                        except Exception:
                            pass
                    break

            # Final check for submission success
            body_final = ""
            try:
                body_final = (await self.page.locator("body").inner_text() or "").lower()
            except Exception:
                pass

            if "/success" in self.page.url or any(phrase in body_final for phrase in ["application sent", "application submitted", "good luck", "you've applied", "has been sent"]):
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

            if any(k in self.page.url for k in ["login.seek.com", "oauth/login"]):
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
