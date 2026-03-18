"""Audit logging for AI Employee.

Every action the AI takes is logged in JSON format to vault/Logs/YYYY-MM-DD.json.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.core.config import config


def setup_logging() -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger("ai_employee")
    logger.setLevel(getattr(logging, config.log_level, logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def audit_log(
    action_type: str,
    target: str,
    parameters: dict | None = None,
    result: str = "success",
    approval_status: str = "auto",
    approved_by: str = "system",
):
    """Write a structured JSON audit log entry.

    Logs are stored in vault/Logs/YYYY-MM-DD.json, one JSON object per line.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": action_type,
        "actor": "ai_employee",
        "target": target,
        "parameters": parameters or {},
        "approval_status": approval_status,
        "approved_by": approved_by,
        "result": result,
        "dry_run": config.dry_run,
    }

    log_file = config.logs_path / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    config.logs_path.mkdir(parents=True, exist_ok=True)

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    logger = logging.getLogger("ai_employee")
    prefix = "[DRY RUN] " if config.dry_run else ""
    logger.info(f"{prefix}{action_type}: {target}")
