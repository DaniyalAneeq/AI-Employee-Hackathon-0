# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Digital FTE (Full-Time Equivalent) — Personal AI Employee**

A local-first, agent-driven autonomous system that proactively manages personal affairs (Gmail, WhatsApp, Bank) and business operations (Social Media, Payments, Project Tasks). Claude Code is the reasoning engine; Obsidian is the management dashboard (GUI + long-term memory).

The system follows a **Perception → Reasoning → Action** architecture:
- **Perception**: Python "Watcher" scripts monitor external sources (Gmail, WhatsApp, filesystem, bank) and write `.md` files into `/Needs_Action/`
- **Reasoning**: Claude Code reads from the Obsidian vault, thinks, and creates `Plan.md` files
- **Action**: MCP servers execute external actions (send emails, post on social media, browser automation)
- **Safety**: Human-in-the-Loop (HITL) via file-based approval (`/Pending_Approval/` → `/Approved/` → execute)

## Architecture

```
External Sources (Gmail, WhatsApp, Bank, Files)
        ↓
Perception Layer — Python Watcher scripts (continuous polling)
        ↓
Obsidian Vault (local markdown) — the central data store
  /Needs_Action/  /Plans/  /Done/  /Logs/
  /Pending_Approval/  /Approved/  /Rejected/
  Dashboard.md  Company_Handbook.md  Business_Goals.md
        ↓
Reasoning Layer — Claude Code (read → think → plan → write → request approval)
        ↓
Action Layer — MCP Servers (Email, Browser/Playwright, Calendar, Slack)
        ↓
Orchestrator.py — master process: scheduling, folder watching, process management
Watchdog.py — health monitor: restart failed processes, alert on errors
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Reasoning Engine | Claude Code (claude-opus-4-6 or via Claude Code Router) |
| Knowledge Base / GUI | Obsidian (local Markdown vault) |
| Watcher Scripts | Python 3.13+ (UV project) |
| MCP Servers | Node.js v24+ LTS |
| Browser Automation | Playwright MCP (port 8808) |
| Process Management | PM2 (recommended) or custom Watchdog |
| Version Control | Git / GitHub Desktop |
| ERP (Gold+) | Odoo Community 19+ (self-hosted, JSON-RPC API) |

## Tiered Deliverables (Phased Development)

### Bronze — Foundation (Minimum Viable)
- Obsidian vault with `Dashboard.md` and `Company_Handbook.md`
- One working Watcher script (Gmail OR filesystem)
- Claude Code reading from and writing to the vault
- Basic folder structure: `/Inbox`, `/Needs_Action`, `/Done`
- All AI functionality as [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)

### Silver — Functional Assistant
- All Bronze + two or more Watchers (Gmail + WhatsApp + LinkedIn)
- Auto-post on LinkedIn for sales generation
- Claude reasoning loop that creates `Plan.md` files
- One working MCP server for external action (e.g., sending emails)
- HITL approval workflow for sensitive actions
- Basic scheduling via cron or Task Scheduler

### Gold — Autonomous Employee
- All Silver + full cross-domain integration (Personal + Business)
- Odoo Community accounting system integrated via [MCP server](https://github.com/AlanOgic/mcp-odoo-adv) (JSON-RPC)
- Facebook, Instagram, Twitter/X integration (post + summarize)
- Multiple MCP servers for different action types
- Weekly Business & Accounting Audit with CEO Briefing generation
- Error recovery, graceful degradation, comprehensive audit logging
- Ralph Wiggum loop for autonomous multi-step task completion

### Platinum — Always-On Cloud + Local Executive
- All Gold + 24/7 cloud VM deployment (Oracle Cloud Free / AWS)
- Work-Zone Specialization: Cloud owns email triage + social drafts; Local owns approvals, WhatsApp, payments
- Vault sync via Git (markdown/state only — secrets never sync)
- Odoo Community deployed on cloud with HTTPS + backups
- Optional A2A upgrade to replace file handoffs

## Key Patterns

### Watcher Pattern
All watchers extend `BaseWatcher` (ABC): implement `check_for_updates()` → `create_action_file()` → write `.md` to `/Needs_Action/`. Each watcher runs as a daemon with its own polling interval.

### Human-in-the-Loop (HITL)
Sensitive actions create approval request files in `/Pending_Approval/` with YAML frontmatter (type, action, amount, status). User moves file to `/Approved/` to authorize or `/Rejected/` to deny. The orchestrator watches `/Approved/` and triggers MCP execution.

### Ralph Wiggum Loop (Persistence)
A Stop hook that intercepts Claude's exit and re-injects the prompt until the task is complete. Two completion strategies:
1. **Promise-based**: Claude outputs `<promise>TASK_COMPLETE</promise>`
2. **File movement**: Stop hook detects when task file moves to `/Done`

Reference: `https://github.com/anthropics/claude-code/tree/main/.claude/plugins/ralph-wiggum`

