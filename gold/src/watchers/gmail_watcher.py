"""Gmail Watcher — monitors Gmail for unread important emails.

Uses the official Gmail API (OAuth 2.0) to poll for new messages matching
a configurable query (default: is:unread is:important).

When a matching email is found:
  1. Extracts subject, sender, date, and body
  2. Writes a .md file to /Needs_Action/ for Claude to process
  3. Persists processed message IDs to avoid duplicates across restarts

Setup (one-time):
    Run setup_gmail_auth.py to authenticate and generate the token file.

Usage:
    uv run python -m src.watchers.gmail_watcher
"""

import base64
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from src.core.config import config
from src.core.vault_manager import write_markdown, update_dashboard, list_needs_action, list_folder
from src.utils.logger import audit_log, setup_logging
from src.watchers.base_watcher import BaseWatcher

logger = setup_logging()

# File to persist processed Gmail message IDs across restarts
_PROCESSED_IDS_FILE = config.silver_dir / ".gmail_processed_ids.json"

# Keywords that bump priority to high
_HIGH_PRIORITY_KEYWORDS = ["urgent", "asap", "critical", "emergency", "invoice overdue", "payment failed"]
_MEDIUM_PRIORITY_KEYWORDS = ["invoice", "payment", "bill", "deadline", "important", "contract", "proposal"]


def _load_processed_ids() -> set[str]:
    """Load previously processed Gmail message IDs from disk."""
    if _PROCESSED_IDS_FILE.exists():
        try:
            data = json.loads(_PROCESSED_IDS_FILE.read_text(encoding="utf-8"))
            return set(data)
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_processed_ids(ids: set[str]):
    """Persist processed IDs to disk. Keeps the last 1000 to prevent unbounded growth."""
    trimmed = list(ids)[-1000:]
    _PROCESSED_IDS_FILE.write_text(json.dumps(trimmed), encoding="utf-8")


def _classify_priority(subject: str, body_preview: str) -> str:
    """Classify email priority based on subject and body content."""
    combined = (subject + " " + body_preview).lower()
    if any(kw in combined for kw in _HIGH_PRIORITY_KEYWORDS):
        return "high"
    if any(kw in combined for kw in _MEDIUM_PRIORITY_KEYWORDS):
        return "medium"
    return "low"


def _decode_body_part(part: dict) -> str:
    """Decode a single MIME body part from base64url."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_plain_text(payload: dict) -> str:
    """Walk a MIME payload tree and return the first text/plain part."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        return _decode_body_part(payload)

    if mime_type == "text/html":
        # Fall back: strip HTML tags if no plain text found
        html = _decode_body_part(payload)
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
        except ImportError:
            return re.sub(r"<[^>]+>", "", html)

    parts = payload.get("parts", [])
    # Prefer text/plain over text/html in multipart
    for part in parts:
        if part.get("mimeType") == "text/plain":
            text = _extract_plain_text(part)
            if text:
                return text
    for part in parts:
        text = _extract_plain_text(part)
        if text:
            return text

    return ""


def _truncate(text: str, max_chars: int = 800) -> str:
    """Truncate text and add ellipsis if needed."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...(truncated)"


# Both read and send scopes — token must be created with these via setup_gmail_auth.py
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _build_gmail_service():
    """Build and return an authenticated Gmail API service.

    Raises FileNotFoundError if credentials or token files are missing.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = config.gmail_token_path

    if not token_path.exists():
        raise FileNotFoundError(
            f"Gmail token not found at {token_path}. "
            "Run 'uv run python setup_gmail_auth.py' first."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), scopes=GMAIL_SCOPES)

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Gmail token refreshed")

    return build("gmail", "v1", credentials=creds)


