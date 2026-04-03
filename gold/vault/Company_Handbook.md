---
last_updated: "2026-03-20T00:00:00Z"
version: "1.0.0"
tier: "gold"
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
| `urgent`, `asap`, `critical` | High | Process immediately, notify user |
| `invoice`, `payment`, `bill` | Medium | Process within current cycle |
| All other files | Low | Process in next scheduled batch |

### File Type Handling
| File Type | Action |
|-----------|--------|
| `.md` (Markdown) | Parse frontmatter, extract tasks, process content |
| `.txt` (Text) | Read content, create action summary |
| `.csv` (Data) | Parse and summarize, flag anomalies |
| `.pdf` (Document) | Log metadata, flag for human review |
| Other | Log metadata, move to Inbox for manual review |

## Email Rules (Gmail)

### Triage Logic
| Condition | Action |
|-----------|--------|
| From a known client (in Business_Goals.md) | High priority — draft reply within same cycle |
| Subject contains `invoice`, `payment`, `contract` | Medium priority — flag for review |
| Newsletter / promotional | Low priority — can be archived |
| From unknown sender | Medium priority — summarize and flag |

### Reply Guidelines
- Always be **professional and concise**.
- Do not make commitments about pricing or deadlines without human approval.
- If the email contains a question you cannot answer from context, mark it `needs_human_response`.
- Draft all replies in `/Plans/PLAN_reply_<email_id>.md` before moving to approval.

### What NEVER to do with email
- Never send an email reply without creating an approval file first.
- Never unsubscribe from mailing lists (user preference unknown).
- Never forward emails externally without approval.

## LinkedIn Rules

### LinkedIn Watcher (Messages & Notifications)
The LinkedIn Watcher daemon monitors LinkedIn via Playwright and writes to `/Needs_Action/`:

| Item Type | File Prefix | Action |
|-----------|-------------|--------|
| `linkedin_message` | `LINKEDIN_MSG_*.md` | Triage message, draft reply if needed |
| `linkedin_notification` | `LINKEDIN_NOTIF_*.md` | Summarize and act if required |

### Triage Logic for LinkedIn Messages
| Condition | Action |
|-----------|--------|
| Message from known client (in Business_Goals.md) | High priority — draft reply plan |
| Message contains `invoice`, `payment`, `partnership` | Medium priority — flag for review |
| Connection request or networking message | Medium priority — summarize |
| Promotional or automated message | Low priority — archive |

### LinkedIn Post Creation Flow
Posts are created via the `/linkedin-post-creator` skill:
1. Claude generates post draft → saves to `/Needs_Action/LINKEDIN_POST_*.md`
2. Approval request → `/Pending_Approval/LINKEDIN_POST_approval_*.md`
3. User reviews and moves approval file to `/Approved/`
4. Orchestrator's `ApprovalWatcher` queues the post
5. `LinkedInWatcher` publishes on next cycle via Playwright

### LinkedIn Post Guidelines
- Posts must be **professional, authentic, and on-brand**
- No false claims, guarantees, or statements requiring legal approval
- Include 3–5 relevant hashtags
- Keep to 150–300 words for best engagement
- Always end with a Call to Action (CTA)
- Maximum **3 posts per hour** (rate limit)

### What NEVER to do with LinkedIn
- Never post directly without creating an approval file first
- Never reply to LinkedIn messages without human approval
- Never accept/reject connection requests autonomously
- Never share confidential business information in posts

## Odoo Accounting Rules (Gold Tier)

The AI Employee integrates with Odoo Community 19+ via the `odoo-mcp` server.
All actions use Odoo's JSON-RPC API (http://localhost:8069/jsonrpc).

### Odoo Action Thresholds (HITL)
| Action | Threshold | Rule |
|--------|-----------|------|
| Create invoice | ≤ $100 | Auto-approve: call `create_invoice` directly |
| Create invoice | > $100 | **HITL required**: write Pending_Approval file first |
| Post payment | Any amount | **HITL ALWAYS required**: write Pending_Approval file first |
| List open invoices | N/A | Auto-approve: read-only, safe |
| Get balance sheet | N/A | Auto-approve: read-only, safe |
| Cancel/delete invoice | Any | **HITL ALWAYS required** |

### Odoo Invoice Creation Flow
1. Detect invoice request in `/Needs_Action/INVOICE_*.md` or `ODOO_*.md`
2. If amount ≤ $100 → call `create_invoice` directly
3. If amount > $100 → write `/Pending_Approval/ODOO_invoice_<id>.md`
4. Human approves → moves file to `/Approved/`
5. Orchestrator calls OdooAccountant skill → executes `create_invoice`
6. Log result to `/Logs/YYYY-MM-DD.json` and update `/Accounting/Odoo/Current_Month.md`
7. Move all source files to `/Done/`

### Odoo Payment Flow
1. Payment request always goes to `/Pending_Approval/ODOO_payment_<id>.md`
2. Include invoice_id, amount, customer name
3. Human approves → orchestrator calls `post_payment`
4. Log to audit trail

### What NEVER to do with Odoo
- Never post a payment without explicit approval in `/Approved/`
- Never delete or cancel invoices autonomously
- Never modify accounting settings or chart of accounts
- Never change tax rates or fiscal positions

