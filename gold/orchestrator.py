"""Orchestrator — Master process for the AI Employee Silver tier.

Responsibilities:
  1. Start and manage the File System Watcher (Bronze carry-over)
  2. Start and manage the Gmail Watcher (Silver new)
  3. Watch /Approved/ folder for human-approved HITL actions
  4. Schedule the Daily Briefing at a configured time
  5. Periodically scan /Needs_Action/ and update Dashboard.md
  6. Handle graceful shutdown

This is the single entry point for running the entire Silver system.
"""

import sys
import time
import signal
import shutil
import threading
from pathlib import Path
from datetime import datetime, timezone
import logging

# Ensure silver/ is on the path
_silver_dir = Path(__file__).resolve().parent
if str(_silver_dir) not in sys.path:
    sys.path.insert(0, str(_silver_dir))

from src.core.config import config
from src.core.vault_manager import (
    list_needs_action,
    list_folder,
    update_dashboard,
    read_frontmatter,
    write_markdown,
)
from src.utils.logger import setup_logging, audit_log
from src.watchers.filesystem_watcher import FileSystemWatcher
from src.watchers.gmail_watcher import GmailWatcher
from src.watchers.linkedin_watcher import LinkedInWatcher, queue_linkedin_post

logger = setup_logging()


# ---------------------------------------------------------------------------
# Approval watcher — watches /Approved/ and acts on approved HITL files
# ---------------------------------------------------------------------------

