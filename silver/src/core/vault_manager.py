"""Vault Manager — read, write, and move files within the Obsidian vault.

This module is the single interface for all vault file operations.
Claude Code uses this (via the vault-processor skill) to process items.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.core.config import config
from src.utils.logger import audit_log, setup_logging

logger = setup_logging()


def read_frontmatter(filepath: Path) -> tuple[dict, str]:
    """Parse YAML frontmatter and body from a markdown file.

    Returns (frontmatter_dict, body_string).
    """
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, parts[2].strip()


def write_markdown(filepath: Path, frontmatter: dict, body: str):
    """Write a markdown file with YAML frontmatter."""
    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
    content = f"---\n{fm_str}\n---\n\n{body}\n"
    filepath.write_text(content, encoding="utf-8")
    audit_log("file_write", str(filepath), {"frontmatter_keys": list(frontmatter.keys())})


def move_to_done(filepath: Path) -> Path:
    """Move a processed file from its current location to /Done/."""
    dest = config.done_path / filepath.name
    # Avoid overwrite by appending timestamp
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        dest = config.done_path / f"{stem}_{ts}{suffix}"

    shutil.move(str(filepath), str(dest))
    audit_log("file_move", str(dest), {"from": str(filepath), "to": str(dest)})
    logger.info(f"Moved to Done: {filepath.name} -> {dest.name}")
    return dest


def move_file(filepath: Path, target_dir: Path) -> Path:
    """Move a file to a target directory within the vault."""
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / filepath.name
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        dest = target_dir / f"{stem}_{ts}{suffix}"

    shutil.move(str(filepath), str(dest))
    audit_log("file_move", str(dest), {"from": str(filepath), "to": str(dest)})
    return dest


def list_needs_action() -> list[Path]:
    """Return all .md files currently in /Needs_Action/."""
    return sorted(
        [f for f in config.needs_action_path.iterdir() if f.suffix == ".md"],
        key=lambda p: p.stat().st_mtime,
    )


def list_folder(folder: Path, extension: str = ".md") -> list[Path]:
    """List files in a vault folder filtered by extension."""
    if not folder.exists():
        return []
    return sorted(
        [f for f in folder.iterdir() if f.suffix == extension],
        key=lambda p: p.stat().st_mtime,
    )


def update_dashboard(pending_count: int, done_today: int, inbox_count: int, watcher_status: str = "Online"):
    """Rewrite Dashboard.md with current stats."""
    now = datetime.now(timezone.utc)

    # Count actual items
    needs_action_items = list_needs_action()
    pending_details = ""
    if needs_action_items:
        lines = []
        for item in needs_action_items:
            fm, _ = read_frontmatter(item)
            priority = fm.get("priority", "low")
            item_type = fm.get("type", "unknown")
            lines.append(f"- **[{priority.upper()}]** `{item.name}` — {item_type}")
        pending_details = "\n".join(lines)
    else:
        pending_details = "> No items in Needs_Action."

    # Read recent log for activity
    log_file = config.logs_path / f"{now.strftime('%Y-%m-%d')}.json"
    recent_activity = "> No recent activity."
    if log_file.exists():
        import json
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        recent = lines[-5:]  # last 5 entries
        activity_lines = []
        for line in recent:
            try:
                entry = json.loads(line)
                ts = entry["timestamp"][:19].replace("T", " ")
                activity_lines.append(f"- [{ts}] {entry['action_type']}: {entry['target']}")
            except (json.JSONDecodeError, KeyError):
                continue
        if activity_lines:
            recent_activity = "\n".join(activity_lines)

    frontmatter = {
        "last_updated": now.isoformat(),
        "version": "0.2.0",
        "tier": "silver",
    }

    body = f"""# AI Employee Dashboard

## System Status
| Component | Status | Last Check |
|-----------|--------|------------|
| Watchers | {"🟢 " + watcher_status if "Offline" not in watcher_status else "🔴 " + watcher_status} | {now.strftime('%Y-%m-%d %H:%M:%S')} UTC |

## Pending Actions
{pending_details}

## Recent Activity
{recent_activity}

## Quick Stats
| Metric | Value |
|--------|-------|
| Items Processed Today | {done_today} |
| Items Pending | {pending_count} |
| Items in Inbox | {inbox_count} |

---
*This dashboard is automatically updated by the AI Employee system.*"""

    write_markdown(config.dashboard_path, frontmatter, body)
    logger.info(f"Dashboard updated: {pending_count} pending, {done_today} done today")