### Odoo Data Locations
| Data | Location |
|------|----------|
| Monthly summary | `gold/vault/Accounting/Odoo/Current_Month.md` |
| Rate card | `gold/vault/Accounting/Odoo/Rates.md` |
| Invoice log | `gold/vault/Accounting/Odoo/Invoice_Log.md` |
| CEO briefing (financial) | `gold/vault/Briefings/YYYY-MM-DD_Financial_Summary.md` |

## Meta Social Media Rules (Gold Tier — Facebook & Instagram)

The AI Employee integrates with Facebook Pages and Instagram Business accounts
via the `meta-social-mcp` server (Meta Graph API v19.0).

### Meta Action Rules (HITL)
| Action | Rule |
|--------|------|
| Post to Facebook Page | **HITL ALWAYS required** |
| Post to Instagram | **HITL ALWAYS required** |
| Reply to comments | **HITL ALWAYS required** |
| Send DMs | **NEVER** — not supported autonomously |
| Generate summary/insights | Auto-approve (read-only) |
| Draft post content | Auto-approve (write to Plans/) |

### Meta Post Creation Flow
1. Detect social request in `/Needs_Action/META_POST_*.md` or from schedule
2. Read Business_Goals.md for brand voice and content pillars
3. Draft post content → write to `/Plans/PLAN_meta_<platform>_<date>.md`
4. Write approval request → `/Pending_Approval/META_<PLATFORM>_<id>.md`
5. Human approves → moves to `/Approved/`
6. Orchestrator calls MetaSocialPoster skill → executes `post_to_facebook` or `post_to_instagram`
7. Log result and move files to `/Done/`

### Facebook Post Guidelines
- **Length:** 150–300 words for best engagement
- **Format:** Short paragraphs, max 3 bullet points
- **Hashtags:** 3–5 relevant business hashtags
- **CTA:** Always include a clear call to action
- **Rate limit:** Max 3 posts per hour

### Instagram Post Guidelines
- **Image required:** ALWAYS — cannot post text-only via Graph API
- **Caption:** 150–200 characters ideal, 2200 max
- **Hashtags:** Up to 10 tags
- **Tone:** Visual-first, inspirational
- **CTA:** "Link in bio" or similar

### Content Pillars (Meta)
1. **Thought Leadership** — AI automation insights and trends
2. **Behind the Scenes** — How the Digital FTE operates
3. **Client Wins** — Anonymized results and case studies
4. **Educational** — Tips, how-tos, product explainers

### What NEVER to post on Meta
- Unverified statistics or false revenue claims
- Confidential client or employee information
- Pricing details without explicit approval
- Political, religious, or divisive content
- Competitor attacks or negative comparisons

## Approval Requirements

### Always requires human approval:
- Sending any external communication (email, LinkedIn post, Meta post)
- Any financial transaction (Odoo payment)
- Any invoice > $100 (Odoo)
- Deleting files outside the vault
- Modifying Company_Handbook.md
- Replying to new/unknown contacts

### Auto-approved (no approval needed):
- Reading and summarizing files
- Moving files between vault folders
- Updating Dashboard.md
- Creating log entries
- Creating Plan.md files
- Archiving processed items to /Done/
- Listing invoices or getting balance sheet (Odoo)
- Generating social media summary reports (Meta)

## Response Templates

### Action File Frontmatter
```yaml
---
type: <file_drop|email|task|report|briefing_request|odoo_invoice_request|meta_post_request>
source: <origin of the item>
priority: <high|medium|low>
status: <pending|in_progress|done|needs_approval>
created: <ISO 8601 timestamp>
requires_approval: <true|false>
---
```

### Approval Request Frontmatter
```yaml
---
type: approval_request
action: <send_email|post_linkedin|post_facebook|post_instagram|odoo_create_invoice|odoo_post_payment>
priority: <high|medium|low>
status: pending
created: <ISO 8601 timestamp>
expires: <ISO 8601 timestamp — 24h from created>
requires_hitl: true
hitl_reason: <why approval is required>
---
```

## Error Handling

1. On transient errors (network, timeout): retry up to 3 times with exponential backoff.
2. On persistent errors: log the error, keep the item in `/Needs_Action/` with `status: error`, and update Dashboard.
3. Never silently swallow errors.
4. If Gmail API fails: note in Dashboard, queue continues building for later processing.
5. If Odoo is unreachable: queue the action, note in Dashboard, retry on next cycle.
6. If Meta Graph API fails: note in Dashboard, do not retry posting — require new approval.

## Permission Boundaries

| Action Category | Auto-Approve Threshold | Always Require Approval |
|:----------------|:----------------------|:------------------------|
| Email replies | To known contacts | New contacts, bulk sends |
| Payments (Odoo) | None — always HITL | All payments |
| Invoices (Odoo) | ≤ $100 | > $100, cancellations |
| Social media posts | None — always HITL | All posts (LinkedIn, Facebook, Instagram) |
| File operations | Create, read | Delete, move outside vault |
| Social insights | Always auto-approved | N/A |
| Financial reports | Always auto-approved | N/A |
