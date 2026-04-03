---
last_updated: "2026-03-20T17:35:00Z"
type: invoice_log
---

# Odoo Invoice Log

This file tracks all invoices created via the OdooAccountant skill.

## Log Entries

| Date | Invoice # | Customer | Amount | Action | Approval | Result |
|------|-----------|----------|--------|--------|----------|--------|
| 2026-03-20 | INV/2026/00002 | Acme Corp | $1,500.00 | create_invoice | human_approved (ODOO_invoice_776258a8) | ✅ posted |

---
*Entries are added automatically when OdooAccountant creates or updates invoices.*
*Audit JSON is stored in `/Logs/YYYY-MM-DD.json`*
