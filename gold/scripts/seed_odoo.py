#!/usr/bin/env python3
"""
seed_odoo.py — Seed Odoo with initial company data, chart of accounts,
               sample customers, and products for the AI Employee Gold Tier.

Usage:
    python3 gold/scripts/seed_odoo.py \
        --url http://localhost:8069 \
        --db odoo_ai_employee \
        --user admin \
        --password admin

Requires: Python 3.10+, requests library
    pip install requests
"""

import argparse
import json
import sys
import time
from urllib.request import urlopen, Request
from urllib.error import URLError


# ── Odoo JSON-RPC Client ───────────────────────────────────────────────────────

class OdooClient:
    def __init__(self, url: str, db: str, user: str, password: str):
        self.url = url.rstrip("/")
        self.db = db
        self.user = user
        self.password = password
        self.uid = None
        self._call_id = 0

    def _rpc(self, service: str, method: str, *args):
        self._call_id += 1
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "call",
            "id": self._call_id,
            "params": {"service": service, "method": method, "args": list(args)},
        }).encode()
        req = Request(
            f"{self.url}/jsonrpc",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        if "error" in result:
            raise RuntimeError(f"Odoo RPC error: {result['error']}")
        return result["result"]

    def authenticate(self):
        self.uid = self._rpc("common", "authenticate", self.db, self.user, self.password, {})
        if not self.uid:
            raise RuntimeError("Authentication failed — check credentials")
        print(f"  ✓ Authenticated as '{self.user}' (uid={self.uid})")
        return self.uid

    def execute(self, model: str, method: str, args=None, kwargs=None):
        return self._rpc(
            "object", "execute_kw",
            self.db, self.uid, self.password,
            model, method,
            args or [],
            kwargs or {},
        )

    def search(self, model: str, domain: list, fields: list = None) -> list:
        return self.execute(model, "search_read", [domain], {"fields": fields or [], "limit": 100})

    def create(self, model: str, vals: dict) -> int:
        return self.execute(model, "create", [vals])

    def write(self, model: str, ids: list, vals: dict) -> bool:
        return self.execute(model, "write", [ids, vals])


# ── Seed Functions ─────────────────────────────────────────────────────────────

def setup_company(client: OdooClient):
    """Configure the default company for the AI Employee."""
    print("\n[1/5] Setting up company...")

    companies = client.search("res.company", [], ["id", "name"])
    if not companies:
        cid = client.create("res.company", {
            "name": "AI Employee Demo Company",
            "email": "admin@aiemployee.demo",
            "phone": "+1 (555) 000-0000",
            "website": "https://aiemployee.demo",
            "currency_id": 2,  # USD typically id=2, may vary
        })
        print(f"  ✓ Created company (id={cid})")
    else:
        cid = companies[0]["id"]
        client.write("res.company", [cid], {
            "name": "AI Employee Demo Company",
            "email": "admin@aiemployee.demo",
        })
        print(f"  ✓ Updated company '{companies[0]['name']}' (id={cid})")

    return cid


def setup_chart_of_accounts(client: OdooClient, company_id: int):
    """Verify chart of accounts is installed (done via --init=account)."""
    print("\n[2/5] Verifying chart of accounts...")

    accounts = client.search(
        "account.account",
        [["company_id", "=", company_id]],
        ["id", "name", "code", "account_type"]
    )
    print(f"  ✓ Chart of accounts: {len(accounts)} accounts found")

    # Check for income account
    income_accounts = [a for a in accounts if "income" in (a.get("account_type") or "")]
    if income_accounts:
        print(f"  ✓ Income accounts: {len(income_accounts)} found")
        print(f"    Sample: {income_accounts[0]['code']} — {income_accounts[0]['name']}")
    else:
        print("  ⚠ No income accounts found — chart of accounts may need configuration")
        print("    Visit http://localhost:8069/odoo/accounting/chart-of-accounts to set up")


def setup_customers(client: OdooClient):
    """Create sample customers."""
    print("\n[3/5] Creating sample customers...")

    sample_customers = [
        {
            "name": "Acme Corp",
            "email": "billing@acme.example.com",
            "phone": "+1 (555) 100-0001",
            "website": "https://acme.example.com",
            "customer_rank": 1,
            "is_company": True,
            "comment": "Key enterprise client — monthly retainer",
        },
        {
            "name": "TechStart Ltd",
            "email": "accounts@techstart.example.com",
            "phone": "+1 (555) 100-0002",
            "customer_rank": 1,
            "is_company": True,
            "comment": "Startup client — project-based billing",
        },
        {
            "name": "GlobalBiz Inc",
            "email": "finance@globalbiz.example.com",
            "phone": "+1 (555) 100-0003",
            "customer_rank": 1,
            "is_company": True,
            "comment": "International client — hourly billing",
        },
        {
            "name": "Alice Johnson",
            "email": "alice@freelancer.example.com",
            "phone": "+1 (555) 200-0001",
            "customer_rank": 1,
            "is_company": False,
            "comment": "Individual client",
        },
    ]

    created = 0
    for customer in sample_customers:
        existing = client.search(
            "res.partner",
            [["name", "=", customer["name"]], ["customer_rank", ">", 0]],
            ["id", "name"]
        )
        if existing:
            print(f"  - '{customer['name']}' already exists (id={existing[0]['id']})")
        else:
            cid = client.create("res.partner", customer)
            print(f"  ✓ Created customer '{customer['name']}' (id={cid})")
            created += 1

    print(f"  ✓ {created} new customers created")


def setup_products(client: OdooClient):
    """Create sample products/services for invoicing."""
    print("\n[4/5] Creating sample products/services...")

    # Find income account
    accounts = client.search(
        "account.account",
        [["account_type", "in", ["income", "income_other"]]],
        ["id", "name", "code"]
    )
    income_account_id = accounts[0]["id"] if accounts else None

    sample_products = [
        {
            "name": "AI Strategy Consulting",
            "type": "service",
            "list_price": 200.00,
            "description": "Per-hour AI strategy and implementation consulting",
            "default_code": "CONSULT-HR",
            "sale_ok": True,
            "purchase_ok": False,
        },
        {
            "name": "AI Employee Gold Tier Setup",
            "type": "service",
            "list_price": 2500.00,
            "description": "Full Digital FTE Gold Tier setup and 6-month support",
            "default_code": "AI-GOLD",
            "sale_ok": True,
            "purchase_ok": False,
        },
        {
            "name": "MCP Server Development",
            "type": "service",
            "list_price": 1200.00,
            "description": "Custom MCP server development (per server)",
            "default_code": "MCP-DEV",
            "sale_ok": True,
            "purchase_ok": False,
        },
        {
            "name": "Monthly Maintenance Retainer",
            "type": "service",
            "list_price": 500.00,
            "description": "Monthly support and maintenance retainer",
            "default_code": "RETAINER-MO",
            "sale_ok": True,
            "purchase_ok": False,
        },
    ]

    if income_account_id:
        for p in sample_products:
            p["property_account_income_id"] = income_account_id

    created = 0
    for product in sample_products:
        existing = client.search(
            "product.product",
            [["name", "=", product["name"]]],
            ["id", "name"]
        )
        if existing:
            print(f"  - '{product['name']}' already exists")
        else:
            pid = client.create("product.template", product)
            print(f"  ✓ Created product '{product['name']}' @ ${product['list_price']} (id={pid})")
            created += 1

    print(f"  ✓ {created} new products created")


def create_sample_invoice(client: OdooClient):
    """Create a sample posted invoice to demonstrate the flow."""
    print("\n[5/5] Creating sample invoice for demonstration...")

    # Find Acme Corp
    partners = client.search(
        "res.partner",
        [["name", "ilike", "Acme Corp"]],
        ["id", "name"]
    )
    if not partners:
        print("  ⚠ Acme Corp not found — skipping sample invoice")
        return

    partner_id = partners[0]["id"]

    # Find income account
    accounts = client.search(
        "account.account",
        [["account_type", "in", ["income", "income_other"]]],
        ["id", "name"]
    )
    if not accounts:
        print("  ⚠ No income account found — skipping sample invoice")
        return

    account_id = accounts[0]["id"]

    # Check if a sample invoice already exists
    existing = client.search(
        "account.move",
        [
            ["partner_id", "=", partner_id],
            ["move_type", "=", "out_invoice"],
            ["ref", "=", "AI_EMPLOYEE_SAMPLE"]
        ],
        ["id", "name"]
    )
    if existing:
        print(f"  - Sample invoice already exists: {existing[0]['name']}")
        return

    invoice_id = client.create("account.move", {
        "move_type": "out_invoice",
        "partner_id": partner_id,
        "ref": "AI_EMPLOYEE_SAMPLE",
        "invoice_line_ids": [
            [0, 0, {
                "name": "AI Employee Gold Tier Setup — March 2026",
                "quantity": 1.0,
                "price_unit": 2500.00,
                "account_id": account_id,
            }]
        ],
    })

    # Post the invoice
    client.execute("account.move", "action_post", [[invoice_id]])

    # Fetch the invoice number
    invoice = client.search(
        "account.move",
        [["id", "=", invoice_id]],
        ["id", "name", "amount_total", "state"]
    )

    print(f"  ✓ Sample invoice created: {invoice[0]['name']} — $2,500.00 for Acme Corp")
    print(f"    Status: {invoice[0]['state']}")
    print(f"    Odoo invoice ID: {invoice_id}")
    print(f"    View at: http://localhost:8069/odoo/accounting/customer-invoices/{invoice_id}")

    return invoice_id


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed Odoo with AI Employee demo data")
    parser.add_argument("--url", default="http://localhost:8069", help="Odoo URL")
    parser.add_argument("--db", default="odoo_ai_employee", help="Database name")
    parser.add_argument("--user", default="admin", help="Admin username")
    parser.add_argument("--password", default="admin", help="Admin password")
    args = parser.parse_args()

    print("=" * 60)
    print("  Odoo Seed Script — AI Employee Gold Tier")
    print("=" * 60)
    print(f"  URL:      {args.url}")
    print(f"  Database: {args.db}")
    print(f"  User:     {args.user}")
    print("=" * 60)

    # Wait for Odoo to be ready
    print("\nWaiting for Odoo to be accessible...")
    for i in range(30):
        try:
            req = Request(f"{args.url}/web/database/list",
                         data=b'{"jsonrpc":"2.0","method":"call","params":{}}',
                         headers={"Content-Type": "application/json"})
            urlopen(req, timeout=5)
            print("  ✓ Odoo is accessible")
            break
        except (URLError, Exception):
            print(f"  ... attempt {i+1}/30", end="\r")
            time.sleep(2)
    else:
        print("\n  ✗ Odoo is not accessible after 60 seconds")
        print(f"  Make sure Odoo is running at {args.url}")
        sys.exit(1)

    client = OdooClient(args.url, args.db, args.user, args.password)

    try:
        client.authenticate()
        company_id = setup_company(client)
        setup_chart_of_accounts(client, company_id)
        setup_customers(client)
        setup_products(client)
        invoice_id = create_sample_invoice(client)

        print("\n" + "=" * 60)
        print("  Seed Complete!")
        print("=" * 60)
        print(f"  Odoo URL:      {args.url}")
        print(f"  Invoices:      {args.url}/odoo/accounting/customer-invoices")
        print(f"  Customers:     {args.url}/odoo/contacts")
        print(f"  Products:      {args.url}/odoo/inventory/products")
        if invoice_id:
            print(f"  Sample Invoice:{args.url}/odoo/accounting/customer-invoices/{invoice_id}")
        print("")
        print("  Update gold/.env:")
        print(f"    ODOO_URL={args.url}")
        print(f"    ODOO_DB={args.db}")
        print(f"    ODOO_USER={args.user}")
        print(f"    ODOO_PASSWORD={args.password}")
        print("=" * 60)

    except Exception as e:
        print(f"\n  ✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