### Permission Boundaries
| Action | Auto-Approve | Always Require Approval |
|--------|-------------|------------------------|
| Email replies | Known contacts | New contacts, bulk sends |
| Payments | < $50 recurring | All new payees, > $100 |
| Social media | Scheduled posts | Replies, DMs |
| File operations | Create, read | Delete, move outside vault |

## Obsidian Vault Structure

```
AI_Employee_Vault/
├── Dashboard.md              # Real-time summary (bank balance, pending messages, active projects)
├── Company_Handbook.md       # Rules of engagement for the AI
├── Business_Goals.md         # Quarterly objectives, KPIs, subscription audit rules
├── Inbox/                    # Raw incoming items
├── Needs_Action/             # Items watchers have flagged for Claude to process
├── Plans/                    # Claude's generated action plans with checkboxes
├── Pending_Approval/         # HITL approval requests (sensitive actions)
├── Approved/                 # Human-approved actions ready for execution
├── Rejected/                 # Human-rejected actions
├── Done/                     # Completed items (archive)
├── In_Progress/<agent>/      # Claim-by-move rule (Platinum tier)
├── Logs/                     # YYYY-MM-DD.json audit logs (retain 90+ days)
├── Briefings/                # Generated CEO briefings
├── Accounting/               # Financial data (Current_Month.md, Rates.md)
└── Invoices/                 # Generated invoice PDFs
```

## Security Rules

- Credentials via environment variables or OS secrets manager — never in vault or code
- `.env` must be in `.gitignore`
- All action scripts support `--dry-run` flag; `DRY_RUN=true` by default during development
- Rate limiting: max 10 emails/hour, max 3 payments/hour
- Audit log every action in JSON format to `/Vault/Logs/YYYY-MM-DD.json`
- Platinum: secrets never sync between cloud and local (`.env`, tokens, WhatsApp sessions, banking creds)

## Commands

```bash
# Python project setup (UV)
uv init
uv add <package>
uv run python <script.py>

# Playwright MCP server
bash .claude/skills/browsing-with-playwright/scripts/start-server.sh   # start
bash .claude/skills/browsing-with-playwright/scripts/stop-server.sh    # stop
python3 .claude/skills/browsing-with-playwright/scripts/verify.py      # verify

# Playwright MCP client calls
python3 .claude/skills/browsing-with-playwright/scripts/mcp-client.py call \
  -u http://localhost:8808 -t <tool_name> -p '<json_params>'

# Process management (PM2)
npm install -g pm2
pm2 start gmail_watcher.py --interpreter python3
pm2 save && pm2 startup

# Run orchestrator
uv run python orchestrator.py
```

## Development Conventions

- All AI functionality must be implemented as **Agent Skills** (SKILL.md files in `.claude/skills/`)
- Obsidian markdown files use YAML frontmatter for metadata (type, status, priority, timestamps)
- File naming: `TYPE_identifier_YYYY-MM-DD.md` (e.g., `EMAIL_abc123.md`, `WHATSAPP_client_a_2026-01-07.md`)
- Logs are JSON (see audit log format in hackathon doc Section 6.3)
- The orchestrator is the single entry point for scheduling and process management
- Claim-by-move rule (Platinum): first agent to move item from `/Needs_Action` to `/In_Progress/<agent>/` owns it
