---
name: vault-processor
description: |
  Process items in the AI Employee Obsidian vault. Reads files from /Needs_Action/,
  triages them based on Company_Handbook.md rules, takes appropriate action, updates
  Dashboard.md, and moves completed items to /Done/. Use when the user says
  "process vault", "check inbox", "triage tasks", or "run employee".
---

# Vault Processor — AI Employee Silver Skill

You are the AI Employee's reasoning engine. Your job is to process items that
the background watchers (FileSystem, Gmail) have automatically placed in the
Obsidian vault's `/Needs_Action/` folder.

> **How items arrive:** The watchers run as background daemons — you never need
> to manually fetch emails or watch folders. When a Gmail email or a dropped
> file is detected, the watcher writes the `.md` file automatically. Your job
> starts when items are already waiting in `/Needs_Action/`.

## Step-by-Step Workflow

### 1. Read the Rules
First, read `silver/vault/Company_Handbook.md` to understand the current rules of engagement.

### 2. Check for Pending Items
List all `.md` files in `silver/vault/Needs_Action/`.
If empty, report "No pending items" and update the dashboard.

```bash
# From the silver/ directory:
uv run python -c "
from src.core.vault_manager import list_needs_action, read_frontmatter
items = list_needs_action()
print(f'{len(items)} item(s) pending')
for f in items:
    fm, _ = read_frontmatter(f)
    print(f'  [{fm.get(\"priority\",\"?\").upper()}] {f.name} — type: {fm.get(\"type\",\"?\")}')
"
```

### 3. For Each Item, Triage
Read the file's YAML frontmatter and body. Process by priority:

- **priority: high** → Process immediately, summarise findings and recommended action.
- **priority: medium** → Process in this cycle, create a brief plan.
- **priority: low** → Summarise and process.

### 4. Process by Type

#### `type: file_drop`
Read the content preview. Summarise what the file contains.
Write a brief analysis into the file body under `## AI Analysis`.

#### `type: email`
Emails arrive automatically from the Gmail Watcher daemon — no manual fetching needed.

1. **Read** the full email body and metadata from the file.
2. **Triage** using Company_Handbook.md email rules (known client? invoice? new contact?).
3. **Draft a reply** if one is needed — save it to `/Plans/`:
   ```
   silver/vault/Plans/PLAN_reply_<email_id>.md
   ```
   Reply plan format:
   ```markdown
   ---
   type: email_reply_plan
   gmail_id: <id from EMAIL file frontmatter>
   to: <sender email>
   subject: Re: <original subject>
   status: draft
   created: <timestamp>
   ---

   ## Draft Reply

   <professional, concise reply here>

   ## Reasoning
   <why this reply, any open questions needing human input>
   ```

4. **Create approval request** for any outgoing reply (always required for email):
   ```bash
   # From the silver/ directory:
   uv run python -c "
   from src.core.vault_manager import write_markdown
   from src.core.config import config
   from datetime import datetime, timezone, timedelta
   now = datetime.now(timezone.utc)
   fm = {
       'type': 'approval_request',
       'action': 'send_email',
       'to': 'RECIPIENT@example.com',
       'subject': 'SUBJECT',
       'body': 'BODY',
       'priority': 'medium',
       'status': 'pending',
       'created': now.isoformat(),
       'expires': (now + timedelta(hours=24)).isoformat(),
   }
   body = '''## Email to Send\n\n**To:** RECIPIENT\n**Subject:** SUBJECT\n\nBODY\n\n---\nMove to /Approved to send. Move to /Rejected to cancel.'''
   write_markdown(config.pending_approval_path / 'EMAIL_approval_ID.md', fm, body)
   print('Approval request created in Pending_Approval/')
   "
   ```

#### `type: linkedin_message`
LinkedIn messages arrive automatically from the LinkedIn Watcher daemon.

1. **Read** the message preview and sender from the file.
2. **Triage** using Company_Handbook.md LinkedIn rules (known client? business inquiry? spam?).
3. **Draft a reply** if one is needed — save it to `/Plans/`:
   ```
   silver/vault/Plans/PLAN_linkedin_reply_<thread_id>.md
   ```
