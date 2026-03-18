"""Watcher modules for the Silver tier AI Employee."""

from src.watchers.base_watcher import BaseWatcher
from src.watchers.filesystem_watcher import FileSystemWatcher
from src.watchers.gmail_watcher import GmailWatcher
from src.watchers.linkedin_watcher import LinkedInWatcher

__all__ = ["BaseWatcher", "FileSystemWatcher", "GmailWatcher", "LinkedInWatcher"]
