"""LinkedIn Watcher — monitors LinkedIn messages and notifications via Playwright.

Uses a persistent browser context (saved session) to monitor:
  - LinkedIn Messaging for unread message threads
  - LinkedIn Notifications for mentions, comments, connection requests

When items are detected, writes .md files to /Needs_Action/ for Claude to process.
Also handles publishing queued posts (queued by ApprovalWatcher after human approval).

Setup (one-time):
    Run setup_linkedin_session.py to log in and save the browser session.

Usage:
    Runs automatically as part of the orchestrator.
    Or standalone: uv run python -m src.watchers.linkedin_watcher
"""

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.core.config import config
from src.core.vault_manager import (
    list_folder,
    list_needs_action,
    update_dashboard,
    write_markdown,
)
from src.utils.logger import audit_log, setup_logging
from src.watchers.base_watcher import BaseWatcher

logger = setup_logging()

# Persist processed item IDs across restarts
_PROCESSED_IDS_FILE = config.silver_dir / ".linkedin_processed_ids.json"
# File-based queue for approved posts (written by ApprovalWatcher, read by LinkedInWatcher)
_PENDING_POSTS_FILE = config.silver_dir / ".linkedin_pending_posts.json"
# Thread lock protects the queue file from concurrent read/write
_queue_lock = threading.Lock()

_MAX_ITEMS_PER_CYCLE = 5

