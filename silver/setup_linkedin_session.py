"""LinkedIn Session Setup — run this once to log in and save the browser session.

This script opens a HEADED (visible) browser window for you to log in to LinkedIn
manually. Once logged in, the session (cookies) is saved to LINKEDIN_SESSION_PATH
so the LinkedIn Watcher daemon can run in the background without showing a window.

Prerequisites:
    uv add playwright
    uv run playwright install chromium

Usage:
    cd silver/
    uv run python setup_linkedin_session.py
"""

import sys
from pathlib import Path

# Ensure silver/ is on the path
_silver_dir = Path(__file__).resolve().parent
if str(_silver_dir) not in sys.path:
    sys.path.insert(0, str(_silver_dir))

from src.core.config import config


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Playwright not installed.")
        print()
        print("Run the following commands first:")
        print("  uv add playwright")
        print("  uv run playwright install chromium")
        sys.exit(1)

    session_path = config.linkedin_session_path
    session_path.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 60)
    print("  LinkedIn Session Setup — AI Employee Silver")
    print("=" * 60)
    print()
    print("A browser window will open. Log in to LinkedIn manually.")
    print("After logging in, return here and press Enter to save the session.")
    print()
    print(f"Session will be saved to: {session_path}")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(session_path),
            headless=False,  # Must be headed so you can log in visually
            args=["--no-sandbox"],
        )

        page = browser.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        page.wait_for_timeout(1_000)

        print("Browser opened. Please log in to LinkedIn now.")
        print("  1. Enter your email/phone and password")
        print("  2. Complete any 2FA if prompted")
        print("  3. Wait until you see your LinkedIn home feed")
        print()
        input(">>> Press Enter AFTER you can see your LinkedIn home feed: ")

        # Verify login succeeded
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        page.wait_for_timeout(2_000)

        current_url = page.url
        if any(kw in current_url for kw in ("login", "authwall", "checkpoint")):
            print()
            print("ERROR: Login does not appear to be complete.")
            print(f"  Current URL: {current_url}")
            print()
            print("Please try again — make sure you're on your LinkedIn feed before pressing Enter.")
            browser.close()
            sys.exit(1)

        print()
        print("Login verified! Saving session...")
        browser.close()

    print()
    print(f"Session saved to: {session_path}")
    print()
    print("Next steps:")
    print("  1. Set LINKEDIN_HEADLESS=true in silver/.env  (daemon runs without browser window)")
    print("  2. Start the orchestrator:  uv run python orchestrator.py")
    print()
    print("The LinkedIn Watcher will now monitor messages and notifications automatically.")
    print("Use /linkedin-post-creator in Claude Code to draft and schedule LinkedIn posts.")
    print()


if __name__ == "__main__":
    main()
