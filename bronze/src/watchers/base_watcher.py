"""Base Watcher — abstract template for all perception-layer watchers.

All watchers follow this pattern:
  1. check_for_updates() — detect new items from an external source
  2. create_action_file() — write a .md file into /Needs_Action/ for Claude to process

Subclasses implement the detection logic; the base class handles
the run loop, logging, and error resilience.
"""

import time
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from src.core.config import config
from src.utils.logger import audit_log


class BaseWatcher(ABC):
    """Abstract base class for all watcher scripts."""

    def __init__(self, check_interval: int | None = None):
        self.vault_path = config.vault_path
        self.needs_action = config.needs_action_path
        self.check_interval = check_interval or config.watcher_interval
        self.logger = logging.getLogger(self.__class__.__name__)
        self._running = False

    @abstractmethod
    def check_for_updates(self) -> list:
        """Return a list of new items to process.

        Each item is an opaque object passed to create_action_file().
        """

    @abstractmethod
    def create_action_file(self, item) -> Path:
        """Create a .md file in /Needs_Action/ for the given item.

        Returns the path to the created file.
        """

    def on_start(self):
        """Hook called once when the watcher starts. Override for setup."""

    def on_stop(self):
        """Hook called when the watcher stops. Override for cleanup."""

    def run(self):
        """Main run loop — poll for updates and create action files."""
        self._running = True
        self.logger.info(f"Starting {self.__class__.__name__} (interval={self.check_interval}s)")
        audit_log("watcher_start", self.__class__.__name__)
        self.on_start()

        try:
            while self._running:
                try:
                    items = self.check_for_updates()
                    for item in items:
                        try:
                            filepath = self.create_action_file(item)
                            self.logger.info(f"Created action file: {filepath.name}")
                        except Exception as e:
                            self.logger.error(f"Failed to create action file: {e}")
                            audit_log(
                                "action_file_error",
                                self.__class__.__name__,
                                {"error": str(e)},
                                result="error",
                            )
                except Exception as e:
                    self.logger.error(f"Error in check_for_updates: {e}")
                    audit_log(
                        "watcher_error",
                        self.__class__.__name__,
                        {"error": str(e)},
                        result="error",
                    )
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            self.logger.info(f"Stopping {self.__class__.__name__} (keyboard interrupt)")
        finally:
            self._running = False
            self.on_stop()
            audit_log("watcher_stop", self.__class__.__name__)

    def stop(self):
        """Signal the watcher to stop after the current cycle."""
        self._running = False
