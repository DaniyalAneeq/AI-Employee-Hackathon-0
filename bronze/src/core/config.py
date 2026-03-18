"""Configuration management for AI Employee Bronze tier."""

import os
from pathlib import Path
from dotenv import load_dotenv


# Load .env from bronze directory
_bronze_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(_bronze_dir / ".env")


class Config:
    """Centralized configuration loaded from environment variables."""

    def __init__(self):
        self.bronze_dir = _bronze_dir

        # Vault path
        vault_raw = os.getenv("VAULT_PATH", "./vault")
        self.vault_path = (self.bronze_dir / vault_raw).resolve()

        # Drop folder path
        drop_raw = os.getenv("DROP_FOLDER_PATH", "./drop_folder")
        self.drop_folder_path = (self.bronze_dir / drop_raw).resolve()

        # Watcher settings
        self.watcher_interval = int(os.getenv("WATCHER_INTERVAL", "5"))

        # Runtime flags
        self.dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Vault subdirectories
    @property
    def inbox_path(self) -> Path:
        return self.vault_path / "Inbox"

    @property
    def needs_action_path(self) -> Path:
        return self.vault_path / "Needs_Action"

    @property
    def done_path(self) -> Path:
        return self.vault_path / "Done"

    @property
    def logs_path(self) -> Path:
        return self.vault_path / "Logs"

    @property
    def plans_path(self) -> Path:
        return self.vault_path / "Plans"

    @property
    def pending_approval_path(self) -> Path:
        return self.vault_path / "Pending_Approval"

    @property
    def approved_path(self) -> Path:
        return self.vault_path / "Approved"

    @property
    def rejected_path(self) -> Path:
        return self.vault_path / "Rejected"

    @property
    def dashboard_path(self) -> Path:
        return self.vault_path / "Dashboard.md"

    @property
    def handbook_path(self) -> Path:
        return self.vault_path / "Company_Handbook.md"

    def ensure_directories(self):
        """Create all required vault directories if they don't exist."""
        for directory in [
            self.inbox_path,
            self.needs_action_path,
            self.done_path,
            self.logs_path,
            self.plans_path,
            self.pending_approval_path,
            self.approved_path,
            self.rejected_path,
            self.drop_folder_path,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


# Singleton config instance
config = Config()
