"""Configuration management for AI Employee Gold tier."""

import os
from pathlib import Path
from dotenv import load_dotenv


# Load .env from gold directory
_gold_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(_gold_dir / ".env")


class Config:
    """Centralized configuration loaded from environment variables."""

    def __init__(self):
        self.silver_dir = _gold_dir  # kept for backward compat
        self.gold_dir = _gold_dir

        # Vault path
        vault_raw = os.getenv("VAULT_PATH", "./vault")
        self.vault_path = (self.silver_dir / vault_raw).resolve()

        # Drop folder path
        drop_raw = os.getenv("DROP_FOLDER_PATH", "./drop_folder")
        self.drop_folder_path = (self.silver_dir / drop_raw).resolve()

        # Watcher settings
        self.watcher_interval = int(os.getenv("WATCHER_INTERVAL", "5"))

        # Runtime flags
        self.dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        # --- Gmail ---
        gmail_creds_raw = os.getenv("GMAIL_CREDENTIALS_PATH", "../gmail_credentials.json")
        self.gmail_credentials_path = (self.silver_dir / gmail_creds_raw).resolve()

        gmail_token_raw = os.getenv("GMAIL_TOKEN_PATH", "../gmail_token.json")
        self.gmail_token_path = (self.silver_dir / gmail_token_raw).resolve()

        self.gmail_check_interval = int(os.getenv("GMAIL_CHECK_INTERVAL", "120"))
        self.gmail_query = os.getenv("GMAIL_QUERY", "is:unread is:important")
        self.gmail_max_results = int(os.getenv("GMAIL_MAX_RESULTS", "10"))

        # --- LinkedIn ---
        linkedin_session_raw = os.getenv("LINKEDIN_SESSION_PATH", "./.linkedin_session")
        self.linkedin_session_path = (self.silver_dir / linkedin_session_raw).resolve()
        self.linkedin_check_interval = int(os.getenv("LINKEDIN_CHECK_INTERVAL", "300"))
        self.linkedin_headless = os.getenv("LINKEDIN_HEADLESS", "true").lower() == "true"
        self.linkedin_post_rate_limit = int(os.getenv("LINKEDIN_POST_RATE_LIMIT", "3"))

        # --- Rate Limits ---
        self.email_rate_limit = int(os.getenv("EMAIL_RATE_LIMIT", "10"))

        # --- Scheduling ---
        self.daily_briefing_hour = int(os.getenv("DAILY_BRIEFING_HOUR", "8"))
        self.daily_briefing_minute = int(os.getenv("DAILY_BRIEFING_MINUTE", "0"))

        # --- Approval ---
        self.approval_check_interval = int(os.getenv("APPROVAL_CHECK_INTERVAL", "10"))

        # --- Odoo (Gold Tier) ---
        self.odoo_url = os.getenv("ODOO_URL", "http://localhost:8069")
        self.odoo_db = os.getenv("ODOO_DB", "odoo_ai_employee")
        self.odoo_user = os.getenv("ODOO_USER", "admin")
        self.odoo_password = os.getenv("ODOO_PASSWORD", "admin")

        # --- Meta Social (Gold Tier) ---
        self.meta_page_id = os.getenv("META_PAGE_ID", "")
        self.meta_page_access_token = os.getenv("META_PAGE_ACCESS_TOKEN", "")
        self.meta_ig_user_id = os.getenv("META_IG_USER_ID", "")
        self.meta_graph_api_version = os.getenv("META_GRAPH_API_VERSION", "v19.0")
        self.meta_post_rate_limit = int(os.getenv("META_POST_RATE_LIMIT", "3"))

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
    def briefings_path(self) -> Path:
        return self.vault_path / "Briefings"

    @property
    def dashboard_path(self) -> Path:
        return self.vault_path / "Dashboard.md"

    @property
    def handbook_path(self) -> Path:
        return self.vault_path / "Company_Handbook.md"

    @property
    def business_goals_path(self) -> Path:
        return self.vault_path / "Business_Goals.md"

    @property
    def odoo_accounting_path(self) -> Path:
        return self.vault_path / "Accounting" / "Odoo"

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
            self.briefings_path,
            self.drop_folder_path,
            self.odoo_accounting_path,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


# Singleton config instance
config = Config()
