---
type: odoo_invoice_request
customer: "Acme Corp"
amount: 1500.00
description: "AI Employee Gold Tier setup — March 2026"
source: whatsapp_watcher
priority: medium
status: pending
created: "2026-03-20T08:00:00Z"
requires_approval: true
---

## Invoice Request

**From:** WhatsApp Watcher (auto-detected keyword: "invoice")
**Client:** Acme Corp
**Message:** "Hey, can you send the invoice for the AI project we completed last week?"

## Requested Invoice Details
- **Customer:** Acme Corp
- **Amount:** $1,500.00
- **Description:** AI Employee Gold Tier setup — March 2026
- **Rate Reference:** See `/Accounting/Odoo/Rates.md` — "AI Employee Gold Tier Setup"

## AI Analysis Required
The amount ($1,500.00) exceeds the $100 auto-approve threshold.
→ OdooAccountant skill must create a Pending_Approval file before calling Odoo.

## Instructions for OdooAccountant
1. Read Company_Handbook.md Odoo rules
2. Detect: amount > $100 → HITL required
3. Write Pending_Approval/ODOO_invoice_*.md
4. Write Plans/PLAN_odoo_invoice_Acme_Corp_20260320.md
5. Update Dashboard.md
6. DO NOT call create_invoice until approved
