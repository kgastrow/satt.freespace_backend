#!/bin/bash
# Deployment script for AYZER Webapp API
# Usage: ./deploy.sh [environment]

set -e

ENVIRONMENT=${1:-production}
DEPLOY_DIR="/opt/ayzer-webapp/backend"
REPO_DIR=$(dirname "$(dirname "$(readlink -f "$0")")")

echo "Deploying AYZER Webapp API to $ENVIRONMENT environment..."

# Create deployment directory if it doesn't exist
sudo mkdir -p $DEPLOY_DIR
sudo mkdir -p $DEPLOY_DIR/logs

# Copy application files
echo "Copying application files..."
sudo rsync -av --exclude='.git' --exclude='venv' --exclude='__pycache__' \
    --exclude='*.pyc' --exclude='.env' --exclude='test.db' \
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

# Copy environment file if it doesn't exist
if [ ! -f "$DEPLOY_DIR/.env" ]; then
    echo "Creating .env file from example..."
    sudo cp $DEPLOY_DIR/deploy/.env.example $DEPLOY_DIR/.env
    echo "WARNING: Please update $DEPLOY_DIR/.env with production values!"
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

# Set permissions
echo "Setting permissions..."
sudo chown -R www-data:www-data $DEPLOY_DIR
sudo chmod -R 750 $DEPLOY_DIR
sudo chmod 600 $DEPLOY_DIR/.env

# Install systemd services
echo "Installing systemd services..."
sudo cp $DEPLOY_DIR/deploy/ayzer-webapp-api.service /etc/systemd/system/
sudo cp $DEPLOY_DIR/deploy/ayzer-webapp-worker.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start services
echo "Starting services..."
sudo systemctl enable ayzer-webapp-api ayzer-webapp-worker
sudo systemctl restart ayzer-webapp-api ayzer-webapp-worker

# Check service status
echo "Checking service status..."
sleep 3
sudo systemctl status ayzer-webapp-api --no-pager || true
sudo systemctl status ayzer-webapp-worker --no-pager || true

# Health check
echo "Performing health check..."
sleep 2
curl -s http://localhost:8000/health || echo "Health check failed - service may still be starting"

echo ""
echo "Deployment complete!"
echo "API is running at http://localhost:8000"
echo ""
echo "To view logs:"
echo "  journalctl -u ayzer-webapp-api -f"
echo "  journalctl -u ayzer-webapp-worker -f"
