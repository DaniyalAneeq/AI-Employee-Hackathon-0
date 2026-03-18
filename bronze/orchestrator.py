"""Orchestrator — Master process for the AI Employee Bronze tier.

Responsibilities:
  1. Start and manage the File System Watcher
  2. Periodically scan /Needs_Action/ and trigger processing
  3. Watch /Approved/ folder for human-approved actions
  4. Update Dashboard.md on each cycle
  5. Handle graceful shutdown

This is the single entry point for running the entire Bronze system.
"""

import sys
import time
import signal
import threading
from pathlib import Path
from datetime import datetime, timezone

# Ensure bronze/ is on the path
bronze_dir = Path(__file__).resolve().parent
if str(bronze_dir) not in sys.path:
    sys.path.insert(0, str(bronze_dir))

from src.core.config import config
from src.core.vault_manager import (
    list_needs_action,
    list_folder,
    update_dashboard,
    read_frontmatter,
)
from src.utils.logger import setup_logging, audit_log
from src.watchers.filesystem_watcher import FileSystemWatcher

logger = setup_logging()


class Orchestrator:
    """Master orchestrator for the Bronze tier AI Employee."""

    def __init__(self):
        self.watcher = FileSystemWatcher()
        self._running = False
        self._scan_interval = config.watcher_interval * 2  # scan less frequently than watcher

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received, stopping...")
        self._running = False

    def _scan_cycle(self):
        """Run a single scan cycle: check folders and update dashboard."""
        now = datetime.now(timezone.utc)

        # Count items across folders
        pending_items = list_needs_action()
        inbox_items = list_folder(config.inbox_path)
        done_items = list_folder(config.done_path)

        # Count items done today
        done_today = len([
            f for f in done_items
            if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).date() == now.date()
        ])

        # Log summary if there are pending items
        if pending_items:
            logger.info(
                f"Scan: {len(pending_items)} pending, "
                f"{len(inbox_items)} inbox, "
                f"{done_today} done today"
            )
            # List high priority items
            for item in pending_items:
                fm, _ = read_frontmatter(item)
                if fm.get("priority") == "high":
                    logger.warning(f"HIGH PRIORITY: {item.name}")

        # Update dashboard
        update_dashboard(
            pending_count=len(pending_items),
            done_today=done_today,
            inbox_count=len(inbox_items),
            watcher_status="Online",
        )

    def run(self):
        """Start the orchestrator and all managed processes."""
        config.ensure_directories()

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        print("=" * 55)
        print("  AI Employee — Bronze Orchestrator")
        print("=" * 55)
        print(f"  Vault:        {config.vault_path}")
        print(f"  Drop Folder:  {config.drop_folder_path}")
        print(f"  Scan Interval: {self._scan_interval}s")
        print(f"  Dry Run:      {config.dry_run}")
        print("=" * 55)
        print()

        audit_log("orchestrator_start", "Orchestrator")

        # Start file system watcher in a separate thread
        watcher_thread = threading.Thread(target=self.watcher.start, daemon=True)
        watcher_thread.start()
        logger.info("File System Watcher started in background")

        self._running = True
        try:
            while self._running:
                self._scan_cycle()
                # Sleep in small increments so we can respond to shutdown quickly
                for _ in range(self._scan_interval):
                    if not self._running:
                        break
                    time.sleep(1)
        finally:
            logger.info("Stopping orchestrator...")
            self.watcher.stop()
            update_dashboard(0, 0, 0, watcher_status="Offline")
            audit_log("orchestrator_stop", "Orchestrator")
            print("\n  AI Employee stopped. Goodbye.\n")


def main():
    orchestrator = Orchestrator()
    orchestrator.run()


if __name__ == "__main__":
    main()