class ApprovalWatcher:
    """Watches /Approved/ for human-approved action files.

    When a file appears in /Approved/, this class:
      1. Reads the frontmatter to determine the action type
      2. Executes the appropriate action (or dry-runs it)
      3. Moves the file to /Done/
      4. Logs the outcome
    """

    def __init__(self, linkedin_watcher=None):
        self._running = False
        self._linkedin_watcher = linkedin_watcher  # may be None if session not set up

    def _handle_approved(self, filepath: Path):
        """Process a single approved action file."""
        try:
            fm, body = read_frontmatter(filepath)
        except Exception as exc:
            logger.error(f"Could not read approved file {filepath.name}: {exc}")
            return

        action_type = fm.get("action", fm.get("type", "unknown"))
        logger.info(f"Approved action detected: {action_type} ({filepath.name})")

        if config.dry_run:
            logger.info(f"[DRY RUN] Would execute: {action_type} — {filepath.name}")
            audit_log(
                "hitl_approved_dry_run",
                filepath.name,
                {"action": action_type, "frontmatter": fm},
                approval_status="approved",
                approved_by="human",
            )
        else:
            # Dispatch to the appropriate handler
            dispatched = self._dispatch(action_type, fm, body, filepath)
            if not dispatched:
                logger.warning(f"No handler for action type '{action_type}' — manual review needed")
                audit_log(
                    "hitl_no_handler",
                    filepath.name,
                    {"action": action_type},
                    result="warning",
                    approval_status="approved",
                    approved_by="human",
                )

        # Move to Done regardless (avoids re-processing)
        done_dest = config.done_path / filepath.name
        if done_dest.exists():
            ts = datetime.now(timezone.utc).strftime("%H%M%S")
            done_dest = config.done_path / f"{filepath.stem}_{ts}{filepath.suffix}"
        shutil.move(str(filepath), str(done_dest))
        audit_log("hitl_processed", str(done_dest), {"from": str(filepath)}, approval_status="approved", approved_by="human")

    def _dispatch(self, action_type: str, fm: dict, body: str, filepath: Path) -> bool:
        """Route an approved action to its handler. Returns True if handled."""
        if action_type in ("send_email", "email"):
            return self._handle_email(fm)
        if action_type in ("linkedin_post", "post_linkedin"):
            return self._handle_linkedin_post(fm, body)
        return False

    def _handle_email(self, fm: dict) -> bool:
        """Send an approved email reply via the Gmail API."""
        import base64
        from email.mime.text import MIMEText
        from src.watchers.gmail_watcher import _build_gmail_service

        to = fm.get("to", "")
        subject = fm.get("subject", "")
        body = fm.get("body", "")

        if not to:
            logger.error("Email action missing 'to' field")
            return False

        try:
            service = _build_gmail_service()

            mime_msg = MIMEText(body, "plain", "utf-8")
            mime_msg["to"] = to
            mime_msg["subject"] = subject

            raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
            service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()

            logger.info(f"Email sent to {to} — Subject: {subject}")
            audit_log(
                "email_send",
                to,
                {"subject": subject, "body_preview": body[:100]},
                approval_status="approved",
                approved_by="human",
                result="success",
            )
            return True

        except Exception as exc:
            logger.error(f"Failed to send email to {to}: {exc}")
            audit_log(
                "email_send",
                to,
                {"subject": subject, "error": str(exc)},
                approval_status="approved",
                approved_by="human",
                result="error",
            )
            return False

    def _handle_linkedin_post(self, fm: dict, body: str) -> bool:
        """Publish an approved LinkedIn post.

        Strategy:
          - If the LinkedInWatcher has an active browser (persistent context is open),
            use the file queue so the watcher publishes it — avoids two processes
            opening the same Chromium user_data_dir simultaneously.
          - If the watcher is NOT running (no browser, or watcher not initialised),
            publish directly using a temporary Playwright context.
        """
        from src.watchers.linkedin_watcher import publish_linkedin_post

        # Extract content — prefer YAML frontmatter 'content' field
        content = fm.get("content", "").strip()
        if not content:
            marker = "## Post Content"
            if marker in body:
                content = body.split(marker, 1)[1].strip()
            else:
                content = body.strip()

        topic = fm.get("topic", "")

        if not content:
            logger.error("LinkedIn post action has no content to publish")
            audit_log(
                "linkedin_post_dispatch",
                "ApprovalWatcher",
                {"error": "no content"},
                approval_status="approved",
                approved_by="human",
                result="error",
            )
            return False

        if config.dry_run:
            logger.info(f"[DRY RUN] Would publish LinkedIn post (topic: {topic!r}):\n{content[:200]}")
            audit_log(
                "linkedin_post_dry_run",
                "ApprovalWatcher",
                {"topic": topic, "preview": content[:200]},
                approval_status="approved",
                approved_by="human",
            )
            return True

        if not config.linkedin_session_path.exists():
            logger.error(
                "LinkedIn session not found. "
                "Run 'uv run python setup_linkedin_session.py' first, "
                "then re-approve this post."
            )
            audit_log(
                "linkedin_post_no_session",
                "ApprovalWatcher",
                {"topic": topic},
                result="error",
            )
            return False

        # Decide: queue (watcher has browser open) vs direct publish (no active context)
        watcher_has_browser = (
            self._linkedin_watcher is not None
            and getattr(self._linkedin_watcher, "_browser", None) is not None
        )

        if watcher_has_browser:
            # Watcher's persistent context is open — write to file queue.
            # The watcher picks this up on its next check_for_updates() cycle.
            queue_linkedin_post(content=content, topic=topic)
            logger.info(
                f"LinkedIn post queued — watcher will publish on next cycle "
                f"(~{config.linkedin_check_interval}s). Topic: {topic!r}"
            )
            audit_log(
                "linkedin_post_queued",
                "ApprovalWatcher",
                {"topic": topic, "preview": content[:200]},
                approval_status="approved",
                approved_by="human",
                result="queued",
            )
            return True
        else:
            # Watcher not running — publish directly with a temporary Playwright context.
            # Safe because no other process holds the user_data_dir lock.
            logger.info(f"LinkedIn watcher not active — publishing directly. Topic: {topic!r}")
            try:
                success = publish_linkedin_post(
                    content=content,
                    session_path=config.linkedin_session_path,
                    headless=config.linkedin_headless,
                )
                audit_log(
                    "linkedin_post_direct",
                    "ApprovalWatcher",
                    {"topic": topic, "preview": content[:200]},
                    approval_status="approved",
                    approved_by="human",
                    result="success" if success else "error",
                )
                if success:
                    logger.info(f"LinkedIn post published successfully (topic: {topic!r})")
                else:
                    logger.error(f"LinkedIn post publishing failed (topic: {topic!r})")
                return success
            except Exception as exc:
                logger.error(f"LinkedIn post publishing error: {exc}")
                audit_log(
                    "linkedin_post_error",
                    "ApprovalWatcher",
                    {"error": str(exc), "topic": topic},
                    result="error",
                )
                return False

    def run_forever(self, stop_event: threading.Event):
        """Poll /Approved/ in a loop until stop_event is set."""
        logger.info(f"ApprovalWatcher started (interval={config.approval_check_interval}s)")
        while not stop_event.is_set():
            try:
                approved_files = list_folder(config.approved_path)
                for filepath in approved_files:
                    self._handle_approved(filepath)
            except Exception as exc:
                logger.error(f"ApprovalWatcher error: {exc}")
            stop_event.wait(timeout=config.approval_check_interval)
        logger.info("ApprovalWatcher stopped")


