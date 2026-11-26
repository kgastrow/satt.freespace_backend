#!/bin/bash
# Deployment script for Freespace API
# Usage: ./deploy.sh [environment]

set -e

ENVIRONMENT=${1:-production}
DEPLOY_DIR="/opt/freespace/backend"
REPO_DIR=$(dirname "$(dirname "$(readlink -f "$0")")")

echo "Deploying Freespace API to $ENVIRONMENT environment..."

# Create deployment directory if it doesn't exist
sudo mkdir -p $DEPLOY_DIR
sudo mkdir -p $DEPLOY_DIR/logs

# Copy application files
echo "Copying application files..."
sudo rsync -av --exclude='.git' --exclude='venv' --exclude='__pycache__' \
    --exclude='*.pyc' --exclude='.env' --exclude='test.db' \
    --exclude='config.json' --exclude='logs' --exclude='.venv' --exclude='tests' \
    $REPO_DIR/ $DEPLOY_DIR/

# Create virtual environment if it doesn't exist
if [ ! -d "$DEPLOY_DIR/venv" ]; then
    echo "Creating virtual environment..."
    sudo python3 -m venv $DEPLOY_DIR/venv
fi

# Install dependencies
echo "Installing dependencies..."
sudo $DEPLOY_DIR/venv/bin/pip install --upgrade pip
sudo $DEPLOY_DIR/venv/bin/pip install -r $DEPLOY_DIR/requirements.txt

# config.json is NOT copied from the repository (it holds secrets and is
# excluded from the rsync above). Create it once by hand from
# config.json.example; see docs/freespace-deployment.md.
if [ ! -f "$DEPLOY_DIR/config.json" ]; then
    echo "ERROR: $DEPLOY_DIR/config.json is missing. Create it from config.json.example first." >&2
    exit 1
fi

# Warn about the deprecated single-origin public_url key.
# It used to mean BOTH the frontend origin (emailed password-reset, invitation
# and unsubscribe links) and the backend origin (Twilio webhook signature
# verification). Those are now public_url_frontend and public_url_backend; the
# old key still works and back-fills both, but a split-origin deployment
# (see deploy/nginx.conf, which serves the API on its own api.* host) needs the
# two set separately or every emailed link points at the API host.
CONFIG_JSON="$DEPLOY_DIR/config.json"
if [ -f "$CONFIG_JSON" ] && grep -q '"public_url"' "$CONFIG_JSON"; then
    if ! grep -q '"public_url_frontend"' "$CONFIG_JSON"; then
        echo "WARNING: $CONFIG_JSON still uses the deprecated \"public_url\" key."
        echo "         Replace it with \"public_url_frontend\" (origin serving the SPA)"
        echo "         and \"public_url_backend\" (origin serving /api/v1)."
        echo "         See docs/public-url-split.md."
    fi
fi

# Run database migrations
echo "Running database migrations..."
cd $DEPLOY_DIR
sudo $DEPLOY_DIR/venv/bin/alembic upgrade head

# BN-4: redeploys must not lose engine state. All of it is in PostgreSQL, so
# a restart is safe; what is NOT safe is a destructive migration. Read every
# new file under alembic/versions/ for DROP/ALTER ... TYPE before running this
# against production, and take a backup first (scripts/backup/freespace_backup.sh).
# Neither seeder below deletes anything: seed_maintenance.py is additive and
# re-runnable; seed_first_tenant.py (bootstrap, first deployment only) must
# NEVER be run with --force-clear here.
echo "Seeding new code-owned reference data (additive)..."
sudo $DEPLOY_DIR/venv/bin/python scripts/seed_maintenance.py

# Set permissions
echo "Setting permissions..."
sudo chown -R www-data:www-data $DEPLOY_DIR
sudo chmod -R 750 $DEPLOY_DIR
sudo chmod 640 $DEPLOY_DIR/config.json
[ -f $DEPLOY_DIR/.env ] && sudo chmod 600 $DEPLOY_DIR/.env || true

# Install systemd services
echo "Installing systemd services..."
sudo cp $DEPLOY_DIR/deploy/freespace-api.service /etc/systemd/system/
sudo cp $DEPLOY_DIR/deploy/freespace-worker.service /etc/systemd/system/
sudo cp $DEPLOY_DIR/deploy/freespace-backup.service /etc/systemd/system/
sudo cp $DEPLOY_DIR/deploy/freespace-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start services
echo "Starting services..."
sudo systemctl enable freespace-api freespace-worker
sudo systemctl restart freespace-api freespace-worker
# Nightly backup timer (BF-83), only once the backup script is present and
# /etc/freespace/backup.env exists.
if [ -x "$DEPLOY_DIR/scripts/backup/freespace_backup.sh" ] && [ -f /etc/freespace/backup.env ]; then
    sudo systemctl enable --now freespace-backup.timer
else
    echo "NOTE: backup timer NOT enabled (need scripts/backup/freespace_backup.sh and /etc/freespace/backup.env)."
fi

# Check service status
echo "Checking service status..."
sleep 3
sudo systemctl status freespace-api --no-pager || true
sudo systemctl status freespace-worker --no-pager || true

# Health check
echo "Performing health check..."
sleep 2
# Liveness (process up, checks nothing):
curl -fs http://localhost:8000/health/live || echo "Health check failed - service may still be starting"
# BF-80 service health (database + engine tick); 503 until the worker has ticked:
curl -s http://localhost:8000/health || true

echo ""
echo "Deployment complete!"
echo "API is running at http://localhost:8000"
echo ""
echo "To view logs:"
echo "  journalctl -u freespace-api -f"
echo "  journalctl -u freespace-worker -f"
