"""File System Watcher — monitors a drop folder for new files.

Uses the `watchdog` library for real-time file system events.
When a file is dropped into the drop folder, this watcher:
  1. Detects the new file via watchdog event
  2. Copies it to vault/Inbox/
  3. Creates a metadata .md file in vault/Needs_Action/

Usage:
    python -m src.watchers.filesystem_watcher
"""

import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from src.core.config import config
from src.utils.logger import audit_log, setup_logging
from src.core.vault_manager import write_markdown, update_dashboard, list_needs_action, list_folder

logger = setup_logging()

# Track processed files to avoid duplicates
_processed_files: set[str] = set()


def _classify_priority(filename: str, content: str = "") -> str:
    """Classify file priority based on keywords in filename or content."""
    combined = (filename + " " + content).lower()
    high_keywords = ["urgent", "asap", "critical", "emergency"]
    medium_keywords = ["invoice", "payment", "bill", "deadline", "important"]

    if any(kw in combined for kw in high_keywords):
        return "high"
    if any(kw in combined for kw in medium_keywords):
        return "medium"
    return "low"


def _detect_file_type(filepath: Path) -> str:
    """Map file extension to a human-readable type."""
    ext_map = {
        ".md": "markdown",
        ".txt": "text",
        ".csv": "data",
        ".pdf": "document",
        ".json": "data",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
    }
    return ext_map.get(filepath.suffix.lower(), "file")


def _create_action_for_file(source: Path):
    """Create a Needs_Action .md file for a dropped file."""
    if source.name in _processed_files:
        return
    if source.name.startswith(".") or source.name == ".gitkeep":
        return

    _processed_files.add(source.name)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d")

    # Read content for text-based files
    content_preview = ""
    if source.suffix.lower() in (".md", ".txt", ".csv", ".json"):
        try:
            raw = source.read_text(encoding="utf-8")
            content_preview = raw[:500]  # first 500 chars
        except (UnicodeDecodeError, OSError):
            content_preview = "(binary or unreadable)"

    priority = _classify_priority(source.name, content_preview)
    file_type = _detect_file_type(source)

    # Copy original file to Inbox
    inbox_dest = config.inbox_path / source.name
    if inbox_dest.exists():
        stem = inbox_dest.stem
        suffix = inbox_dest.suffix
        ts = now.strftime("%H%M%S")
        inbox_dest = config.inbox_path / f"{stem}_{ts}{suffix}"

    shutil.copy2(str(source), str(inbox_dest))
    audit_log("file_copy", str(inbox_dest), {"source": str(source)})

    # Create action file in Needs_Action
    action_filename = f"FILE_{source.stem}_{timestamp}.md"
    action_path = config.needs_action_path / action_filename

    frontmatter = {
        "type": "file_drop",
        "source": str(source),
        "original_name": source.name,
        "file_type": file_type,
        "size_bytes": source.stat().st_size,
        "priority": priority,
        "status": "pending",
        "created": now.isoformat(),
    }

    body_lines = [
        f"# File Drop: {source.name}",
        "",
        f"A new file was detected in the drop folder.",
        "",
        "## File Details",
        f"- **Name:** {source.name}",
        f"- **Type:** {file_type}",
        f"- **Size:** {source.stat().st_size:,} bytes",
        f"- **Priority:** {priority}",
        f"- **Inbox Copy:** `{inbox_dest.name}`",
        "",
    ]

    if content_preview:
        body_lines.extend([
            "## Content Preview",
            "```",
            content_preview,
            "```",
            "",
        ])

    body_lines.extend([
        "## Suggested Actions",
        "- [ ] Review file content",
        "- [ ] Process or categorize",
        "- [ ] Move to Done when complete",
    ])

    write_markdown(action_path, frontmatter, "\n".join(body_lines))
    logger.info(f"Action file created: {action_filename} (priority={priority})")

    # Update dashboard
    pending = len(list_needs_action())
    inbox = len(list_folder(config.inbox_path))
    done_today_count = len([
        f for f in list_folder(config.done_path)
        if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).date() == now.date()
    ])
    update_dashboard(pending, done_today_count, inbox, watcher_status="Online")


class _DropFolderHandler(FileSystemEventHandler):
    """Watchdog event handler for the drop folder."""

    def on_created(self, event):
        if event.is_directory:
            return
        source = Path(event.src_path)
        # Small delay to ensure file write is complete
        import time
        time.sleep(0.5)
        if source.exists():
            logger.info(f"New file detected: {source.name}")
            _create_action_for_file(source)


class FileSystemWatcher:
    """Watches a drop folder for new files using watchdog.

    This is the Bronze tier's primary perception component.
    """

    def __init__(self):
        self.drop_folder = config.drop_folder_path
        self.observer = Observer()
        self._handler = _DropFolderHandler()
        self.logger = logging.getLogger(self.__class__.__name__)

    def start(self):
        """Start watching the drop folder."""
        self.drop_folder.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(self._handler, str(self.drop_folder), recursive=False)
        self.observer.start()
        self.logger.info(f"FileSystemWatcher started — watching: {self.drop_folder}")
        audit_log("watcher_start", "FileSystemWatcher", {"path": str(self.drop_folder)})

        # Update dashboard to show online status
        pending = len(list_needs_action())
        inbox = len(list_folder(config.inbox_path))
        update_dashboard(pending, 0, inbox, watcher_status="Online")

    def stop(self):
        """Stop the watcher."""
        self.observer.stop()
        self.observer.join()
        self.logger.info("FileSystemWatcher stopped")
        audit_log("watcher_stop", "FileSystemWatcher")

    def run_forever(self):
        """Start and block until KeyboardInterrupt."""
        self.start()
        try:
            while self.observer.is_alive():
                self.observer.join(timeout=1)
        except KeyboardInterrupt:
            self.logger.info("Shutting down FileSystemWatcher...")
        finally:
            self.stop()


def main():
    """Entry point for running the file system watcher standalone."""
    setup_logging()
    config.ensure_directories()
    watcher = FileSystemWatcher()
    print(f"\n  AI Employee — File System Watcher (Bronze)")
    print(f"  Watching: {config.drop_folder_path}")
    print(f"  Vault:    {config.vault_path}")
    print(f"  Dry Run:  {config.dry_run}")
    print(f"\n  Drop files into the folder above. Press Ctrl+C to stop.\n")
    watcher.run_forever()


if __name__ == "__main__":
    main()
