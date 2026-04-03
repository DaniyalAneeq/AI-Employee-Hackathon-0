/**
 * odoo-mcp — MCP Server for Odoo Community 19+ (JSON-RPC API)
 *
 * Tools exposed:
 *   create_invoice       — Create a customer invoice in Odoo
 *   list_open_invoices   — List all open (unpaid) invoices
 *   post_payment         — Register a payment against an invoice
 *   get_balance_sheet    — Fetch a high-level financial summary
 *
 * Configuration (env vars):
 *   ODOO_URL      — e.g. http://localhost:8069
 *   ODOO_DB       — e.g. odoo_ai_employee
 *   ODOO_USER     — admin username
 *   ODOO_PASSWORD — admin password
 *   DRY_RUN       — "true" to skip actual Odoo calls (logs only)
 *
 * Reference: https://www.odoo.com/documentation/19.0/developer/reference/external_api.html
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { createRequire } from "module";
import { readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

// Load .env from gold/ directory
const __dirname = dirname(fileURLToPath(import.meta.url));
const envPath = resolve(__dirname, "../../.env");
if (existsSync(envPath)) {
  const envContent = readFileSync(envPath, "utf8");
  for (const line of envContent.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, "");
    if (!process.env[key]) process.env[key] = val;
  }
}

// ── Configuration ──────────────────────────────────────────────────────────────
const ODOO_URL = process.env.ODOO_URL || "http://localhost:8069";
const ODOO_DB = process.env.ODOO_DB || "odoo_ai_employee";
const ODOO_USER = process.env.ODOO_USER || "admin";
const ODOO_PASSWORD = process.env.ODOO_PASSWORD || "admin";
const DRY_RUN = process.env.DRY_RUN?.toLowerCase() === "true";

// ── Odoo JSON-RPC Client ───────────────────────────────────────────────────────
let _uid = null;

async function jsonrpc(service, method, params) {
  const body = JSON.stringify({
    jsonrpc: "2.0",
    method: "call",
    id: Date.now(),
    params: { service, method, args: params },
  });

  const resp = await fetch(`${ODOO_URL}/jsonrpc`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });

  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  }

  const data = await resp.json();
  if (data.error) {
    throw new Error(`Odoo RPC error: ${JSON.stringify(data.error)}`);
  }
  return data.result;
}

async function authenticate() {
  if (_uid) return _uid;
  _uid = await jsonrpc("common", "authenticate", [
    ODOO_DB,
    ODOO_USER,
    ODOO_PASSWORD,
    {},
  ]);
  if (!_uid) throw new Error("Odoo authentication failed — check credentials");
  return _uid;
}

async function executeKw(model, method, args, kwargs = {}) {
  const uid = await authenticate();
  return jsonrpc("object", "execute_kw", [
    ODOO_DB,
    uid,
    ODOO_PASSWORD,
    model,
    method,
    args,
    kwargs,
  ]);
}

// ── Tool Implementations ───────────────────────────────────────────────────────

/**
 * Find or create a partner (customer) by name. Returns partner_id.
 */
async function findOrCreatePartner(customerName) {
  const results = await executeKw("res.partner", "search_read", [
    [["name", "ilike", customerName], ["customer_rank", ">", 0]],
    { fields: ["id", "name"], limit: 1 },
  ]);
  if (results.length > 0) return results[0].id;

  // Create new partner
  return executeKw("res.partner", "create", [
    { name: customerName, customer_rank: 1 },
  ]);
}

/**
 * create_invoice — creates a draft customer invoice in Odoo
 */
async function createInvoice(customer, amount, description) {
  if (DRY_RUN) {
    return {
      dry_run: true,
      message: `[DRY RUN] Would create invoice for "${customer}" — $${amount} — "${description}"`,
      invoice_id: "DRY_RUN_ID",
    };
  }

  const partnerId = await findOrCreatePartner(customer);

  // Find default income account (account_type = 'income' or 'other_income')
  const accounts = await executeKw("account.account", "search_read", [
    [
      ["account_type", "in", ["income", "income_other"]],
      ["company_id.id", "=", 1],
    ],
    { fields: ["id", "name"], limit: 1 },
  ]);

  if (accounts.length === 0) {
    throw new Error(
      "No income account found. Please set up a chart of accounts in Odoo first."
    );
  }
  const accountId = accounts[0].id;

  const invoiceId = await executeKw("account.move", "create", [
    {
      move_type: "out_invoice",
      partner_id: partnerId,
      invoice_line_ids: [
        [
          0,
          0,
          {
            name: description,
            quantity: 1.0,
            price_unit: parseFloat(amount),
            account_id: accountId,
          },
        ],
      ],
    },
  ]);

  // Confirm (post) the invoice
  await executeKw("account.move", "action_post", [[invoiceId]]);

  // Fetch the confirmed invoice details
  const invoice = await executeKw("account.move", "read", [
    [invoiceId],
    { fields: ["id", "name", "amount_total", "state", "payment_state"] },
  ]);

  return {
    success: true,
    invoice_id: invoiceId,
    invoice_number: invoice[0]?.name,
    customer,
    amount: parseFloat(amount),
    description,
    state: invoice[0]?.state,
    payment_state: invoice[0]?.payment_state,
    message: `Invoice ${invoice[0]?.name} created and posted for ${customer} — $${amount}`,
  };
}