# ---------------------------------------------------------------------------
# Daily Briefing Scheduler
# ---------------------------------------------------------------------------

class DailyBriefingScheduler:
    """Triggers a CEO Briefing generation task at the configured daily time."""

    def __init__(self):
        self._last_briefing_date: str | None = None

    def check_and_trigger(self):
        """Check if it's time to generate today's briefing."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        if (
            now.hour == config.daily_briefing_hour
            and now.minute == config.daily_briefing_minute
            and self._last_briefing_date != today
        ):
            self._last_briefing_date = today
            self._generate_briefing_task(now)

    def _generate_briefing_task(self, now: datetime):
        """Create a Needs_Action item to trigger Claude to write a CEO briefing."""
        filename = f"BRIEFING_REQUEST_{now.strftime('%Y-%m-%d')}.md"
        action_path = config.needs_action_path / filename

        if action_path.exists():
            return  # Already triggered today

        frontmatter = {
            "type": "briefing_request",
            "priority": "high",
            "status": "pending",
            "created": now.isoformat(),
            "target_date": now.strftime("%Y-%m-%d"),
        }
        body = f"""# Monday Morning CEO Briefing Request

Generate the weekly CEO briefing for **{now.strftime('%A, %B %d, %Y')}**.

## Instructions
1. Read `Business_Goals.md` for current targets and KPIs
2. Check `/Done/` for completed tasks this week
3. Check `/Accounting/` for financial data
4. Identify bottlenecks (tasks that took unusually long)
5. Suggest proactive cost optimisations
6. Write the briefing to `/Briefings/{now.strftime('%Y-%m-%d')}_Briefing.md`