_HIGH_PRIORITY_KEYWORDS = [
    "urgent", "asap", "critical", "invoice", "payment",
    "partnership", "proposal", "contract", "collaboration",
]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _load_processed_ids() -> set[str]:
    if _PROCESSED_IDS_FILE.exists():
        try:
            return set(json.loads(_PROCESSED_IDS_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_processed_ids(ids: set[str]):
    """Keep at most 2000 IDs to prevent unbounded growth."""
    trimmed = list(ids)[-2000:]
    _PROCESSED_IDS_FILE.write_text(json.dumps(trimmed), encoding="utf-8")


def _make_id(text: str) -> str:
    """Generate a stable 12-char ID from text content."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _classify_priority(text: str) -> str:
    lowered = text.lower()
    if any(kw in lowered for kw in _HIGH_PRIORITY_KEYWORDS):
        return "high"
    return "medium"


def queue_linkedin_post(content: str, topic: str = "", post_id: str = ""):
    """Write a post to the thread-safe file queue for the watcher to publish.

    Called by ApprovalWatcher when a linkedin_post approval is processed.
    The LinkedInWatcher picks this up on its next check_for_updates() cycle.
    """
    with _queue_lock:
        pending = []
        if _PENDING_POSTS_FILE.exists():
            try:
                pending = json.loads(_PENDING_POSTS_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pending = []
        pending.append({
            "content": content,
            "topic": topic,
            "post_id": post_id,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        })
        _PENDING_POSTS_FILE.write_text(json.dumps(pending, indent=2), encoding="utf-8")
    logger.info(f"LinkedIn post queued for publishing (topic: {topic!r})")


def _consume_pending_posts() -> list[dict]:
    """Atomically read and clear all pending posts from the file queue."""
    with _queue_lock:
        if not _PENDING_POSTS_FILE.exists():
            return []
        try:
            posts = json.loads(_PENDING_POSTS_FILE.read_text(encoding="utf-8"))
            _PENDING_POSTS_FILE.unlink(missing_ok=True)
            return posts
        except (json.JSONDecodeError, OSError):
            return []


# ---------------------------------------------------------------------------
# Playwright helpers — shared between watcher and standalone publisher
# ---------------------------------------------------------------------------

def _is_logged_in(page) -> bool:
    """Return True if the current page shows an authenticated LinkedIn session."""
    url = page.url
    if any(kw in url for kw in ("login", "authwall", "checkpoint", "uas/authenticate")):
        logger.warning("LinkedIn session expired — run 'uv run python setup_linkedin_session.py'")
        audit_log("linkedin_session_expired", "LinkedInWatcher", result="error")
        return False
    return True


def _find_element(page, selectors: list, description: str):
    """Try selectors in order and return the first visible element found."""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return el
        except Exception:
            continue
    logger.error(f"LinkedIn: could not find {description!r} — tried {len(selectors)} selectors")
    return None


def _post_on_page(page, content: str) -> bool:
    """Core posting logic — shared by both the watcher and standalone publisher.

    Navigates to LinkedIn feed, clicks 'Start a post', types content, and submits.
    Uses multiple selector fallbacks since LinkedIn's DOM changes frequently.
    Returns True on success.
    """
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(2_000)

    if not _is_logged_in(page):
        return False

    # --- Step 1: Click "Start a post" ---
    start_btn = _find_element(page, [
        "[aria-label='Start a post']",
        "button.share-box-feed-entry__trigger",
        ".share-box-feed-entry__trigger",
        "span:has-text('Start a post')",
        "button:has-text('Start a post')",
        "[data-test-id='create-post-button']",
    ], "Start a post button")
    if start_btn is None:
        return False

    start_btn.click()
    page.wait_for_timeout(2_000)

    # --- Step 2: Find the rich-text post editor ---
    editor = _find_element(page, [
        "div.ql-editor[contenteditable='true']",
        "[role='textbox']",
        "div[contenteditable='true']",
        "[aria-label*='post'][contenteditable]",
        "[aria-label*='content'][contenteditable]",
    ], "post editor")
    if editor is None:
        return False

    editor.click()
    page.wait_for_timeout(500)

    # Type with a 30ms delay — gives LinkedIn's rich text editor time to register each key
    page.keyboard.type(content, delay=30)
    page.wait_for_timeout(1_000)

    # --- Validate content was actually entered ---
    try:
        typed_text = editor.inner_text()
        if len(typed_text.strip()) < 10:
            logger.error(
                f"LinkedIn editor appears empty after typing "
                f"(got {len(typed_text.strip())} chars). Aborting."
            )
            return False
        logger.debug(f"LinkedIn editor has {len(typed_text)} chars — looks good")
    except Exception as exc:
        logger.warning(f"Could not validate editor content: {exc}")

    # --- Step 3: Click the "Post" submit button ---
    post_btn = _find_element(page, [
        "button.share-actions__primary-action",
        "button[aria-label='Post']",
        "button:has-text('Post')",
        "[data-test-id='post-button']",
    ], "Post submit button")
    if post_btn is None:
        return False

    post_btn.click()
    page.wait_for_timeout(3_000)

    logger.info("LinkedIn post submitted via Playwright")
    return True


def publish_linkedin_post(content: str, session_path: Path, headless: bool = True) -> bool:
    """Publish a LinkedIn post using a standalone Playwright context.

    Opens a temporary persistent context (using the saved session cookies),
    posts the content, then closes. Use this when LinkedInWatcher is NOT running.

    Args:
        content:      Plain-text post content (no markdown).
        session_path: Path to the saved Chromium user-data-dir.
        headless:     False = visible browser window.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: uv add playwright && uv run playwright install chromium")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(session_path),
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page()
        try:
            return _post_on_page(page, content)
        except Exception as exc:
            logger.error(f"LinkedIn post publishing error: {exc}")
            return False
        finally:
            page.close()
            browser.close()


# ---------------------------------------------------------------------------
# LinkedInWatcher
# ---------------------------------------------------------------------------

class LinkedInWatcher(BaseWatcher):
    """Playwright-based watcher for LinkedIn messages, notifications, and post publishing.

    Uses a persistent browser context so the LinkedIn login session is maintained.

    First-time setup:
        uv run python setup_linkedin_session.py
    """

    def __init__(self):
        super().__init__(check_interval=config.linkedin_check_interval)
        self._processed_ids: set[str] = _load_processed_ids()
        self._pw_ctx = None   # SyncPlaywrightContextManager (for cleanup)
        self._pw = None       # Playwright instance
        self._browser = None  # Persistent browser context

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self):
        """Launch persistent browser context with saved LinkedIn session."""
        if not config.linkedin_session_path.exists():
            raise FileNotFoundError(
                f"LinkedIn session not found at {config.linkedin_session_path}. "
                "Run 'uv run python setup_linkedin_session.py' first."
            )

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright not installed. "
                "Run: uv add playwright && uv run playwright install chromium"
            )

        self._pw_ctx = sync_playwright()
        self._pw = self._pw_ctx.__enter__()
        self._browser = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(config.linkedin_session_path),
            headless=config.linkedin_headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        logger.info(f"LinkedIn browser started (headless={config.linkedin_headless})")
        audit_log("linkedin_browser_start", "LinkedInWatcher", result="success")

    def on_stop(self):
        """Close browser and persist processed IDs."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw_ctx:
            try:
                self._pw_ctx.__exit__(None, None, None)
            except Exception:
                pass
        _save_processed_ids(self._processed_ids)
        logger.info(f"LinkedIn watcher stopped, {len(self._processed_ids)} IDs saved")

    # ------------------------------------------------------------------
    # BaseWatcher interface
    # ------------------------------------------------------------------

    def check_for_updates(self) -> list:
        """Check LinkedIn for new messages, notifications, and publish queued posts."""
        if self._browser is None:
            return []

        # 1. Publish any posts approved while we were sleeping
        pending_posts = _consume_pending_posts()
        for post in pending_posts:
            self._publish_queued_post(post)

        # 2. Check messages and notifications
        items: list[dict] = []
        try:
            items.extend(self._check_messages())
        except Exception as exc:
            logger.error(f"LinkedIn message check error: {exc}")
            audit_log("linkedin_messages_error", "LinkedInWatcher", {"error": str(exc)}, result="error")

        try:
            items.extend(self._check_notifications())
        except Exception as exc:
            logger.error(f"LinkedIn notification check error: {exc}")
            audit_log("linkedin_notifications_error", "LinkedInWatcher", {"error": str(exc)}, result="error")

        return items

    def create_action_file(self, item: dict) -> Path:
        """Write a Needs_Action .md file for a LinkedIn message or notification."""
        item_type = item.get("type", "linkedin")
        item_id = item.get("id", _make_id(str(item)))
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%d")

        if item_type == "linkedin_message":
            sender = item.get("sender", "Unknown")
            preview = item.get("preview", "")
            url = item.get("url", "")
            priority = _classify_priority(preview)

            filename = f"LINKEDIN_MSG_{item_id}_{timestamp}.md"
            frontmatter = {
                "type": "linkedin_message",
                "linkedin_thread_id": item_id,
                "from": sender,
                "url": url,
                "priority": priority,
                "status": "pending",
                "created": now.isoformat(),
                "requires_approval": True,
            }
            body = "\n".join([
                f"# LinkedIn Message from {sender}",
                "",
                f"**From:** {sender}",
                f"**Priority:** {priority.upper()}",
                f"**Thread URL:** {url}",
                "",
                "## Message Preview",
                "",
                preview,
                "",
                "## Suggested Actions",
                "- [ ] Review message",
                "- [ ] Draft reply (save to `/Plans/PLAN_linkedin_reply_<id>.md`)",
                "- [ ] Create approval request in `/Pending_Approval/` before replying",
                "",
                "## Notes",
                "> Add context or reply draft here.",
            ])

        elif item_type == "linkedin_notification":
            text = item.get("text", "")
            url = item.get("url", "")
            priority = _classify_priority(text)

            filename = f"LINKEDIN_NOTIF_{item_id}_{timestamp}.md"
            frontmatter = {
                "type": "linkedin_notification",
                "linkedin_notif_id": item_id,
                "url": url,
                "priority": priority,
                "status": "pending",
                "created": now.isoformat(),
                "requires_approval": False,
            }
            body = "\n".join([
                "# LinkedIn Notification",
                "",
                f"**Priority:** {priority.upper()}",
                f"**URL:** {url}",
                "",
                "## Notification Content",
                "",
                text,
                "",
                "## Suggested Actions",
                "- [ ] Review and take action if needed",
                "- [ ] Archive after handling",
            ])

        else:
            filename = f"LINKEDIN_{item_id}_{timestamp}.md"
            frontmatter = {"type": "linkedin", "priority": "low", "status": "pending", "created": now.isoformat()}
            body = str(item)

        action_path = config.needs_action_path / filename
        write_markdown(action_path, frontmatter, body)

        # Mark processed
        self._processed_ids.add(item_id)
        _save_processed_ids(self._processed_ids)

        audit_log("linkedin_item_captured", filename, {"type": item_type, "id": item_id})

        # Update dashboard
        pending = len(list_needs_action())
        inbox = len(list_folder(config.inbox_path))
        update_dashboard(pending, 0, inbox, watcher_status="Online (LinkedIn)")

        return action_path

    # ------------------------------------------------------------------
    # Playwright: Monitor messages and notifications
    # ------------------------------------------------------------------

    def _check_messages(self) -> list[dict]:
        """Navigate to LinkedIn Messaging and return unread thread dicts."""
        page = self._browser.new_page()
        results: list[dict] = []
        try:
            page.goto(
                "https://www.linkedin.com/messaging/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            page.wait_for_timeout(3_000)

            if not _is_logged_in(page):
                return []

            unread_convs = []
            for sel in [
                "li.msg-conversation-listitem--is-unread",
                "[data-test-id='conversation-list-item'][aria-label*='unread']",
                ".msg-conversations-container__conversations-list li[aria-label*='unread']",
            ]:
                try:
                    unread_convs = page.query_selector_all(sel)
                    if unread_convs:
                        break
                except Exception:
                    continue

            if not unread_convs:
                logger.debug("LinkedIn: no unread messages")
                return []

            logger.info(f"LinkedIn: {len(unread_convs)} unread message thread(s)")

            for conv in unread_convs[:_MAX_ITEMS_PER_CYCLE]:
                try:
                    sender = "Unknown"
                    for sel in [
                        ".msg-conversation-listitem__participant-names",
                        ".msg-conversation-card__participant-name",
                        "[aria-label*='from']",
                    ]:
                        el = conv.query_selector(sel)
                        if el:
                            sender = el.inner_text().strip()
                            break

                    preview = ""
                    for sel in [
                        ".msg-conversation-card__message-snippet-body",
                        ".msg-conversation-card__message-snippet",
                        ".msg-conversation-listitem__message-snippet",
                    ]:
                        el = conv.query_selector(sel)
                        if el:
                            preview = el.inner_text().strip()
                            break

                    item_id = _make_id(sender + preview[:50])
                    if item_id in self._processed_ids:
                        continue

                    href = ""
                    link_el = conv.query_selector("a[href*='/messaging/thread/']")
                    if link_el:
                        href = link_el.get_attribute("href") or ""

                    results.append({
                        "type": "linkedin_message",
                        "id": item_id,
                        "sender": sender,
                        "preview": preview,
                        "url": f"https://www.linkedin.com{href}" if href.startswith("/") else href,
                    })
                except Exception as exc:
                    logger.debug(f"Error parsing LinkedIn conversation: {exc}")

        except Exception as exc:
            logger.error(f"LinkedIn messaging page error: {exc}")
        finally:
            page.close()

        return results

    def _check_notifications(self) -> list[dict]:
        """Navigate to LinkedIn Notifications and return unread notification dicts."""
        page = self._browser.new_page()
        results: list[dict] = []
        try:
            page.goto(
                "https://www.linkedin.com/notifications/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            page.wait_for_timeout(2_000)

            if not _is_logged_in(page):
                return []

            unread_notifs = []
            for sel in [
                ".nt-card--unread",
                "[data-urn][aria-label*='new']",
                ".artdeco-list__item.notification-item--unread",
            ]:
                try:
                    unread_notifs = page.query_selector_all(sel)
                    if unread_notifs:
                        break
                except Exception:
                    continue

            if not unread_notifs:
                logger.debug("LinkedIn: no unread notifications")
                return []

            logger.info(f"LinkedIn: {len(unread_notifs)} unread notification(s)")

            for notif in unread_notifs[:_MAX_ITEMS_PER_CYCLE]:
                try:
                    text = notif.inner_text().strip()
                    if not text:
                        continue

                    item_id = _make_id(text[:100])
                    if item_id in self._processed_ids:
                        continue

                    href = ""
                    link_el = notif.query_selector("a[href]")
                    if link_el:
                        href = link_el.get_attribute("href") or ""

                    results.append({
                        "type": "linkedin_notification",
                        "id": item_id,
                        "text": text[:400],
                        "url": f"https://www.linkedin.com{href}" if href.startswith("/") else href,
                    })
                except Exception as exc:
                    logger.debug(f"Error parsing LinkedIn notification: {exc}")

        except Exception as exc:
            logger.error(f"LinkedIn notifications page error: {exc}")
        finally:
            page.close()

        return results

    # ------------------------------------------------------------------
    # Playwright: Post publishing
    # ------------------------------------------------------------------

    def _publish_queued_post(self, post: dict):
        """Publish a single queued post using the existing browser context."""
        content = post.get("content", "")
        topic = post.get("topic", "")
        if not content:
            logger.warning("LinkedIn queued post has no content — skipping")
            return

        logger.info(f"LinkedIn: publishing queued post (topic: {topic!r})")
        audit_log("linkedin_post_start", "LinkedInWatcher", {"topic": topic})

        if config.dry_run:
            logger.info(f"[DRY RUN] Would publish LinkedIn post:\n{content[:200]}...")
            audit_log("linkedin_post_dry_run", "LinkedInWatcher", {"topic": topic, "preview": content[:200]})
            return

        page = self._browser.new_page()
        try:
            success = _post_on_page(page, content)
            result = "success" if success else "error"
            audit_log("linkedin_post_published", "LinkedInWatcher", {"topic": topic}, result=result)
            if not success:
                logger.error(f"LinkedIn post publishing failed (topic: {topic!r})")
        except Exception as exc:
            logger.error(f"LinkedIn post error: {exc}")
            audit_log("linkedin_post_error", "LinkedInWatcher", {"error": str(exc)}, result="error")
        finally:
            page.close()


def main():
    """Entry point for running the LinkedIn watcher as a standalone daemon."""
    setup_logging()
    config.ensure_directories()

    if not config.linkedin_session_path.exists():
        print()
        print("  ERROR: LinkedIn session not found.")
        print(f"  Expected: {config.linkedin_session_path}")
        print()
        print("  Run first-time setup:")
        print("    uv run python setup_linkedin_session.py")
        print()
        raise SystemExit(1)

    print("=" * 55)
    print("  AI Employee — LinkedIn Watcher Daemon (Silver)")
    print("=" * 55)
    print(f"  Vault:     {config.vault_path}")
    print(f"  Session:   {config.linkedin_session_path}")
    print(f"  Interval:  {config.linkedin_check_interval}s")
    print(f"  Headless:  {config.linkedin_headless}")
    print(f"  Dry Run:   {config.dry_run}")
    print("=" * 55)
    print()
    print("  Running. LinkedIn messages/notifications → vault/Needs_Action/ automatically.")
    print("  Press Ctrl+C to stop.")
    print()

    watcher = LinkedInWatcher()
    watcher.run()


if __name__ == "__main__":
    main()
