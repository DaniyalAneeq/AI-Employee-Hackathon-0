#!/usr/bin/env bash
# =============================================================================
# verify_setup.sh — Check that Option B (Odoo) and Option C (Meta) are ready
#
# Usage: bash gold/scripts/verify_setup.sh
# Run from: repo root (Hackathon-0-AI-Employee-main/)
# =============================================================================

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

GOLD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$GOLD_DIR/.env"

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
info() { echo -e "  ${BLUE}→${NC} $1"; }
hdr()  { echo -e "\n${BOLD}$1${NC}"; }

# Load .env
[ -f "$ENV_FILE" ] && export $(grep -v '^#' "$ENV_FILE" | grep '=' | xargs) 2>/dev/null

# ══════════════════════════════════════════════════════════════════════════════
hdr "═══ ENVIRONMENT ════════════════════════════════"
# ══════════════════════════════════════════════════════════════════════════════

if [ -f "$ENV_FILE" ]; then ok ".env file exists"; else fail ".env missing — copy .env.example"; fi

DRY="${DRY_RUN:-true}"
if [ "$DRY" = "false" ]; then
    ok "DRY_RUN=false (live mode)"
else
    warn "DRY_RUN=$DRY (mock mode — set DRY_RUN=false for live calls)"
fi

# ══════════════════════════════════════════════════════════════════════════════
hdr "═══ OPTION B — ODOO ════════════════════════════"
# ══════════════════════════════════════════════════════════════════════════════

# Docker check
if command -v docker &>/dev/null; then
    ok "Docker is installed"
    if docker info &>/dev/null 2>&1; then
        ok "Docker daemon is running"
    else
        fail "Docker daemon not running — start Docker Desktop"
    fi
else
    fail "Docker not found — install Docker Desktop + enable WSL integration"
fi

# Container status
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    DB_STATUS=$(docker compose -f "$GOLD_DIR/docker-compose.yml" ps db --format "{{.Status}}" 2>/dev/null || echo "not running")
    ODOO_STATUS=$(docker compose -f "$GOLD_DIR/docker-compose.yml" ps odoo --format "{{.Status}}" 2>/dev/null || echo "not running")

    if echo "$DB_STATUS" | grep -qi "healthy\|running"; then
        ok "PostgreSQL container: running"
    else
        fail "PostgreSQL container: not running (run setup script)"
        info "docker compose -f gold/docker-compose.yml up -d"
    fi

    if echo "$ODOO_STATUS" | grep -qi "healthy\|running"; then
        ok "Odoo container: running"
    else
        fail "Odoo container: not running"
    fi
fi

# Odoo HTTP check
ODOO_URL="${ODOO_URL:-http://localhost:8069}"
if curl -sf "$ODOO_URL/web/health" &>/dev/null; then
    ok "Odoo is accessible at $ODOO_URL"
else
    fail "Odoo not accessible at $ODOO_URL"
    info "Run: bash gold/scripts/setup_odoo_docker.sh"
fi

# Odoo auth check
ODOO_DB="${ODOO_DB:-odoo_ai_employee}"
ODOO_USER="${ODOO_USER:-admin}"
ODOO_PASSWORD="${ODOO_PASSWORD:-admin}"

