---
type: approval_request
action: odoo_create_invoice
customer: "Acme Corp"
amount: 1500.00
description: "AI Employee Gold Tier setup — March 2026"
source_file: "INVOICE_acme_corp_2026-03-20.md"
plan_file: "PLAN_odoo_invoice_Acme_Corp_20260320.md"
priority: high
status: pending
created: "2026-03-20T17:30:27Z"
expires: "2026-03-21T17:30:27Z"
requires_hitl: true
hitl_reason: "Invoice > $100 requires human approval per Company_Handbook.md"
---

## Invoice Approval Required

**Customer:** Acme Corp
**Amount:** $1,500.00
**Description:** AI Employee Gold Tier setup — March 2026
**Source:** WhatsApp Watcher — client message: *"Hey, can you send the invoice for the AI project we completed last week?"*
**Rate Reference:** Rates.md — "AI Employee Gold Tier Setup" @ $2,500.00 (project rate)

> This invoice is $1,500.00 which exceeds the $100 auto-approve threshold.
> Human approval is required before creating this invoice in Odoo.

---

## To Approve
Move this file to `gold/vault/Approved/`

```bash
mv gold/vault/Pending_Approval/ODOO_invoice_776258a8.md gold/vault/Approved/
```

The OdooAccountant skill will then call `create_invoice("Acme Corp", 1500.00, "AI Employee Gold Tier setup — March 2026")` and create the invoice in Odoo.

## To Reject
Move this file to `gold/vault/Rejected/`

```bash
mv gold/vault/Pending_Approval/ODOO_invoice_776258a8.md gold/vault/Rejected/
```