## Required Sections
- Executive Summary
- Revenue vs Target
- Completed Tasks
- Bottlenecks
- Proactive Suggestions
- Upcoming Deadlines
"""
        write_markdown(action_path, frontmatter, body)
        logger.info(f"Daily briefing task created: {filename}")
        audit_log("briefing_scheduled", filename, {"date": now.strftime("%Y-%m-%d")})


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

class SilverOrchestrator:
    """Master orchestrator for the Silver tier AI Employee."""

    def __init__(self):
        self._running = False
        self._stop_event = threading.Event()
        self._scan_interval = config.watcher_interval * 2

        self._fs_watcher = FileSystemWatcher()
        self._gmail_watcher: GmailWatcher | None = None
        self._linkedin_watcher: LinkedInWatcher | None = None
        self._briefing_scheduler = DailyBriefingScheduler()

        # Try to init Gmail watcher; skip gracefully if not configured
        try:
            self._gmail_watcher = GmailWatcher()
        except Exception as exc:
            logger.warning(f"Gmail watcher not available: {exc} — run setup_gmail_auth.py first")

        # Try to init LinkedIn watcher; skip gracefully if session not configured
        try:
            self._linkedin_watcher = LinkedInWatcher()
        except Exception as exc:
            logger.warning(f"LinkedIn watcher not available: {exc} — run setup_linkedin_session.py first")

        # ApprovalWatcher is created AFTER watchers so it can receive the LinkedIn reference.
        # This is critical — the LinkedIn post handler needs to know if the watcher's
        # browser is active before deciding to queue vs. publish directly.
        self._approval_watcher = ApprovalWatcher(linkedin_watcher=self._linkedin_watcher)

    def _signal_handler(self, signum, frame):
        logger.info("Shutdown signal received, stopping...")
        self._running = False
        self._stop_event.set()

    def _scan_cycle(self):
        """Run a single scan cycle: triage folders and update dashboard."""
        now = datetime.now(timezone.utc)
        pending_items = list_needs_action()
        inbox_items = list_folder(config.inbox_path)
        done_items = list_folder(config.done_path)

        done_today = len([
            f for f in done_items
            if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).date() == now.date()
        ])

        if pending_items:
            logger.info(
                f"Scan: {len(pending_items)} pending, "
                f"{len(inbox_items)} inbox, {done_today} done today"
            )
            for item in pending_items:
                fm, _ = read_frontmatter(item)
                if fm.get("priority") == "high":
                    logger.warning(f"HIGH PRIORITY: {item.name}")

        # Check if briefing should be triggered
        self._briefing_scheduler.check_and_trigger()

        # Build watcher status string
        watchers = ["FileSystem"]
        if self._gmail_watcher is not None:
            watchers.append("Gmail")
        if self._linkedin_watcher is not None:
            watchers.append("LinkedIn")
        watcher_status = "Online (" + ", ".join(watchers) + ")"

        update_dashboard(
            pending_count=len(pending_items),
            done_today=done_today,
            inbox_count=len(inbox_items),
            watcher_status=watcher_status,
        )

    def _start_watchers(self):
        """Start all watchers in background daemon threads."""
        # File system watcher (event-driven, uses watchdog)
        fs_thread = threading.Thread(target=self._fs_watcher.start, name="FileSystemWatcher", daemon=True)
        fs_thread.start()
        logger.info("FileSystem watcher started")

        # Gmail watcher (polling loop)
        if self._gmail_watcher is not None:
            def _gmail_run():
                try:
                    self._gmail_watcher.run()
                except Exception as exc:
                    logger.error(f"Gmail watcher crashed: {exc}")

            gmail_thread = threading.Thread(target=_gmail_run, name="GmailWatcher", daemon=True)
            gmail_thread.start()
            logger.info("Gmail watcher started")

        # LinkedIn watcher (polling loop with Playwright)
        if self._linkedin_watcher is not None:
            def _linkedin_run():
                try:
                    self._linkedin_watcher.run()
                except Exception as exc:
                    logger.error(f"LinkedIn watcher crashed: {exc}")

            linkedin_thread = threading.Thread(target=_linkedin_run, name="LinkedInWatcher", daemon=True)
            linkedin_thread.start()
            logger.info("LinkedIn watcher started")

        # Approval watcher
        approval_thread = threading.Thread(
            target=self._approval_watcher.run_forever,
            args=(self._stop_event,),
            name="ApprovalWatcher",
            daemon=True,
        )
        approval_thread.start()
        logger.info("Approval watcher started")

    def run(self):
        """Start the orchestrator and all managed processes."""
        config.ensure_directories()

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        print("=" * 60)
        print("  AI Employee — Silver Orchestrator")
        print("=" * 60)
        print(f"  Vault:         {config.vault_path}")
        print(f"  Drop Folder:   {config.drop_folder_path}")
        print(f"  Gmail:         {'Enabled' if self._gmail_watcher else 'Disabled (run setup_gmail_auth.py)'}")
        print(f"  LinkedIn:      {'Enabled' if self._linkedin_watcher else 'Disabled (run setup_linkedin_session.py)'}")
        print(f"  Briefing:      Daily at {config.daily_briefing_hour:02d}:{config.daily_briefing_minute:02d} UTC")
        print(f"  Scan Interval: {self._scan_interval}s")
        print(f"  Dry Run:       {config.dry_run}")
        print("=" * 60)
        print()

        audit_log("orchestrator_start", "SilverOrchestrator")
        self._start_watchers()

        self._running = True
        try:
            while self._running:
                self._scan_cycle()
                for _ in range(self._scan_interval):
                    if not self._running:
                        break
                    time.sleep(1)
        finally:
            logger.info("Stopping orchestrator...")
            self._stop_event.set()
            self._fs_watcher.stop()
            if self._gmail_watcher is not None:
                self._gmail_watcher.stop()
            if self._linkedin_watcher is not None:
                self._linkedin_watcher.stop()
            update_dashboard(0, 0, 0, watcher_status="Offline")
            audit_log("orchestrator_stop", "SilverOrchestrator")
            print("\n  AI Employee stopped. Goodbye.\n")


def main():
    orchestrator = SilverOrchestrator()
    orchestrator.run()


if __name__ == "__main__":
    main()
