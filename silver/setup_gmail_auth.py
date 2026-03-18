"""Gmail OAuth 2.0 Setup — run this once to authenticate.

This script opens a browser window for Google OAuth consent and saves
the resulting token to the path configured in GMAIL_TOKEN_PATH.

Scopes granted:
  - gmail.readonly  — read emails (used by GmailWatcher)
  - gmail.send      — send emails (used by ApprovalWatcher when reply is approved)

Prerequisites:
  1. Go to Google Cloud Console → APIs & Services → Credentials
  2. Create an OAuth 2.0 Client ID (Desktop App type)
  3. Download the JSON and save it (e.g., silver/gmail_credentials.json)
  4. Enable the Gmail API for your project
  5. Set GMAIL_CREDENTIALS_PATH in your .env

Usage:
    cd silver/
    uv run python setup_gmail_auth.py
"""

import sys
from pathlib import Path

# Ensure silver/ is on the path
_silver_dir = Path(__file__).resolve().parent
if str(_silver_dir) not in sys.path:
    sys.path.insert(0, str(_silver_dir))

from src.core.config import config
from src.watchers.gmail_watcher import GMAIL_SCOPES


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("ERROR: Google auth libraries not installed.")
        print("Run: uv add google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

    creds_path = config.gmail_credentials_path
    token_path = config.gmail_token_path

    if not creds_path.exists():
        print(f"ERROR: Credentials file not found at: {creds_path}")
        print()
        print("Steps to create it:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create/select a project")
        print("  3. Enable the Gmail API")
        print("  4. Go to APIs & Services > Credentials")
        print("  5. Create OAuth 2.0 Client ID (Desktop App)")
        print("  6. Download JSON and save it to:", creds_path)
        sys.exit(1)

    # If a token exists but was created with old scopes (readonly only), delete it
    # so we force a fresh OAuth flow with both scopes.
    if token_path.exists():
        import json
        try:
            data = json.loads(token_path.read_text(encoding="utf-8"))
            existing_scopes = set(data.get("scopes", []))
            required_scopes = set(GMAIL_SCOPES)
            if not required_scopes.issubset(existing_scopes):
                print(f"Existing token is missing scopes. Deleting and re-authenticating.")
                print(f"  Have:    {existing_scopes}")
                print(f"  Need:    {required_scopes}")
                print()
                token_path.unlink()
        except (json.JSONDecodeError, OSError):
            token_path.unlink(missing_ok=True)

    # Check if we already have a valid token with the right scopes
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)

    if creds and creds.valid:
        print(f"Token already valid at: {token_path}")
        print(f"Scopes: {GMAIL_SCOPES}")
        print()
        print("Authentication complete — Gmail Watcher + send are ready.")
        return

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        print(f"Token refreshed and saved to: {token_path}")
        return

    # Run full OAuth flow
    print()
    print("Opening browser for Google OAuth consent...")
    print("(Granting: gmail.readonly + gmail.send)")
    print()
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), GMAIL_SCOPES)
    creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    print()
    print(f"Token saved to: {token_path}")
    print()
    print("Authentication complete.")
    print()
    print("Next steps:")
    print("  1. Set DRY_RUN=false in silver/.env")
    print("  2. Start the orchestrator:  uv run python orchestrator.py")


if __name__ == "__main__":
    main()