class GmailWatcher(BaseWatcher):
    """Polls Gmail for unread important emails and creates Needs_Action files.

    Extends BaseWatcher using the Gmail REST API.
    """

    def __init__(self):
        super().__init__(check_interval=config.gmail_check_interval)
        self._processed_ids: set[str] = _load_processed_ids()
        self._service = None  # lazy-initialised in on_start()

    def on_start(self):
        """Authenticate with Gmail API on startup."""
        try:
            self._service = _build_gmail_service()
            logger.info("Gmail API authenticated successfully")
            audit_log("gmail_auth", "GmailWatcher", result="success")
        except FileNotFoundError as exc:
            logger.error(str(exc))
            audit_log("gmail_auth", "GmailWatcher", result="error", parameters={"error": str(exc)})
            raise

    def on_stop(self):
        """Persist processed IDs on shutdown."""
        _save_processed_ids(self._processed_ids)
        logger.info(f"Gmail processed IDs saved ({len(self._processed_ids)} total)")

    def check_for_updates(self) -> list:
        """Return a list of new Gmail message metadata dicts.

        Retries up to 3 times on transient network errors (e.g. connection reset).
        """
        if self._service is None:
            return []

        last_exc = None
        for attempt in range(3):
            try:
                result = (
                    self._service.users()
                    .messages()
                    .list(
                        userId="me",
                        q=config.gmail_query,
                        maxResults=config.gmail_max_results,
                    )
                    .execute()
                )
                messages = result.get("messages", [])
                new_messages = [m for m in messages if m["id"] not in self._processed_ids]
                if new_messages:
                    logger.info(f"Gmail: {len(new_messages)} new message(s) found")
                else:
                    logger.debug(f"Gmail: no new messages (query: {config.gmail_query!r})")
                return new_messages

            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(f"Gmail API error (attempt {attempt + 1}/3): {exc} — retrying in {wait}s")
                import time
                time.sleep(wait)

        logger.error(f"Gmail API failed after 3 attempts: {last_exc}")
        audit_log("gmail_fetch_error", "GmailWatcher", {"error": str(last_exc)}, result="error")
        return []

    def create_action_file(self, message: dict) -> Path:
        """Fetch full email content and write a Needs_Action .md file."""
        msg_id = message["id"]

        # Fetch full message
        full_msg = (
            self._service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )

        # Extract headers
        headers: dict[str, str] = {
            h["name"]: h["value"]
            for h in full_msg.get("payload", {}).get("headers", [])
        }
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "Unknown")
        date_str = headers.get("Date", "")
        message_id_header = headers.get("Message-ID", "")

        # Extract body
        body_text = _extract_plain_text(full_msg.get("payload", {}))
        if not body_text:
            body_text = full_msg.get("snippet", "")

        body_preview = _truncate(body_text)
        priority = _classify_priority(subject, body_preview)

        # Mark as processed before writing (idempotent)
        self._processed_ids.add(msg_id)
        _save_processed_ids(self._processed_ids)

        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%d")
        safe_id = re.sub(r"[^\w]", "", msg_id)[:16]
        filename = f"EMAIL_{safe_id}_{timestamp}.md"
        action_path = config.needs_action_path / filename

        frontmatter = {
            "type": "email",
            "gmail_id": msg_id,
            "message_id_header": message_id_header,
            "from": sender,
            "subject": subject,
            "received": date_str,
            "priority": priority,
            "status": "pending",
            "created": now.isoformat(),
            "requires_approval": True,
        }

        body_lines = [
            f"# Email: {subject}",
            "",
            f"**From:** {sender}",
            f"**Date:** {date_str}",
            f"**Priority:** {priority.upper()}",
            "",
            "## Email Body",
            "",
            body_preview,
            "",
            "## Suggested Actions",
            "- [ ] Review email content",
            "- [ ] Draft reply (saved to `/Plans/`)",
            "- [ ] Send reply (requires human approval in `/Pending_Approval/`)",
            "- [ ] Archive / move to Done",
            "",
            "## Notes",
            "> Add any notes or context here before approving a reply.",
        ]

        write_markdown(action_path, frontmatter, "\n".join(body_lines))
        audit_log(
            "gmail_email_captured",
            filename,
            {"from": sender, "subject": subject, "priority": priority},
        )

        # Update dashboard
        pending = len(list_needs_action())
        inbox = len(list_folder(config.inbox_path))
        update_dashboard(pending, 0, inbox, watcher_status="Online (Gmail)")

        return action_path


def main():
    """Entry point for running the Gmail watcher as a standalone daemon.

    Runs indefinitely, polling Gmail every GMAIL_CHECK_INTERVAL seconds.
    New emails matching GMAIL_QUERY are written to vault/Needs_Action/ as
    EMAIL_*.md files automatically — no manual invocation needed.

    First-time setup:
        uv run python setup_gmail_auth.py
    """
    setup_logging()
    config.ensure_directories()

    # Pre-flight check: token must exist before starting the daemon
    if not config.gmail_token_path.exists():
        print()
        print("  ERROR: Gmail token not found.")
        print(f"  Expected: {config.gmail_token_path}")
        print()
        print("  Run first-time setup:")
        print("    uv run python setup_gmail_auth.py")
        print()
        raise SystemExit(1)

    print("=" * 55)
    print("  AI Employee — Gmail Watcher Daemon (Silver)")
    print("=" * 55)
    print(f"  Vault:     {config.vault_path}")
    print(f"  Query:     {config.gmail_query}")
    print(f"  Interval:  {config.gmail_check_interval}s")
    print(f"  Dry Run:   {config.dry_run}")
    print("=" * 55)
    print()
    print("  Running. New emails → vault/Needs_Action/ automatically.")
    print("  Press Ctrl+C to stop.")
    print()

    watcher = GmailWatcher()
    watcher.run()


if __name__ == "__main__":
    main()
