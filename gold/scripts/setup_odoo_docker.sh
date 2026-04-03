#!/usr/bin/env bash
# =============================================================================
# setup_odoo_docker.sh — Start Odoo + PostgreSQL via Docker Compose
#                         Seed with demo data for AI Employee Gold Tier
#
# Usage:
#   bash gold/scripts/setup_odoo_docker.sh
#
# What this does:
#   1. Verifies Docker is running
#   2. Initializes Odoo database (installs accounting modules) — one-time
#   3. Starts PostgreSQL + Odoo containers
#   4. Waits for Odoo to be ready
#   5. Seeds demo data (company, customers, products, sample invoice)
#
# Run from the repo ROOT:
#   cd /mnt/d/AI/.../Hackathon-0-AI-Employee-main
#   bash gold/scripts/setup_odoo_docker.sh
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
GOLD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log()  { echo -e "${GREEN}[ODOO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

log "Gold dir: $GOLD_DIR"
cd "$GOLD_DIR"

# ── 1. Verify Docker ───────────────────────────────────────────────────────────
log "Checking Docker..."
command -v docker &>/dev/null || err "Docker not found. Install Docker Desktop and enable WSL integration."
docker info &>/dev/null       || err "Docker daemon not running. Start Docker Desktop."
command -v docker &>/dev/null && docker compose version &>/dev/null || err "docker compose plugin not found."
log "Docker OK"

# ── 2. Initialize database (first time only) ───────────────────────────────────
# Check if database already exists by looking at the volume
if docker volume inspect ai_employee_odoo_data &>/dev/null; then
    warn "Odoo data volume already exists — skipping init (use 'docker compose down -v' for fresh start)"
else
    log "First-time setup: initializing Odoo database + accounting modules..."
    log "This takes 3-5 minutes — please wait..."

    # Start PostgreSQL first
    docker compose up -d db
    log "Waiting for PostgreSQL to be healthy..."
    for i in $(seq 1 30); do
        docker compose exec db pg_isready -U odoo &>/dev/null && break
        sleep 2
        echo -n "."
    done
    echo ""
    log "PostgreSQL ready"

    # Run the init container (installs base + account modules, then exits)
    docker compose --profile init run --rm odoo-init
    log "Database initialized"
fi

# ── 3. Start all services ──────────────────────────────────────────────────────
log "Starting all services (PostgreSQL + Odoo)..."
docker compose up -d db odoo

# ── 4. Wait for Odoo to be ready ──────────────────────────────────────────────
log "Waiting for Odoo to be ready (up to 3 minutes)..."
for i in $(seq 1 36); do
    if curl -sf http://localhost:8069/web/health &>/dev/null; then
        echo ""
        log "Odoo is ready!"
        break
    fi
    echo -n "."
    sleep 5
    if [ "$i" -eq 36 ]; then
        echo ""
        warn "Odoo didn't respond in time. Check logs: docker compose logs odoo"
    fi
done

# ── 5. Seed demo data ──────────────────────────────────────────────────────────
log "Seeding Odoo with demo data..."
python3 "$GOLD_DIR/scripts/seed_odoo.py" \
    --url  http://localhost:8069 \
    --db   odoo_ai_employee \
    --user admin \
    --password admin

# ── 6. Summary ─────────────────────────────────────────────────────────────────
echo ""
log "============================================"
log "  Odoo is running!"
log "============================================"
log "  Web UI:    http://localhost:8069"
log "  Login:     admin / admin"
log "  DB:        odoo_ai_employee"
log ""
log "  Invoices:  http://localhost:8069/odoo/accounting/customer-invoices"
log "  Contacts:  http://localhost:8069/odoo/contacts"
log ""
log "  Stop:      docker compose down          (keeps data)"
log "  Wipe:      docker compose down -v       (deletes all data)"
log "  Logs:      docker compose logs -f odoo"
log "============================================"
log ""
log "  Now update gold/.env:"
log "    ODOO_URL=http://localhost:8069"
log "    ODOO_DB=odoo_ai_employee"
log "    ODOO_USER=admin"
log "    ODOO_PASSWORD=admin"
log "    DRY_RUN=false"
log "============================================"
