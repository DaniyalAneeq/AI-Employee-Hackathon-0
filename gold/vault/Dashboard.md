---
last_updated: '2026-03-20T17:35:00Z'
version: 1.0.0
tier: gold
---

# AI Employee Dashboard — Gold Tier

## System Status
| Component | Status | Last Check |
|-----------|--------|------------|
| FileSystem Watcher | 🔴 Offline | 2026-03-20 17:35:00 UTC |
| Gmail Watcher | 🔴 Offline | 2026-03-20 17:35:00 UTC |
| LinkedIn Watcher | 🔴 Offline | 2026-03-20 17:35:00 UTC |
| odoo-mcp Server | 🟢 Online | 2026-03-20 17:35:00 UTC |
| meta-social-mcp Server | 🟡 Not Started | 2026-03-20 17:35:00 UTC |
| Odoo ERP | 🟢 Running (Docker) | 2026-03-20 17:35:00 UTC |

## Pending Actions
- **[MEDIUM]** `META_POST_20260320_launch.md` — meta_post_request
- **[MEDIUM]** `LINKEDIN_NOTIF_9b24d43d9e29_2026-03-18.md` — linkedin_notification
- **[MEDIUM]** 6x `LINKEDIN_POST_*.md` — linkedin_post

## Odoo Accounting Summary
| Metric | Value |
|--------|-------|
| Total Invoiced (MTD) | $4,000.00 |
| Total Collected (MTD) | $0.00 |
| Outstanding AR | $4,000.00 |
| Open Invoices | 2 |
| Pending Approvals (Odoo) | 0 |

## Meta Social Media Summary
| Platform | Posts (7 days) | Engagement | Pending Approval |
|----------|---------------|------------|-----------------|
| Facebook | 0 | 0 | 0 |
| Instagram | 0 | 0 | 0 |

## Pending Approvals
| File | Type | Amount/Action | Created |
|------|------|--------------|---------|
| *(none)* | — | — | — |

## Recent Activity
- [2026-03-20 17:35:00] odoo_create_invoice: ✅ INV/2026/00002 — Acme Corp — $1,500.00 — human_approved
- [2026-03-20 17:30:27] odoo_hitl_triggered: INVOICE_acme_corp — $1,500 > $100 — Pending_Approval written
- [2026-03-20 17:26:20] odoo_get_balance_sheet: auto_approved — Briefings/2026-03-20_Financial_Summary.md
- [2026-03-20 17:25:00] odoo_list_open_invoices: auto_approved — 1 open invoice ($2,500)

## Quick Stats
| Metric | Value |
|--------|-------|
| Items Processed Today | 3 |
| Items Pending | 8 |
| Items in Inbox | 0 |
| Odoo Invoices Created | 1 |
| Odoo Pending Approvals | 0 |
| Social Posts Published | 0 |

## MCP Servers
| Server | Command | Status |
|--------|---------|--------|
| odoo-mcp | `node gold/mcp-servers/odoo-mcp/index.js` | 🟢 Online |
| meta-social-mcp | `node gold/mcp-servers/meta-social-mcp/index.js` | 🟡 Not Started |

---
*Last updated by OdooAccountant skill — 2026-03-20 17:35:00 UTC*
*Gold Tier — Odoo ERP + Meta Social Media + Full HITL Workflow*