/**
 * list_open_invoices — returns all unpaid customer invoices
 */
async function listOpenInvoices() {
  if (DRY_RUN) {
    return {
      dry_run: true,
      invoices: [
        {
          id: 1,
          name: "INV/2026/0001",
          partner: "Sample Customer",
          amount_due: 1500.0,
          due_date: "2026-04-01",
        },
      ],
    };
  }

  const invoices = await executeKw("account.move", "search_read", [
    [
      ["move_type", "=", "out_invoice"],
      ["payment_state", "in", ["not_paid", "partial"]],
      ["state", "=", "posted"],
    ],
    {
      fields: [
        "id",
        "name",
        "partner_id",
        "amount_total",
        "amount_residual",
        "invoice_date_due",
        "payment_state",
      ],
    },
  ]);

  return {
    count: invoices.length,
    invoices: invoices.map((inv) => ({
      id: inv.id,
      name: inv.name,
      partner: inv.partner_id?.[1] || "Unknown",
      amount_total: inv.amount_total,
      amount_due: inv.amount_residual,
      due_date: inv.invoice_date_due || "N/A",
      payment_state: inv.payment_state,
    })),
  };
}

/**
 * post_payment — registers a payment against an invoice
 */
async function postPayment(invoiceId, amount) {
  if (DRY_RUN) {
    return {
      dry_run: true,
      message: `[DRY RUN] Would post payment of $${amount} against invoice ID ${invoiceId}`,
    };
  }

  // Read the invoice to get partner_id
  const invoice = await executeKw("account.move", "read", [
    [parseInt(invoiceId)],
    {
      fields: [
        "id",
        "name",
        "partner_id",
        "amount_residual",
        "currency_id",
        "state",
      ],
    },
  ]);

  if (!invoice || invoice.length === 0) {
    throw new Error(`Invoice ID ${invoiceId} not found`);
  }

  const inv = invoice[0];
  if (inv.state !== "posted") {
    throw new Error(`Invoice ${inv.name} is not in 'posted' state`);
  }

  // Find the default payment journal (bank or cash)
  const journals = await executeKw("account.journal", "search_read", [
    [["type", "in", ["bank", "cash"]], ["company_id.id", "=", 1]],
    { fields: ["id", "name"], limit: 1 },
  ]);

  if (journals.length === 0) {
    throw new Error("No bank/cash journal found. Set up journals in Odoo.");
  }

  const paymentId = await executeKw("account.payment", "create", [
    {
      payment_type: "inbound",
      partner_type: "customer",
      partner_id: inv.partner_id[0],
      amount: parseFloat(amount),
      journal_id: journals[0].id,
      currency_id: inv.currency_id[0],
      memo: `Payment for ${inv.name}`,
    },
  ]);

  // Post the payment
  await executeKw("account.payment", "action_post", [[paymentId]]);

  // Reconcile with invoice
  const payment = await executeKw("account.payment", "read", [
    [paymentId],
    { fields: ["id", "name", "move_id"] },
  ]);

  if (payment[0]?.move_id) {
    const moveLinesPayment = await executeKw(
      "account.move.line",
      "search_read",
      [
        [
          ["move_id", "=", payment[0].move_id[0]],
          ["account_id.account_type", "in", ["asset_receivable"]],
        ],
        { fields: ["id"] },
      ]
    );

    const moveLinesInvoice = await executeKw(
      "account.move.line",
      "search_read",
      [
        [
          ["move_id", "=", parseInt(invoiceId)],
          ["account_id.account_type", "in", ["asset_receivable"]],
        ],
        { fields: ["id"] },
      ]
    );

    const lineIds = [
      ...moveLinesPayment.map((l) => l.id),
      ...moveLinesInvoice.map((l) => l.id),
    ];

    if (lineIds.length >= 2) {
      await executeKw("account.move.line", "reconcile", [lineIds]);
    }
  }

  return {
    success: true,
    payment_id: paymentId,
    invoice_id: invoiceId,
    invoice_name: inv.name,
    amount_paid: parseFloat(amount),
    message: `Payment of $${amount} posted for invoice ${inv.name}`,
  };
}