if curl -sf "$ODOO_URL/web/health" &>/dev/null; then
    AUTH_RESULT=$(curl -sf -X POST "$ODOO_URL/jsonrpc" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"params\":{\"service\":\"common\",\"method\":\"authenticate\",\"args\":[\"$ODOO_DB\",\"$ODOO_USER\",\"$ODOO_PASSWORD\",{}]}}" \
        2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result','fail'))" 2>/dev/null || echo "fail")

    if [ "$AUTH_RESULT" != "fail" ] && [ "$AUTH_RESULT" != "False" ] && [ -n "$AUTH_RESULT" ]; then
        ok "Odoo authentication works (uid=$AUTH_RESULT)"
    else
        fail "Odoo auth failed — check ODOO_USER/ODOO_PASSWORD in .env"
        info "Current: user=$ODOO_USER, db=$ODOO_DB"
    fi
fi

# MCP server check
MCP_PATH="$GOLD_DIR/mcp-servers/odoo-mcp/index.js"
if [ -f "$MCP_PATH" ]; then
    ok "odoo-mcp server file exists"
    if [ -d "$GOLD_DIR/mcp-servers/odoo-mcp/node_modules" ]; then
        ok "odoo-mcp npm packages installed"
    else
        fail "odoo-mcp npm packages missing — run: cd gold/mcp-servers/odoo-mcp && npm install"
    fi
else
    fail "odoo-mcp/index.js not found"
fi

# settings.json check
SETTINGS="$(dirname "$GOLD_DIR")/.claude/settings.json"
if [ -f "$SETTINGS" ]; then
    if grep -q "odoo-mcp" "$SETTINGS"; then
        ok ".claude/settings.json has odoo-mcp registered"
        SETTINGS_DRY=$(python3 -c "
import json
with open('$SETTINGS') as f: d = json.load(f)
servers = d.get('mcpServers', {})
odoo = servers.get('odoo-mcp', {})
print(odoo.get('env',{}).get('DRY_RUN','true'))
" 2>/dev/null)
        if [ "$SETTINGS_DRY" = "false" ]; then
            ok "settings.json DRY_RUN=false for odoo-mcp"
        else
            warn "settings.json DRY_RUN=$SETTINGS_DRY for odoo-mcp — update to 'false' for live calls"
        fi
    else
        fail "odoo-mcp not in .claude/settings.json"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
hdr "═══ OPTION C — META (Facebook + Instagram) ════"
# ══════════════════════════════════════════════════════════════════════════════

# .env variables
if [ -n "${META_PAGE_ID:-}" ]; then
    ok "META_PAGE_ID set: ${META_PAGE_ID}"
else
    fail "META_PAGE_ID not set in .env"
    info "Get from: Facebook Page → About section"
fi

if [ -n "${META_PAGE_ACCESS_TOKEN:-}" ]; then
    TOKEN_LEN=${#META_PAGE_ACCESS_TOKEN}
    ok "META_PAGE_ACCESS_TOKEN set (${TOKEN_LEN} chars)"
else
    fail "META_PAGE_ACCESS_TOKEN not set in .env"
    info "Get from: developers.facebook.com → Graph API Explorer"
fi

if [ -n "${META_IG_USER_ID:-}" ]; then
    ok "META_IG_USER_ID set: ${META_IG_USER_ID}"
else
    warn "META_IG_USER_ID not set — Instagram posting will be unavailable"
    info "Get: Graph API Explorer → GET /{page-id}?fields=instagram_business_account"
fi

# Token validity check (only if token is set)
if [ -n "${META_PAGE_ACCESS_TOKEN:-}" ] && [ -n "${META_PAGE_ID:-}" ]; then
    TOKEN_CHECK=$(curl -sf \
        "https://graph.facebook.com/v19.0/me?access_token=${META_PAGE_ACCESS_TOKEN}" \
        2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if 'error' in d: print('ERR:' + d['error']['message'])
    else: print('OK:' + d.get('name','?'))
except: print('PARSE_ERROR')
" 2>/dev/null || echo "NETWORK_ERROR")

    if echo "$TOKEN_CHECK" | grep -q "^OK:"; then
        NAME=$(echo "$TOKEN_CHECK" | sed 's/OK://')
        ok "Meta token is valid (account: $NAME)"
    elif echo "$TOKEN_CHECK" | grep -q "^ERR:"; then
        MSG=$(echo "$TOKEN_CHECK" | sed 's/ERR://')
        fail "Meta token invalid: $MSG"
        info "Get a new token from: developers.facebook.com/tools/explorer"
    else
        warn "Could not validate Meta token (network issue or not connected)"
    fi
fi

# MCP server check
META_MCP="$GOLD_DIR/mcp-servers/meta-social-mcp/index.js"
if [ -f "$META_MCP" ]; then
    ok "meta-social-mcp server file exists"
    if [ -d "$GOLD_DIR/mcp-servers/meta-social-mcp/node_modules" ]; then
        ok "meta-social-mcp npm packages installed"
    else
        fail "meta-social-mcp npm packages missing — run: cd gold/mcp-servers/meta-social-mcp && npm install"
    fi
else
    fail "meta-social-mcp/index.js not found"
fi

if [ -f "$SETTINGS" ]; then
    if grep -q "meta-social-mcp" "$SETTINGS"; then
        ok ".claude/settings.json has meta-social-mcp registered"
    else
        fail "meta-social-mcp not in .claude/settings.json"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
hdr "═══ VAULT STRUCTURE ════════════════════════════"
# ══════════════════════════════════════════════════════════════════════════════

VAULT="$GOLD_DIR/vault"
for dir in Needs_Action Pending_Approval Approved Rejected Done Plans Logs Briefings "Accounting/Odoo"; do
    if [ -d "$VAULT/$dir" ]; then
        COUNT=$(find "$VAULT/$dir" -name "*.md" 2>/dev/null | wc -l)
        ok "$dir/ exists ($COUNT .md files)"
    else
        fail "$dir/ missing"
    fi
done

# ══════════════════════════════════════════════════════════════════════════════
hdr "═══ QUICK TEST COMMANDS ════════════════════════"
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "  ${BOLD}In Claude Code (from repo root):${NC}"
echo "    /odoo-accountant        → Test Odoo invoice HITL flow"
echo "    /meta-social-poster     → Test Facebook/Instagram post flow"
echo "    /vault-processor        → Process all Needs_Action items"
echo ""
echo -e "  ${BOLD}Docker commands (from gold/ directory):${NC}"
echo "    docker compose ps                   → Check container status"
echo "    docker compose logs -f odoo         → Follow Odoo logs"
echo "    docker compose down                 → Stop containers"
echo "    docker compose down -v              → Stop + wipe data"
echo ""
echo -e "  ${BOLD}Odoo URLs:${NC}"
echo "    http://localhost:8069                          → Dashboard"
echo "    http://localhost:8069/odoo/accounting          → Accounting"
echo "    http://localhost:8069/odoo/accounting/customer-invoices → Invoices"
echo "    http://localhost:8069/odoo/contacts            → Customers"
echo ""
