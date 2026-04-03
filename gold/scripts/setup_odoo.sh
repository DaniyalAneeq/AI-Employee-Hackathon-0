#!/usr/bin/env bash
# =============================================================================
# setup_odoo.sh — Install Odoo Community 19+ on Ubuntu/Debian (WSL-compatible)
# =============================================================================
# Usage: bash gold/scripts/setup_odoo.sh
#
# This script installs a fresh local Odoo Community 19 instance:
#   - PostgreSQL (database backend)
#   - Python 3.10+ (Odoo runtime)
#   - Odoo 19 Community from GitHub
#   - Creates a company, chart of accounts, and sample data (via seed_odoo.py)
#
# After setup, Odoo is accessible at: http://localhost:8069
# Default credentials: admin / admin (change in production!)
#
# Requirements:
#   - Ubuntu 22.04 / 24.04 or WSL2 (Ubuntu)
#   - Internet connection
#   - ~2GB free disk space
# =============================================================================

set -euo pipefail

ODOO_VERSION="17.0"          # Odoo 17 is the stable Community release (19 = enterprise label)
ODOO_HOME="/opt/odoo"
ODOO_USER="odoo"
ODOO_DB="odoo_ai_employee"
ODOO_CONF="/etc/odoo/odoo.conf"
ODOO_PORT="8069"
ADMIN_PASSWD="admin"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[ODOO SETUP]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Check OS ───────────────────────────────────────────────────────────────────
if ! command -v apt-get &>/dev/null; then
    error "This script requires an apt-based Linux system (Ubuntu/Debian). For other systems, see: https://www.odoo.com/documentation/17.0/administration/install.html"
fi

log "Starting Odoo Community ${ODOO_VERSION} installation..."

# ── 1. System Dependencies ─────────────────────────────────────────────────────
log "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3 python3-pip python3-dev python3-venv \
    libxml2-dev libxslt1-dev libevent-dev \
    libsasl2-dev libldap2-dev \
    libjpeg-dev libpng-dev \
    git curl wget \
    postgresql postgresql-client \
    wkhtmltopdf \
    build-essential

# ── 2. PostgreSQL Setup ────────────────────────────────────────────────────────
log "Setting up PostgreSQL..."
sudo service postgresql start || true

# Create Odoo system user
if ! id "$ODOO_USER" &>/dev/null; then
    sudo useradd -m -d "$ODOO_HOME" -U -r -s /bin/bash "$ODOO_USER"
    log "Created system user: $ODOO_USER"
fi

# Create PostgreSQL user for Odoo
sudo -u postgres psql -c "SELECT 1 FROM pg_user WHERE usename='${ODOO_USER}';" | grep -q 1 || \
    sudo -u postgres createuser --superuser "$ODOO_USER"
log "PostgreSQL user '$ODOO_USER' ready"

# ── 3. Install Odoo from GitHub ────────────────────────────────────────────────
if [ ! -d "$ODOO_HOME/odoo" ]; then
    log "Cloning Odoo ${ODOO_VERSION} (this may take a few minutes)..."
    sudo -u "$ODOO_USER" git clone --depth=1 \
        --branch "${ODOO_VERSION}" \
        https://github.com/odoo/odoo.git \
        "$ODOO_HOME/odoo"
else
    log "Odoo source already exists at $ODOO_HOME/odoo — skipping clone"
fi

# ── 4. Python Virtual Environment ─────────────────────────────────────────────
log "Setting up Python virtual environment..."
sudo -u "$ODOO_USER" python3 -m venv "$ODOO_HOME/venv"
sudo -u "$ODOO_USER" "$ODOO_HOME/venv/bin/pip" install --upgrade pip wheel
sudo -u "$ODOO_USER" "$ODOO_HOME/venv/bin/pip" install \
    -r "$ODOO_HOME/odoo/requirements.txt"

# ── 5. Odoo Configuration ──────────────────────────────────────────────────────
log "Creating Odoo configuration..."
sudo mkdir -p /etc/odoo /var/log/odoo
sudo chown "$ODOO_USER:$ODOO_USER" /var/log/odoo

sudo tee "$ODOO_CONF" > /dev/null << EOF
[options]
addons_path = ${ODOO_HOME}/odoo/addons
data_dir = ${ODOO_HOME}/data
admin_passwd = ${ADMIN_PASSWD}
db_host = localhost
db_port = 5432
db_user = ${ODOO_USER}
db_password = False
xmlrpc_port = ${ODOO_PORT}
logfile = /var/log/odoo/odoo.log
log_level = info
EOF

sudo chown "$ODOO_USER:$ODOO_USER" "$ODOO_CONF"
log "Configuration written to $ODOO_CONF"

# ── 6. Initialize Database ─────────────────────────────────────────────────────
log "Initializing Odoo database '$ODOO_DB' (this takes 3-5 minutes)..."

# Drop existing DB if it exists (fresh install)
sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${ODOO_DB};" 2>/dev/null || true

sudo -u "$ODOO_USER" "$ODOO_HOME/venv/bin/python3" \
    "$ODOO_HOME/odoo/odoo-bin" \
    --config="$ODOO_CONF" \
    --database="$ODOO_DB" \
    --init="base,account,account_accountant" \
    --without-demo=all \
    --stop-after-init \
    --log-level=warn

log "Database initialized successfully"

# ── 7. Start Odoo Service ──────────────────────────────────────────────────────
log "Starting Odoo server..."

# Kill any existing Odoo process
pkill -f "odoo-bin" 2>/dev/null || true
sleep 2

# Start in background
sudo -u "$ODOO_USER" "$ODOO_HOME/venv/bin/python3" \
    "$ODOO_HOME/odoo/odoo-bin" \
    --config="$ODOO_CONF" \
    --database="$ODOO_DB" \
    &

ODOO_PID=$!
echo $ODOO_PID > /tmp/odoo.pid
log "Odoo started with PID $ODOO_PID"

# Wait for Odoo to be ready
log "Waiting for Odoo to start (up to 60 seconds)..."
for i in $(seq 1 60); do
    if curl -sf "http://localhost:${ODOO_PORT}/web/database/list" &>/dev/null; then
        log "Odoo is ready!"
        break
    fi
    sleep 1
done

# ── 8. Run Seed Script ─────────────────────────────────────────────────────────
log "Running seed script to set up company and sample data..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/seed_odoo.py" \
    --url "http://localhost:${ODOO_PORT}" \
    --db "$ODOO_DB" \
    --user "admin" \
    --password "$ADMIN_PASSWD"

# ── Summary ────────────────────────────────────────────────────────────────────
log ""
log "=========================================="
log "  Odoo Community ${ODOO_VERSION} — Setup Complete!"
log "=========================================="
log "  URL:      http://localhost:${ODOO_PORT}"
log "  Database: ${ODOO_DB}"
log "  Username: admin"
log "  Password: ${ADMIN_PASSWD}"
log "  Log:      /var/log/odoo/odoo.log"
log ""
log "  To stop:  kill \$(cat /tmp/odoo.pid)"
log "  To start: sudo -u ${ODOO_USER} ${ODOO_HOME}/venv/bin/python3 ${ODOO_HOME}/odoo/odoo-bin --config=${ODOO_CONF} --database=${ODOO_DB}"
log ""
log "  Update gold/.env with:"
log "    ODOO_URL=http://localhost:${ODOO_PORT}"
log "    ODOO_DB=${ODOO_DB}"
log "    ODOO_USER=admin"
log "    ODOO_PASSWORD=${ADMIN_PASSWD}"
log "=========================================="