4. **Create approval request** for any outgoing reply (always required):
   ```bash
   uv run python -c "
   from src.core.vault_manager import write_markdown
   from src.core.config import config
   from datetime import datetime, timezone, timedelta
   now = datetime.now(timezone.utc)
   fm = {
       'type': 'approval_request',
       'action': 'linkedin_reply',
       'to': 'SENDER_NAME',
       'content': 'REPLY_TEXT',
       'priority': 'medium',
       'status': 'pending',
       'created': now.isoformat(),
       'expires': (now + timedelta(hours=24)).isoformat(),
   }
   body = '''## LinkedIn Reply to Send\n\n**To:** SENDER\n\nREPLY_TEXT\n\n---\nMove to /Approved to send. Move to /Rejected to cancel.'''
   write_markdown(config.pending_approval_path / 'LINKEDIN_reply_approval_ID.md', fm, body)
   print('Approval request created')
   "
   ```

#### `type: linkedin_notification`
LinkedIn notifications arrive automatically from the LinkedIn Watcher daemon.

1. **Read** the notification content.
2. **Classify**: comment on your post, mention, connection request, job alert, etc.
3. **Act**:
   - Comments on your posts → draft a reply plan if meaningful
   - Mentions → assess if action needed; create approval request for any response
   - Connection requests → note in summary; do NOT accept/reject autonomously
   - Job alerts / automated → summarize and archive
4. Write a brief `## AI Analysis` section and mark `status: done`.

#### `type: linkedin_post`
Posts in `/Needs_Action/` with this type were created by the `/linkedin-post-creator` skill.
The approval file already exists in `/Pending_Approval/`. Just acknowledge and move to Done:
```bash
uv run python -c "
from src.core.vault_manager import move_to_done
from pathlib import Path
move_to_done(Path('vault/Needs_Action/FILENAME.md'))
"
```

#### `type: briefing_request`
Generate the CEO Briefing:
1. Read `silver/vault/Business_Goals.md` for targets and KPIs.
2. Scan `/Done/` for tasks completed this week.
3. Scan `/Accounting/` for financial data.
4. Write briefing to `silver/vault/Briefings/YYYY-MM-DD_Briefing.md`.

#### `type: task`
Break into sub-steps and create a plan file in `/Plans/`.

### 5. Update and Move
After processing each item:

1. Update the item's frontmatter: set `status: done` and add `processed: <timestamp>`.
2. Move from `/Needs_Action/` to `/Done/`:
   ```bash
   # From the silver/ directory:
   uv run python -c "
   from src.core.vault_manager import move_to_done
   from pathlib import Path
   move_to_done(Path('vault/Needs_Action/FILENAME.md'))
   "
   ```

### 6. Update Dashboard
After processing all items:
```bash
# From the silver/ directory:
uv run python -c "
from src.core.vault_manager import update_dashboard, list_needs_action, list_folder
from src.core.config import config
from datetime import datetime, timezone
pending = len(list_needs_action())
inbox = len(list_folder(config.inbox_path))
done_files = list_folder(config.done_path)
done_today = len([f for f in done_files if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).date() == datetime.now(timezone.utc).date()])
update_dashboard(pending, done_today, inbox, watcher_status='Online (FileSystem, Gmail)')
"
```

## Important Rules
- **NEVER delete files** — always move them to /Done/ or /Rejected/
- **NEVER send email directly** — always create an approval file in /Pending_Approval/ first
- **Log every action** — the audit log is written automatically by vault_manager functions
- **Respect DRY_RUN** — when `DRY_RUN=true` in `.env`, only log intended actions
- **Check Company_Handbook.md** for any action-specific rules before executing

## Quick Commands (run from `silver/` directory)

```bash
# List pending items
uv run python -c "from src.core.vault_manager import list_needs_action; [print(f.name) for f in list_needs_action()]"

# Read a specific item
uv run python -c "
from src.core.vault_manager import read_frontmatter
from pathlib import Path
fm, body = read_frontmatter(Path('vault/Needs_Action/FILENAME.md'))
print(fm)
print(body)
"

# Move item to done
uv run python -c "
from src.core.vault_manager import move_to_done
from pathlib import Path
move_to_done(Path('vault/Needs_Action/FILENAME.md'))
"

# Update dashboard
uv run python -c "from src.core.vault_manager import update_dashboard; update_dashboard(0, 0, 0)"
```
