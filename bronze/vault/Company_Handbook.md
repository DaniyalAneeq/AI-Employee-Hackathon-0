---
last_updated: "2026-03-15T00:00:00Z"
version: "0.1.0"
---

# Company Handbook — Rules of Engagement

This document defines how the AI Employee should behave when processing tasks.
Claude Code reads this file to understand the rules before taking any action.

## General Rules

1. **Safety First**: Never execute destructive actions without human approval.
2. **Log Everything**: Every action must be logged to `/Logs/` in JSON format.
3. **Dry Run Default**: When `DRY_RUN=true`, log intended actions without executing.
4. **Ask When Unsure**: If a task is ambiguous, create a clarification request instead of guessing.

## File Processing Rules

### Priority Classification
| Keyword in Filename/Content | Priority | Action |
|------------------------------|----------|--------|
| `urgent`, `asap`, `critical` | 🔴 High | Process immediately, notify user |
| `invoice`, `payment`, `bill` | 🟡 Medium | Process within current cycle |
| All other files | 🟢 Low | Process in next scheduled batch |

### File Type Handling
| File Type | Action |
|-----------|--------|
| `.md` (Markdown) | Parse frontmatter, extract tasks, process content |
| `.txt` (Text) | Read content, create action summary |
| `.csv` (Data) | Parse and summarize, flag anomalies |
| `.pdf` (Document) | Log metadata, flag for human review |
| Other | Log metadata, move to Inbox for manual review |

## Approval Requirements

Actions that **always** require human approval:
- Sending any external communication (email, message)
- Any financial transaction
- Deleting files outside the vault
- Modifying Company_Handbook.md

Actions that can be **auto-approved**:
- Reading and summarizing files
- Moving files between vault folders
- Updating Dashboard.md
- Creating log entries
- Creating Plan.md files

## Response Templates

When creating action files, use this frontmatter:
```yaml
---
type: <file_drop|email|task|report>
source: <origin of the item>
priority: <high|medium|low>
status: <pending|in_progress|done|needs_approval>
created: <ISO 8601 timestamp>
---
```

## Error Handling

1. On transient errors (network, timeout): retry up to 3 times with exponential backoff.
2. On persistent errors: log the error, move the item to `/Needs_Action/` with `status: error`, and alert via Dashboard.
3. Never silently swallow errors.
