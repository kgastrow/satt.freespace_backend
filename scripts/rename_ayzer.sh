#!/bin/bash
set -euo pipefail

# =============================================================================
# Rename Script: Rename project from "ayzer" naming to a user-provided name
# =============================================================================
# Derives all naming variants and directory paths from a single input:
#
#   "my project"  →  snake: my_project      (dirs, files, services, queues)
#                     kebab: my-project      (deb packages, docker, S3)
#                     title: My Project      (descriptions, messages, UI)
#                     upper: MY PROJECT      (HTML title, PWA name)
#
# Usage:
#   ./scripts/rename_ayzer.sh "my project"
# =============================================================================

if [ $# -lt 1 ]; then
    echo "Usage: $0 <new-name>"
    echo ""
    echo "Examples:"
    echo "  $0 \"my project\""
    echo "  $0 \"cool app\""
    exit 1
fi

RAW_NAME="$1"

# Validate input: only letters, numbers, and spaces allowed
if ! echo "$RAW_NAME" | grep -qE '^[a-zA-Z][a-zA-Z0-9 ]*$'; then
    echo "Error: Name must start with a letter and contain only letters, numbers, and spaces."
    echo "  Special characters (&, /, \\, etc.) break sed replacements."
    exit 1
fi

# ---------------------------------------------------------------------------
# Derive naming variants
# ---------------------------------------------------------------------------
SNAKE=$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '_')
KEBAB=$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
TITLE=$(echo "$RAW_NAME" | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1')
UPPER=$(echo "$RAW_NAME" | tr '[:lower:]' '[:upper:]')

# Default ServerName: <snake>.example.com (customize via prompt below)
SERVER_NAME="${SNAKE}.example.com"

echo "Renaming project to: ${RAW_NAME}"
echo "  snake_case : ${SNAKE}"
echo "  kebab-case : ${KEBAB}"
echo "  Title Case : ${TITLE}"
echo "  UPPER CASE : ${UPPER}"
echo ""
echo "  Backend install dir  : /home/${SNAKE}"
echo "  Backend deploy dir   : /opt/${KEBAB}/backend"
echo "  Frontend install dir : /var/www/${SNAKE}"
echo "  Backend service      : ${SNAKE}_backend.service"
echo "  Worker service       : ${SNAKE}_worker.service"
echo "  Deploy API service   : ${KEBAB}-api.service"
echo "  Deploy worker service: ${KEBAB}-worker.service"
echo "  Apache config        : ${SNAKE}.conf"
echo "  Apache ServerName    : ${SERVER_NAME}"
echo "  ARQ queue            : arq:${SNAKE}_backend"
echo "  S3 bucket            : ${KEBAB}-files"
echo ""

# ---------------------------------------------------------------------------
# Optional customizations (interactive prompts, press Enter to keep defaults)
# ---------------------------------------------------------------------------
read -rp "Website URL for sidebar links [https://ayzer.ai]: " input_url
WEBSITE_URL="${input_url:-https://ayzer.ai}"

read -rp "Logo symbol asset filename [A_symbol.svg]: " input_symbol
LOGO_SYMBOL="${input_symbol:-A_symbol.svg}"

read -rp "Logo wordmark asset filename [AYZER_wordmark.svg]: " input_wordmark
LOGO_WORDMARK="${input_wordmark:-AYZER_wordmark.svg}"

read -rp "Apache ServerName [${SERVER_NAME}]: " input_servername
SERVER_NAME="${input_servername:-${SERVER_NAME}}"

SERVER_ALIAS="www.${SERVER_NAME}"
read -rp "Apache ServerAlias [${SERVER_ALIAS}]: " input_serveralias
SERVER_ALIAS="${input_serveralias:-${SERVER_ALIAS}}"

echo ""
echo "  Website URL  : ${WEBSITE_URL}"
echo "  Logo symbol  : ${LOGO_SYMBOL}"
echo "  Logo wordmark: ${LOGO_WORDMARK}"
echo "  ServerName   : ${SERVER_NAME}"
echo "  ServerAlias  : ${SERVER_ALIAS}"
echo ""

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
if sed --version >/dev/null 2>&1; then
    SED_INPLACE=(sed -i)
else
    SED_INPLACE=(sed -i '')
fi

replace_in() {
    local file="$1"
    shift
    if [ -f "$file" ]; then
        "${SED_INPLACE[@]}" "$@" "$file"
    fi
}

# ---------------------------------------------------------------------------
# Phase 1: File renames
# ---------------------------------------------------------------------------
echo "=== Phase 1: File renames ==="

# Apache config — find whatever .conf exists and rename it
APACHE_DIR="app/backend/apache_site_config"
NEW_APACHE="${APACHE_DIR}/${SNAKE}.conf"
if [ -d "$APACHE_DIR" ]; then
    for conf in "$APACHE_DIR"/*.conf; do
        [ -f "$conf" ] || continue
        if [ "$conf" != "$NEW_APACHE" ]; then
            git mv "$conf" "$NEW_APACHE"
            echo "  Renamed $(basename "$conf") → $(basename "$NEW_APACHE")"
        fi
    done
fi

# Initscripts systemd service files — remove old, create new
for old_svc in app/backend/initscripts/ayzer_backend.service \
               app/backend/initscripts/ayzer_worker.service; do
    if [ -f "$old_svc" ]; then
        git rm "$old_svc"
        echo "  Removed $(basename "$old_svc")"
    fi
done

NEW_BACKEND_SVC="app/backend/initscripts/${SNAKE}_backend.service"
if [ ! -f "$NEW_BACKEND_SVC" ]; then
    cat > "$NEW_BACKEND_SVC" << SVCEOF
[Unit]
Description=${TITLE} Backend Service
After=syslog.target network.target

[Service]
Type=simple
WorkingDirectory=/home/${SNAKE}/
ExecStart=/bin/bash -c "PORT=\$\$(/home/${SNAKE}/.venv/bin/python3 -c 'import json; print(json.load(open(\"config.json\"))[\"server\"][\"port\"])' 2>/dev/null || echo 8000); exec /home/${SNAKE}/.venv/bin/gunicorn --workers=4 --worker-class=uvicorn.workers.UvicornWorker --bind=127.0.0.1:\$\$PORT --log-level=info main:app"
Restart=on-failure

[Install]
WantedBy=multi-user.target
SVCEOF
    echo "  Created $(basename "$NEW_BACKEND_SVC")"
fi

NEW_WORKER_SVC="app/backend/initscripts/${SNAKE}_worker.service"
if [ ! -f "$NEW_WORKER_SVC" ]; then
    cat > "$NEW_WORKER_SVC" << SVCEOF
[Unit]
Description=${TITLE} ARQ Background Worker
After=syslog.target network.target redis.service ${SNAKE}_backend.service

[Service]
Type=simple
WorkingDirectory=/home/${SNAKE}/
ExecStart=/home/${SNAKE}/.venv/bin/arq src.workers.worker.WorkerSettings
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF
    echo "  Created $(basename "$NEW_WORKER_SVC")"
fi

# Deploy service files — rename
DEPLOY_DIR="app/backend/deploy"
OLD_DEPLOY_API="${DEPLOY_DIR}/ayzer-webapp-api.service"
NEW_DEPLOY_API="${DEPLOY_DIR}/${KEBAB}-api.service"
if [ -f "$OLD_DEPLOY_API" ] && [ "$OLD_DEPLOY_API" != "$NEW_DEPLOY_API" ]; then
    git mv "$OLD_DEPLOY_API" "$NEW_DEPLOY_API"
    echo "  Renamed $(basename "$OLD_DEPLOY_API") → $(basename "$NEW_DEPLOY_API")"
fi

OLD_DEPLOY_WORKER="${DEPLOY_DIR}/ayzer-webapp-worker.service"
NEW_DEPLOY_WORKER="${DEPLOY_DIR}/${KEBAB}-worker.service"
if [ -f "$OLD_DEPLOY_WORKER" ] && [ "$OLD_DEPLOY_WORKER" != "$NEW_DEPLOY_WORKER" ]; then
    git mv "$OLD_DEPLOY_WORKER" "$NEW_DEPLOY_WORKER"
    echo "  Renamed $(basename "$OLD_DEPLOY_WORKER") → $(basename "$NEW_DEPLOY_WORKER")"
fi

echo ""

# ---------------------------------------------------------------------------
# Phase 2: Content replacements
# ---------------------------------------------------------------------------
echo "=== Phase 2: Content replacements ==="

# ---- Build / deploy infrastructure ----

# --- Backend apache site config ---
APACHE_CONF="app/backend/apache_site_config/${SNAKE}.conf"
replace_in "$APACHE_CONF" \
    -e "s|ServerName [^ ]*|ServerName ${SERVER_NAME}|g" \
    -e "s|ServerAlias [^ ]*|ServerAlias ${SERVER_ALIAS}|g" \
    -e "s|DocumentRoot /var/www/[a-zA-Z0-9_-]*|DocumentRoot /var/www/${SNAKE}|g" \
    -e "s|<Directory /var/www/[a-zA-Z0-9_-]*>|<Directory /var/www/${SNAKE}>|g"
echo "  Updated apache site config (ServerName: ${SERVER_NAME}, ServerAlias: ${SERVER_ALIAS})"

# --- Backend initscripts/control ---
replace_in app/backend/initscripts/control \
    -e "s/^Package: .*/Package: ${KEBAB}-backend/" \
    -e "s/^Description: .* Backend$/Description: ${TITLE} Backend/"
echo "  Updated backend control file"

# --- Backend initscripts/postinst ---
replace_in app/backend/initscripts/postinst \
    -e "s|INSTALL_DIR=\"/home/[a-zA-Z0-9_]*\"|INSTALL_DIR=\"/home/${SNAKE}\"|g" \
    -e "s|sites-available/[a-zA-Z0-9_]*\.conf|sites-available/${SNAKE}.conf|g" \
    -e "s|apache_site_config/[a-zA-Z0-9_]*\.conf|apache_site_config/${SNAKE}.conf|g" \
    -e "s|a2ensite [a-zA-Z0-9_]*|a2ensite ${SNAKE}|g" \
    -e "s|enable [a-zA-Z0-9_]*_backend\.service|enable ${SNAKE}_backend.service|g" \
    -e "s|enable [a-zA-Z0-9_]*_worker\.service|enable ${SNAKE}_worker.service|g" \
    -e "s|start [a-zA-Z0-9_]*_backend\.service|start ${SNAKE}_backend.service|g" \
    -e "s|start [a-zA-Z0-9_]*_worker\.service|start ${SNAKE}_worker.service|g" \
    -e "s|Adding .* Backend services|Adding ${TITLE} Backend services|g" \
    -e "s|Starting .* Backend applications|Starting ${TITLE} Backend applications|g" \
    -e "s|.* Backend installed successfully|${TITLE} Backend installed successfully|g"
echo "  Updated backend postinst"

# --- Backend initscripts/prerm ---
replace_in app/backend/initscripts/prerm \
    -e "s|stop [a-zA-Z0-9_]*_worker\.service|stop ${SNAKE}_worker.service|g" \
    -e "s|stop [a-zA-Z0-9_]*_backend\.service|stop ${SNAKE}_backend.service|g" \
    -e "s|disable [a-zA-Z0-9_]*_worker\.service|disable ${SNAKE}_worker.service|g" \
    -e "s|disable [a-zA-Z0-9_]*_backend\.service|disable ${SNAKE}_backend.service|g" \
    -e "s|Stopping .* Backend services|Stopping ${TITLE} Backend services|g" \
    -e "s|Removing .* Backend services|Removing ${TITLE} Backend services|g" \
    -e "s|a2dissite [a-zA-Z0-9_]*\.conf|a2dissite ${SNAKE}.conf|g"
echo "  Updated backend prerm"

# --- Backend initscripts systemd service files ---
for svc in "app/backend/initscripts/${SNAKE}_backend.service" \
           "app/backend/initscripts/${SNAKE}_worker.service"; do
    if [ -f "$svc" ]; then
        replace_in "$svc" \
            -e "s|WorkingDirectory=/home/[a-zA-Z0-9_]*/|WorkingDirectory=/home/${SNAKE}/|g" \
            -e "s|/home/[a-zA-Z0-9_]*/\.venv|/home/${SNAKE}/.venv|g" \
            -e "s|redis\.service [a-zA-Z0-9_]*_backend\.service|redis.service ${SNAKE}_backend.service|g" \
            -e "s|Description=.* Backend Service|Description=${TITLE} Backend Service|" \
            -e "s|Description=.* ARQ Background Worker|Description=${TITLE} ARQ Background Worker|"
        echo "  Updated $(basename "$svc")"
    fi
done

# --- Backend make_pkg ---
replace_in app/backend/make_pkg \
    -e "s|PACKAGE_NAME=\"[a-zA-Z0-9_-]*-backend\"|PACKAGE_NAME=\"${KEBAB}-backend\"|" \
    -e "s|INSTALL_DIR=\"/home/[a-zA-Z0-9_]*\"|INSTALL_DIR=\"/home/${SNAKE}\"|" \
    -e "s|initscripts/[a-zA-Z0-9_]*_backend\.service|initscripts/${SNAKE}_backend.service|g" \
    -e "s|initscripts/[a-zA-Z0-9_]*_worker\.service|initscripts/${SNAKE}_worker.service|g" \
    -e "s|apache_site_config/[a-zA-Z0-9_]*\.conf|apache_site_config/${SNAKE}.conf|g"
echo "  Updated backend make_pkg"

# --- Frontend initscripts/control ---
replace_in app/frontend/initscripts/control \
    -e "s/^Package: .*/Package: ${KEBAB}-frontend/" \
    -e "s/^Description: .* Frontend$/Description: ${TITLE} Frontend/"
echo "  Updated frontend control file"

# --- Frontend initscripts/postinst ---
replace_in app/frontend/initscripts/postinst \
    -e "s|INSTALL_DIR=\"/var/www/[a-zA-Z0-9_]*\"|INSTALL_DIR=\"/var/www/${SNAKE}\"|g" \
    -e "s|.* Frontend installed successfully|${TITLE} Frontend installed successfully|g"
echo "  Updated frontend postinst"

# --- Frontend initscripts/prerm ---
replace_in app/frontend/initscripts/prerm \
    -e "s|Removing .* Frontend|Removing ${TITLE} Frontend|g"
echo "  Updated frontend prerm"

# --- Frontend make_pkg ---
replace_in app/frontend/make_pkg \
    -e "s|PACKAGE_NAME=\"[a-zA-Z0-9_-]*-frontend\"|PACKAGE_NAME=\"${KEBAB}-frontend\"|" \
    -e "s|DESCRIPTION=\".* Frontend\"|DESCRIPTION=\"${TITLE} Frontend\"|" \
    -e "s|INSTALL_DIR=\"/var/www/[a-zA-Z0-9_]*\"|INSTALL_DIR=\"/var/www/${SNAKE}\"|" \
    -e "s|Debian package for the .* React frontend|Debian package for the ${TITLE} React frontend|"
echo "  Updated frontend make_pkg"

# ---- Deploy directory (deploy.sh, nginx.conf, service files) ----

# --- deploy/deploy.sh ---
replace_in app/backend/deploy/deploy.sh \
    -e "s|Deployment script for .* API|Deployment script for ${TITLE} API|" \
    -e "s|DEPLOY_DIR=\"/opt/[a-zA-Z0-9_-]*/backend\"|DEPLOY_DIR=\"/opt/${KEBAB}/backend\"|" \
    -e "s|Deploying .* API to|Deploying ${TITLE} API to|" \
    -e "s|deploy/[a-zA-Z0-9_-]*-api\.service|deploy/${KEBAB}-api.service|g" \
    -e "s|deploy/[a-zA-Z0-9_-]*-worker\.service|deploy/${KEBAB}-worker.service|g" \
    -e "s|enable [a-zA-Z0-9_-]*-api [a-zA-Z0-9_-]*-worker|enable ${KEBAB}-api ${KEBAB}-worker|g" \
    -e "s|restart [a-zA-Z0-9_-]*-api [a-zA-Z0-9_-]*-worker|restart ${KEBAB}-api ${KEBAB}-worker|g" \
    -e "s|status [a-zA-Z0-9_-]*-api |status ${KEBAB}-api |g" \
    -e "s|status [a-zA-Z0-9_-]*-worker |status ${KEBAB}-worker |g" \
    -e "s|journalctl -u [a-zA-Z0-9_-]*-api|journalctl -u ${KEBAB}-api|g" \
    -e "s|journalctl -u [a-zA-Z0-9_-]*-worker|journalctl -u ${KEBAB}-worker|g"
echo "  Updated deploy/deploy.sh"

# --- deploy/nginx.conf ---
replace_in app/backend/deploy/nginx.conf \
    -e "s|Nginx configuration for .* API|Nginx configuration for ${TITLE} API|" \
    -e "s|sites-available/[a-zA-Z0-9_-]*-api|sites-available/${KEBAB}-api|" \
    -e "s|upstream [a-zA-Z0-9_]*_webapp_api|upstream ${SNAKE}_api|g" \
    -e "s|server_name api\.[a-zA-Z0-9_-]*\.example\.com|server_name api.${KEBAB}.example.com|g" \
    -e "s|letsencrypt/live/api\.[a-zA-Z0-9_-]*\.example\.com|letsencrypt/live/api.${KEBAB}.example.com|g" \
    -e "s|nginx/[a-zA-Z0-9_-]*-api-access|nginx/${KEBAB}-api-access|g" \
    -e "s|nginx/[a-zA-Z0-9_-]*-api-error|nginx/${KEBAB}-api-error|g" \
    -e "s|proxy_pass http://[a-zA-Z0-9_]*_webapp_api|proxy_pass http://${SNAKE}_api|g"
echo "  Updated deploy/nginx.conf"

# --- deploy/ service files (API + worker) ---
for svc in "app/backend/deploy/${KEBAB}-api.service" \
           "app/backend/deploy/${KEBAB}-worker.service"; do
    if [ -f "$svc" ]; then
        replace_in "$svc" \
            -e "s|Description=.* API (FastAPI/Uvicorn)|Description=${TITLE} API (FastAPI/Uvicorn)|" \
            -e "s|Description=.* ARQ Background Worker|Description=${TITLE} ARQ Background Worker|" \
            -e "s|WorkingDirectory=/opt/[a-zA-Z0-9_-]*/backend|WorkingDirectory=/opt/${KEBAB}/backend|g" \
            -e "s|Environment=\"PATH=/opt/[a-zA-Z0-9_-]*/backend|Environment=\"PATH=/opt/${KEBAB}/backend|g" \
            -e "s|EnvironmentFile=/opt/[a-zA-Z0-9_-]*/backend|EnvironmentFile=/opt/${KEBAB}/backend|g" \
            -e "s|ExecStart=/opt/[a-zA-Z0-9_-]*/backend|ExecStart=/opt/${KEBAB}/backend|g" \
            -e "s|ReadWritePaths=/opt/[a-zA-Z0-9_-]*/backend|ReadWritePaths=/opt/${KEBAB}/backend|g"
        echo "  Updated $(basename "$svc")"
    fi
done

# ---- Docker compose ----

for dc in app/backend/docker-compose.yml app/backend/docker-compose.prod.yml; do
    if [ -f "$dc" ]; then
        # Container names: match "container_name: <anything>-<suffix>"
        replace_in "$dc" \
            -e "s|container_name: [a-zA-Z0-9_-]*-postgres$|container_name: ${KEBAB}-postgres|g" \
            -e "s|container_name: [a-zA-Z0-9_-]*-pgbouncer$|container_name: ${KEBAB}-pgbouncer|g" \
            -e "s|container_name: [a-zA-Z0-9_-]*-redis$|container_name: ${KEBAB}-redis|g" \
            -e "s|container_name: [a-zA-Z0-9_-]*-api$|container_name: ${KEBAB}-api|g" \
            -e "s|container_name: [a-zA-Z0-9_-]*-worker$|container_name: ${KEBAB}-worker|g" \
            -e "s|container_name: [a-zA-Z0-9_-]*-nginx$|container_name: ${KEBAB}-nginx|g"

        # Network name: appears as "- <name>" references and as top-level "<name>:" definition
        # First handle the specific ayzer pattern, then handle any previously-renamed pattern
        replace_in "$dc" \
            -e "s|ayzer-webapp-network|${KEBAB}-network|g"
        echo "  Updated $(basename "$dc")"
    fi
done

# ---- Backend source code ----

# --- ARQ queue names ---
for f in app/backend/src/services/tasks.py \
         app/backend/src/workers/settings.py \
         app/backend/src/workers/worker.py; do
    if [ -f "$f" ]; then
        replace_in "$f" \
            -e "s|\"arq:[a-zA-Z0-9_]*\"|\"arq:${SNAKE}_backend\"|g"
        echo "  Updated ARQ queue name in $(basename "$f")"
    fi
done

# --- config.py (APP_NAME, API docs defaults, S3 bucket, config.json fallbacks) ---
replace_in app/backend/src/core/config.py \
    -e "s|APP_NAME: str = \"[^\"]*\"|APP_NAME: str = \"${TITLE} Webapp\"|" \
    -e "s|API_DOCS_USERNAME: str = \"[^\"]*\"|API_DOCS_USERNAME: str = \"${SNAKE}\"|" \
    -e "s|API_DOCS_PASSWORD: str = \"[^\"]*\"|API_DOCS_PASSWORD: str = \"${SNAKE}\"|" \
    -e "s|S3_BUCKET: str = \"[^\"]*-files\"|S3_BUCKET: str = \"${KEBAB}-files\"|" \
    -e "s|app\.get(\"name\", \"[^\"]*\")|app.get(\"name\", \"${TITLE} Webapp\")|" \
    -e "s|s3\.get(\"bucket\", \"[^\"]*-files\")|s3.get(\"bucket\", \"${KEBAB}-files\")|" \
    -e "s|\"username\", \"ayzer\"|\"username\", \"${SNAKE}\"|g" \
    -e "s|\"password\", \"ayzer\"|\"password\", \"${SNAKE}\"|g"
echo "  Updated config.py (APP_NAME, API docs creds, S3 bucket, fallbacks)"

# --- two_factor.py (TOTP issuer) ---
replace_in app/backend/src/services/two_factor.py \
    -e "s|issuer: str = \"[A-Z][A-Z]*\"|issuer: str = \"${UPPER}\"|" \
    -e "s|Issuer name (default: [A-Z][A-Z]*)|Issuer name (default: ${UPPER})|"
echo "  Updated two_factor.py issuer"

# --- 2FA test assertion ---
replace_in app/backend/tests/unit_tests/test_two_factor_auth.py \
    -e "s|assert \"[A-Z][A-Z]*\" in unquote(uri)|assert \"${UPPER}\" in unquote(uri)|"
echo "  Updated test_two_factor_auth.py"

# --- config.json.example (api_docs creds) ---
replace_in app/backend/config.json.example \
    -e "s|\"username\": \"ayzer\"|\"username\": \"${SNAKE}\"|g" \
    -e "s|\"password\": \"ayzer\"|\"password\": \"${SNAKE}\"|g"
echo "  Updated config.json.example"

# --- Makefile ---
replace_in app/backend/Makefile \
    -e "s|# Makefile for .* Backend|# Makefile for ${TITLE} Backend|" \
    -e "s|echo \".* Backend - Available Commands\"|echo \"${TITLE} Backend - Available Commands\"|"
echo "  Updated Makefile"

# --- locustfile.py ---
replace_in app/backend/perf/locustfile.py \
    -e "s|load testing the .* API|load testing the ${TITLE} API|"
echo "  Updated locustfile.py"

# ---- Frontend ----

# --- index.html ---
replace_in app/frontend/index.html \
    -e "s|<title>[^<]*</title>|<title>${UPPER}</title>|"
echo "  Updated index.html title"

# --- offline.html ---
replace_in app/frontend/public/offline.html \
    -e "s|<title>Offline - [^<]*</title>|<title>Offline - ${UPPER}</title>|"
echo "  Updated offline.html title"

# --- vite.config.ts (PWA fallback name) ---
replace_in app/frontend/vite.config.ts \
    -e "s#process\.env\.VITE_PWA_APP_NAME || '[^']*'#process.env.VITE_PWA_APP_NAME || '${UPPER}'#g"
echo "  Updated vite.config.ts PWA name"

# --- Frontend .env.example (PWA name + API docs creds) ---
replace_in app/frontend/.env.example \
    -e "s|^VITE_PWA_APP_NAME=.*|VITE_PWA_APP_NAME=${UPPER}|" \
    -e "s|^API_DOCS_USERNAME=.*|API_DOCS_USERNAME=${SNAKE}|" \
    -e "s|^API_DOCS_PASSWORD=.*|API_DOCS_PASSWORD=${SNAKE}|"
echo "  Updated frontend .env.example"

# --- Locales (en/common.json app name — scoped to "app" block) ---
replace_in app/frontend/src/locales/en/common.json \
    -e "/\"app\"/{n;s|\"name\": \"[^\"]*\"|\"name\": \"${UPPER}\"|;}"
echo "  Updated en/common.json app name"

# --- NotificationSettingsPage.tsx placeholders ---
replace_in app/frontend/src/pages/admin/NotificationSettingsPage.tsx \
    -e "s|placeholder=\"[A-Z][A-Za-z]* Webapp\"|placeholder=\"${TITLE} Webapp\"|g" \
    -e "s|placeholder=\"[A-Z][A-Z]*\" maxLength|placeholder=\"${UPPER}\" maxLength|g"
echo "  Updated NotificationSettingsPage.tsx placeholders"

# --- AppSidebar.tsx (logo alt text, website URL, asset filenames) ---
replace_in app/frontend/src/components/AppSidebar.tsx \
    -e "s|alt=\"[A-Z][A-Z]*\"|alt=\"${UPPER}\"|g" \
    -e "s|href=\"https://ayzer\.ai\"|href=\"${WEBSITE_URL}\"|g" \
    -e "s|src=\"/A_symbol\.svg\"|src=\"/${LOGO_SYMBOL}\"|g" \
    -e "s|src=\"/AYZER_wordmark\.svg\"|src=\"/${LOGO_WORDMARK}\"|g"
echo "  Updated AppSidebar.tsx (alt text, URL, logos)"

# ---- Ruff / tooling ----

replace_in app/backend/ruff.toml \
    -e "s|# Ruff configuration for .* Webapp Backend|# Ruff configuration for ${TITLE} Webapp Backend|"
echo "  Updated ruff.toml comment"

# ---- Scripts ----

for script in scripts/start.sh scripts/stop_apps.sh scripts/setup-system-deps.sh; do
    if [ -f "$script" ]; then
        replace_in "$script" \
            -e "s|Starting .* Webapp.*\"|Starting ${TITLE} Webapp...\"|g" \
            -e "s|Stopping .* Webapp.*\"|Stopping ${TITLE} Webapp...\"|g" \
            -e "s|[A-Z][A-Za-z ]* Webapp[A-Za-z ]* - System Dependencies|${TITLE} Webapp - System Dependencies|g" \
            -e "s|# PostgreSQL 15 (added by .* setup)|# PostgreSQL 15 (added by ${SNAKE} setup)|g"
        echo "  Updated $(basename "$script")"
    fi
done

replace_in scripts/generate-api-types.sh \
    -e "s|API_DOCS_USERNAME=\"\${API_DOCS_USERNAME:-[^}]*}\"|API_DOCS_USERNAME=\"\${API_DOCS_USERNAME:-${SNAKE}}\"|" \
    -e "s|API_DOCS_PASSWORD=\"\${API_DOCS_PASSWORD:-[^}]*}\"|API_DOCS_PASSWORD=\"\${API_DOCS_PASSWORD:-${SNAKE}}\"|"
echo "  Updated generate-api-types.sh defaults"

replace_in scripts/claude-aliases.sh \
    -e "s|/ayzer\.webapp\.template/|/${KEBAB}/|g"
echo "  Updated claude-aliases.sh"

# ---- ADW modules ----

replace_in adws/adw_modules/database_ops.py \
    -e "s|\"user\": \"ayzer-webapp-user\"|\"user\": \"${KEBAB}-user\"|" \
    -e "s|\"password\": \"ayzer-webapp-pass\"|\"password\": \"${KEBAB}-pass\"|" \
    -e "s|\"db\": \"ayzer-webapp\"|\"db\": \"${KEBAB}\"|"
echo "  Updated adws/adw_modules/database_ops.py"

replace_in adws/adw_tests/test_smoke_standalone.py \
    -e "s|ayzer-webapp-template|${KEBAB}|g"
echo "  Updated adws/adw_tests/test_smoke_standalone.py"

# ---- .env.sample (Command Center agent identity) ----

replace_in .env.sample \
    -e "s|CODEBASE_NAME=ayzer-webapp-template|CODEBASE_NAME=${KEBAB}|"
echo "  Updated .env.sample (CODEBASE_NAME)"

# Create .env from .env.sample if it doesn't exist
if [ ! -f .env ]; then
    cp .env.sample .env
    echo "  Created .env from .env.sample"
else
    echo "  .env already exists — skipping copy (update manually if needed)"
fi

# ---- package-lock.json ----

replace_in package-lock.json \
    -e "s|\"name\": \"ayzer\.webapp\.template\"|\"name\": \"${KEBAB}\"|"
echo "  Updated package-lock.json"

# ---- Documentation ----

replace_in CLAUDE.md \
    -e "s|# AYZER Webapp Template|# ${TITLE} Webapp|" \
    -e "s|ayzer-webapp-template|${KEBAB}|g"
echo "  Updated CLAUDE.md"

replace_in README.md \
    -e "s|# AYZER Webapp Template|# ${TITLE} Webapp|" \
    -e "s|ayzer-webapp-template|${KEBAB}|g" \
    -e "s|cd ayzer-webapp-template|cd ${KEBAB}|g" \
    -e "s|ayzer-webapp-api|${KEBAB}-api|g" \
    -e "s|ayzer-webapp-worker|${KEBAB}-worker|g" \
    -e "s|Username\`: \`ayzer\`|Username\`: \`${SNAKE}\`|g" \
    -e "s|Password\`: \`ayzer\`|Password\`: \`${SNAKE}\`|g"
echo "  Updated README.md"

replace_in docs/2fa-configuration.md \
    -e "s|AYZER Webapp Template|${TITLE} Webapp|g" \
    -e "s|\"name\": \"AYZER\"|\"name\": \"${UPPER}\"|g" \
    -e "s|issuer=AYZER|issuer=${UPPER}|g" \
    -e "s|AYZER:user@example|${UPPER}:user@example|g"
echo "  Updated docs/2fa-configuration.md"

replace_in app_docs/openapi-typescript-generation.md \
    -e "s|\`ayzer\`/\`ayzer\`|\`${SNAKE}\`/\`${SNAKE}\`|g"
echo "  Updated app_docs/openapi-typescript-generation.md"

replace_in app_docs/chrome-smoke-testing.md \
    -e "s|ayzer\.webapp\.template|${KEBAB}|g"
echo "  Updated app_docs/chrome-smoke-testing.md"

for aidoc in ai_docs/skills/frontend_dev.md ai_docs/skills/context_expert.md; do
    if [ -f "$aidoc" ]; then
        replace_in "$aidoc" \
            -e "s|AYZER Webapp|${TITLE} Webapp|g"
        echo "  Updated $(basename "$aidoc")"
    fi
done

replace_in ai_docs/backend/context/background_jobs.md \
    -e "s|ayzer-webapp-worker\.service|${KEBAB}-worker.service|g" \
    -e "s|/opt/ayzer-webapp/backend|/opt/${KEBAB}/backend|g"
echo "  Updated ai_docs/backend/context/background_jobs.md"

echo ""

# ---------------------------------------------------------------------------
# Phase 3: Report remaining old references
# ---------------------------------------------------------------------------
echo "=== Phase 3: Remaining 'ayzer' references ==="
echo "These files still contain 'ayzer' and may need manual review"
echo "(domain names, emails, SVG assets, docs, ADW modules, etc.):"
echo ""
grep -ri --include='*.py' --include='*.sh' --include='*.ts' --include='*.tsx' \
    --include='*.json' --include='*.yml' --include='*.yaml' --include='*.html' \
    --include='*.toml' --include='*.example' --include='*.env*' --include='*.conf' \
    --include='*.md' --include='*.service' --include='Makefile' \
    -l 'ayzer' . 2>/dev/null \
    | grep -v '.git/' | grep -v 'node_modules/' | grep -v 'rename_ayzer' \
    | sort || echo "  (none found)"

echo ""
echo "=== Done ==="
echo "Review the changes with: git diff"
echo "Consider removing this script: git rm scripts/rename_ayzer.sh"
