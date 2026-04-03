---
type: test_scenario
created: "2026-03-20T00:00:00Z"
status: ready_to_run
---

# Sample Invoice Flow Test — End-to-End Odoo Integration

This file documents the complete test scenario for the OdooAccountant Gold Tier skill.
Run this test after Odoo is set up (see `gold/scripts/setup_odoo.sh`).

---

## Test Scenario 1: Small Invoice (≤ $100 — auto-approved)

### Setup
Place this file in `/Needs_Action/` to trigger the OdooAccountant skill:

```markdown
---
type: odoo_invoice_request
customer: "Test Client Small"
amount: 75.00
description: "Consultation call — 30 minutes"
source: manual_test
status: pending
created: 2026-03-20T10:00:00Z
requires_approval: false
---

Test invoice for $75.00 — should be auto-approved and created in Odoo.
```

### Expected Behavior
1. OdooAccountant reads the file
2. Detects amount ≤ $100 → auto-approve
3. Calls `odoo-mcp: create_invoice("Test Client Small", 75.00, "Consultation call — 30 minutes")`
4. Invoice created in Odoo (or DRY_RUN response logged)
5. Log entry added to `/Logs/2026-03-20.json`
6. `/Accounting/Odoo/Current_Month.md` updated
7. File moved to `/Done/`

### Expected MCP Response (DRY_RUN=true)
```json
{
  "dry_run": true,
  "message": "[DRY RUN] Would create invoice for \"Test Client Small\" — $75 — \"Consultation call — 30 minutes\"",
  "invoice_id": "DRY_RUN_ID"
}
```

### Expected MCP Response (DRY_RUN=false, Odoo running)
```json
{
  "success": true,
  "invoice_id": 42,
  "invoice_number": "INV/2026/0001",
  "customer": "Test Client Small",
  "amount": 75.00,
  "description": "Consultation call — 30 minutes",
  "state": "posted",
  "payment_state": "not_paid",
  "message": "Invoice INV/2026/0001 created and posted for Test Client Small — $75"
}
```

---

## Test Scenario 2: Large Invoice (> $100 — HITL required)

### Setup
Place this file in `/Needs_Action/`:

```markdown
---
type: odoo_invoice_request
customer: "Acme Corp"
amount: 1500.00
description: "AI Employee Gold Tier setup — March 2026"
source: whatsapp_watcher
status: pending
created: 2026-03-20T11:00:00Z
requires_approval: true
---

Client Acme Corp requested invoice for $1,500 AI setup project.
WhatsApp message: "Hey, can you send the invoice for the project we discussed?"
```

### Expected Behavior
1. OdooAccountant reads the file
2. Detects amount > $100 → HITL required
3. **Does NOT call create_invoice**
4. Writes `/Pending_Approval/ODOO_invoice_<id>.md`
5. Writes `/Plans/PLAN_odoo_invoice_Acme_Corp_20260320.md`
6. Updates Dashboard.md with pending count
7. Waits for human approval

### Expected Approval File
```
gold/vault/Pending_Approval/ODOO_invoice_abc12345.md
```
```yaml
---
type: approval_request
action: odoo_create_invoice
customer: Acme Corp
amount: 1500.00
description: "AI Employee Gold Tier setup — March 2026"
priority: high
status: pending
created: 2026-03-20T11:00:00Z
expires: 2026-03-21T11:00:00Z
requires_hitl: true
hitl_reason: Invoice > $100 requires human approval per Company_Handbook.md
---
```

### After Human Approval
Move the approval file to `/Approved/`.
Orchestrator detects it → calls OdooAccountant → creates invoice in Odoo.

---

## Test Scenario 3: Payment (always HITL)

### Setup
Place this file in `/Needs_Action/`:

```markdown
---
type: odoo_payment_request
invoice_id: "42"
amount: 1500.00
customer: "Acme Corp"
source: email_watcher
status: pending
created: 2026-03-20T14:00:00Z
requires_approval: true
---

Acme Corp sent payment confirmation email. Need to post payment against INV/2026/0001.
```

### Expected Behavior
1. OdooAccountant reads the file
2. Payment → ALWAYS HITL
3. Writes `/Pending_Approval/ODOO_payment_<id>.md`
4. Waits for human approval
5. After approval → calls `post_payment("42", 1500.00)`

---

## Running the Test

### With DRY_RUN=true (safe — no real Odoo calls)
```bash
# 1. Ensure DRY_RUN=true in gold/.env
grep DRY_RUN gold/.env

# 2. Create the test file
cp gold/vault/Accounting/Odoo/sample_invoice_flow_test.md \
   gold/vault/Needs_Action/ODOO_test_invoice_20260320.md

# 3. Run the OdooAccountant skill
# In Claude Code:
#   /odoo-accountant
# Or prompt Claude: "process the vault using the odoo-accountant skill"

# 4. Check results
ls gold/vault/Pending_Approval/ODOO_*.md
ls gold/vault/Done/ODOO_*.md
cat gold/vault/Accounting/Odoo/Current_Month.md
```

### With DRY_RUN=false (requires Odoo running)
```bash
# 1. Ensure Odoo is running
curl -s http://localhost:8069/web/database/list

# 2. Set DRY_RUN=false in gold/.env
# 3. Set ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD in gold/.env
# 4. Start odoo-mcp server (in .claude/settings.json or run manually)
# 5. Run the OdooAccountant skill
```

---

## Checklist — Phase 1 Test Criteria
- [ ] odoo-mcp server starts without errors: `node gold/mcp-servers/odoo-mcp/index.js`
- [ ] DRY_RUN mode returns correct mock responses
- [ ] Invoice ≤ $100 is auto-approved (no Pending_Approval file created)
- [ ] Invoice > $100 creates Pending_Approval file (does NOT call Odoo)
- [ ] Payment always creates Pending_Approval file
- [ ] list_open_invoices returns data (DRY_RUN or real)
- [ ] get_balance_sheet returns summary (DRY_RUN or real)
- [ ] Audit log written to `/Logs/`
- [ ] Dashboard.md updated after processing
- [ ] Source files moved to `/Done/` after completion
