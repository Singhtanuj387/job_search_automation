"""
Indeed Interactive Login Helper.
Opens a visible Chrome browser on the desktop to complete login
(solving reCAPTCHA, entering email OTP code, or using Google sign-in).
Once completed, exports cookies and storage state for headless auto-apply.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def run_interactive_login(email: str = "singhtanuj387@gmail.com", timeout_seconds: int = 180):
    display = os.environ.get("DISPLAY", ":0.0")
    print(f"\n========================================================")
    print(f"🚀 Launching Indeed Login Window on {display}")
    print(f"Target Email: {email}")
    print(f"========================================================\n")

    user_data_dir = Path("data/indeed_chrome_profile")
    user_data_dir.mkdir(parents=True, exist_ok=True)

    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=1280,850",
    ]

    chrome_bin = "/usr/bin/google-chrome"
    if not os.path.exists(chrome_bin):
        chrome_bin = "/usr/bin/chromium-browser"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir.resolve()),
            headless=False,
            executable_path=chrome_bin if os.path.exists(chrome_bin) else None,
            args=args,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1280, "height": 850},
        )

        page = context.pages[0] if context.pages else await context.new_page()
        try:
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
        except Exception:
            pass

        print("Navigating to Indeed authentication portal...")
        await page.goto("https://in.indeed.com/account/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Accept cookie banner if present
        try:
            c_btn = page.locator("#onetrust-accept-btn-handler, button:has-text('Accept All Cookies')").first
            if await c_btn.is_visible(timeout=2000):
                await c_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        # Check if already logged in
        curr_url = page.url
        curr_title = await page.title()
        if "auth" not in curr_url and "login" not in curr_url and "signin" not in curr_url and "Blocked" not in curr_title:
            print("✅ Already logged in to Indeed!")
            await save_session(context)
            await context.close()
            return True

        # Pre-fill email
        try:
            email_inp = page.locator("input[name='__email'], input[type='email']").first
            if await email_inp.is_visible(timeout=2500):
                val = await email_inp.input_value()
                if email not in val:
                    await email_inp.click()
                    for ch in email:
                        await email_inp.press_sequentially(ch, delay=25)
                    await asyncio.sleep(0.5)

                cont_btn = page.locator("button[type='submit']:has-text('Continue')").first
                if await cont_btn.is_visible(timeout=1500):
                    print("Submitting email...")
                    await cont_btn.click()
                    await asyncio.sleep(2)
        except Exception as e:
            print(f"Note on email prefill: {e}")

        # Check for code link option
        try:
            code_link = page.locator("#auth-page-google-otp-fallback, a:has-text('Sign in with a code'), button:has-text('Sign in with a code')").first
            if await code_link.is_visible(timeout=2500):
                print("Clicking 'Sign in with a code'...")
                await code_link.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        print("\n👉 A Chrome window is now OPEN on your screen.")
        print("1. Complete the visual reCAPTCHA puzzle if prompted.")
        print("2. Enter the verification code sent to your email (or use Google sign-in).")
        print(f"3. Waiting up to {timeout_seconds} seconds for you to finish logging in...\n")

        # Wait for user to complete login
        for sec in range(timeout_seconds):
            await asyncio.sleep(1)
            url = page.url
            title = await page.title()

            is_authenticated = (
                ("in.indeed.com" in url or "myjobs.indeed.com" in url or "profile.indeed.com" in url or "indeed.com" in url)
                and "auth" not in url
                and "login" not in url
                and "signin" not in url
                and "challenge" not in url
                and "Blocked" not in title
            )

            if is_authenticated:
                print(f"\n🎉 Successfully authenticated on Indeed! URL: {url}")
                await save_session(context)
                await asyncio.sleep(2)
                await context.close()
                return True

            if sec % 15 == 0 and sec > 0:
                print(f"Still waiting for login... ({sec}/{timeout_seconds}s). Current page: {title}")

        print("\n❌ Login timed out. Please try again.")
        await context.close()
        return False

async def save_session(context):
    """Save cookies and storage state to persistent paths."""
    out_dirs = [Path("data"), Path("web/backend/data")]
    for d in out_dirs:
        d.mkdir(parents=True, exist_ok=True)

    cookies = await context.cookies()
    for d in out_dirs:
        (d / "indeed_cookies.json").write_text(json.dumps(cookies, indent=2))
        try:
            await context.storage_state(path=str((d / "indeed_storage_state.json").resolve()))
        except Exception:
            pass
    print("💾 Saved Indeed session cookies to data/indeed_cookies.json and data/indeed_storage_state.json")

if __name__ == "__main__":
    email_arg = sys.argv[1] if len(sys.argv) > 1 else "singhtanuj387@gmail.com"
    success = asyncio.run(run_interactive_login(email_arg))
    sys.exit(0 if success else 1)