/**
 * get_balance_sheet — fetches a high-level P&L and AR summary
 */
async function getBalanceSheet() {
  if (DRY_RUN) {
    return {
      dry_run: true,
      summary: {
        total_invoiced: 15000.0,
        total_collected: 9500.0,
        outstanding_ar: 5500.0,
        open_invoice_count: 3,
      },
    };
  }

  // Total posted invoices
  const allPosted = await executeKw("account.move", "search_read", [
    [["move_type", "=", "out_invoice"], ["state", "=", "posted"]],
    { fields: ["amount_total", "amount_residual", "payment_state"] },
  ]);

  const totalInvoiced = allPosted.reduce((s, i) => s + i.amount_total, 0);
  const totalOutstanding = allPosted.reduce((s, i) => s + i.amount_residual, 0);
  const totalCollected = totalInvoiced - totalOutstanding;
  const openCount = allPosted.filter((i) =>
    ["not_paid", "partial"].includes(i.payment_state)
  ).length;

  // Total vendor bills (expenses)
  const bills = await executeKw("account.move", "search_read", [
    [["move_type", "=", "in_invoice"], ["state", "=", "posted"]],
    { fields: ["amount_total"] },
  ]);
  const totalExpenses = bills.reduce((s, b) => s + b.amount_total, 0);

  return {
    summary: {
      total_invoiced: parseFloat(totalInvoiced.toFixed(2)),
      total_collected: parseFloat(totalCollected.toFixed(2)),
      outstanding_ar: parseFloat(totalOutstanding.toFixed(2)),
      open_invoice_count: openCount,
      total_expenses: parseFloat(totalExpenses.toFixed(2)),
      estimated_net: parseFloat((totalCollected - totalExpenses).toFixed(2)),
    },
    generated_at: new Date().toISOString(),
  };
}

// ── MCP Server Setup ───────────────────────────────────────────────────────────
const server = new Server(
  { name: "odoo-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "create_invoice",
      description:
        "Create a customer invoice in Odoo. NOTE: Invoices > $100 require HITL approval — the OdooAccountant skill handles this automatically.",
      inputSchema: {
        type: "object",
        properties: {
          customer: {
            type: "string",
            description: "Customer name (will be created if not found)",
          },
          amount: {
            type: "number",
            description: "Invoice total amount in USD",
          },
          description: {
            type: "string",
            description: "Line item description for the invoice",
          },
        },
        required: ["customer", "amount", "description"],
      },
    },
    {
      name: "list_open_invoices",
      description:
        "List all open (unpaid or partially paid) customer invoices from Odoo.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "post_payment",
      description:
        "Register a payment against an invoice in Odoo. NOTE: Always requires HITL approval before calling — the OdooAccountant skill enforces this.",
      inputSchema: {
        type: "object",
        properties: {
          invoice_id: {
            type: "string",
            description: "Odoo invoice ID (numeric)",
          },
          amount: {
            type: "number",
            description: "Payment amount in USD",
          },
        },
        required: ["invoice_id", "amount"],
      },
    },
    {
      name: "get_balance_sheet",
      description:
        "Get a high-level financial summary from Odoo: total invoiced, collected, outstanding AR, and net estimate.",
      inputSchema: { type: "object", properties: {} },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    let result;
    switch (name) {
      case "create_invoice":
        result = await createInvoice(args.customer, args.amount, args.description);
        break;
      case "list_open_invoices":
        result = await listOpenInvoices();
        break;
      case "post_payment":
        result = await postPayment(args.invoice_id, args.amount);
        break;
      case "get_balance_sheet":
        result = await getBalanceSheet();
        break;
      default:
        throw new Error(`Unknown tool: ${name}`);
    }

    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  } catch (err) {
    return {
      content: [{ type: "text", text: `Error: ${err.message}` }],
      isError: true,
    };
  }
});

// ── Start Server ───────────────────────────────────────────────────────────────
const transport = new StdioServerTransport();
await server.connect(transport);
console.error(`odoo-mcp server running (DRY_RUN=${DRY_RUN}, URL=${ODOO_URL})`);
