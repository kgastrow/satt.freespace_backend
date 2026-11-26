#!/bin/bash
#
# System Dependencies Setup Script
# Run this script manually to install and configure PostgreSQL, PgBouncer, and Redis
#
# Usage: ./scripts/setup-system-deps.sh
#

set -e

# Get script directory for relative paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "AYZER Webapp Template - System Dependencies"
echo "============================================"
echo ""

# ============================================
# Check for existing config.json
# ============================================

CONFIG_FILE="$PROJECT_ROOT/app/backend/config.json"
CONFIG_EXAMPLE="$PROJECT_ROOT/app/backend/config.json.example"
USE_EXISTING_CONFIG=false

if [[ -f "$CONFIG_FILE" ]]; then
    echo "Found existing config.json at $CONFIG_FILE"
    echo ""
    read -p "Use credentials from existing config.json? [Y/n]: " USE_EXISTING
    USE_EXISTING=${USE_EXISTING:-Y}

    if [[ "$USE_EXISTING" =~ ^[Yy]$ ]]; then
        USE_EXISTING_CONFIG=true
        # Parse credentials from config.json using grep/sed (portable)
        DB_NAME=$(grep -o '"db": *"[^"]*"' "$CONFIG_FILE" | head -1 | sed 's/"db": *"\([^"]*\)"/\1/')
        DB_USER=$(grep -o '"user": *"[^"]*"' "$CONFIG_FILE" | head -1 | sed 's/"user": *"\([^"]*\)"/\1/')
        DB_PASSWORD=$(grep -o '"password": *"[^"]*"' "$CONFIG_FILE" | head -1 | sed 's/"password": *"\([^"]*\)"/\1/')

        if [[ -z "$DB_NAME" ]] || [[ -z "$DB_USER" ]] || [[ -z "$DB_PASSWORD" ]]; then
            echo "Error: Could not parse credentials from config.json"
            echo "Please check the file format or enter credentials manually."
            USE_EXISTING_CONFIG=false
        else
            echo ""
            echo "Using credentials from config.json:"
            echo "  Database: $DB_NAME"
            echo "  User:     $DB_USER"
            echo "  Password: ****"
            echo ""
        fi
    fi
fi

# ============================================
# Prompt for Database Credentials (if not using existing)
# ============================================

if [[ "$USE_EXISTING_CONFIG" == false ]]; then
    echo ""
    read -p "Database name [appdb]: " DB_NAME
    DB_NAME=${DB_NAME:-appdb}

    read -p "Database user [appuser]: " DB_USER
    DB_USER=${DB_USER:-appuser}

    read -s -p "Database password [password]: " DB_PASSWORD
    echo ""
    DB_PASSWORD=${DB_PASSWORD:-password}

    echo ""
    echo "Using:"
    echo "  Database: $DB_NAME"
    echo "  User:     $DB_USER"
    echo "  Password: ****"
    echo ""
fi

# Note: macOS PgBouncer requires md5 auth; Linux uses plain text (compatible with asyncpg SCRAM auth)

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ -f /etc/debian_version ]]; then
    OS="debian"
elif [[ -f /etc/redhat-release ]]; then
    OS="redhat"
else
    echo "Unsupported OS. Please install manually:"
    echo "  - PostgreSQL 15"
    echo "  - PgBouncer"
    echo "  - Redis"
    exit 1
fi

echo "Detected OS: $OS"
echo ""

# ============================================
# Install Packages
# ============================================

echo "[1/7] Installing system packages..."

if [[ "$OS" == "macos" ]]; then
    if ! command -v brew &> /dev/null; then
        echo "Homebrew not found. Please install it first:"
        echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi

    brew install postgresql@15 pgbouncer redis uv node gh

    # Add postgresql@15 to PATH permanently (it's keg-only)
    PG_PATH_LINE='export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"'
    SHELL_RC="$HOME/.zshrc"
    if [[ "$SHELL" == *"bash"* ]]; then
        SHELL_RC="$HOME/.bash_profile"
    fi
    if ! grep -q "postgresql@15/bin" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# PostgreSQL 15 (added by ayzer setup)" >> "$SHELL_RC"
        echo "$PG_PATH_LINE" >> "$SHELL_RC"
        echo "Added postgresql@15 to PATH in $SHELL_RC"
    fi
    # Also export for current script
    export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"

    brew services start postgresql@15
    brew services start redis

elif [[ "$OS" == "debian" ]]; then
    sudo apt-get update
    sudo apt-get install -y postgresql postgresql-contrib pgbouncer redis-server nodejs npm netcat-openbsd
    # Install GitHub CLI
    (type -p wget >/dev/null || sudo apt-get install wget -y) \
      && sudo mkdir -p -m 755 /etc/apt/keyrings \
      && wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
      && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
      && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
      && sudo apt-get update \
      && sudo apt-get install -y gh
    # Install uv
    curl -LsSf https://astral.sh/uv/install.sh | sh

elif [[ "$OS" == "redhat" ]]; then
    sudo dnf install -y postgresql15-server postgresql15-contrib pgbouncer redis nodejs npm
    sudo postgresql-setup --initdb
    # Install GitHub CLI
    sudo dnf install -y gh || (sudo dnf install -y 'dnf-command(config-manager)' && sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo && sudo dnf install -y gh)
    # Install uv
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

echo "Packages installed."
echo ""

# ============================================
# Configure PostgreSQL
# ============================================

echo "[2/7] Configuring PostgreSQL..."

if [[ "$OS" == "debian" ]] || [[ "$OS" == "redhat" ]]; then
    sudo systemctl enable postgresql
    sudo systemctl start postgresql
fi

# Create user and database (ignore errors if they already exist)
if [[ "$OS" == "macos" ]]; then
    # PATH was already set above to include postgresql@15/bin

    # Check if user exists, create if not
    if psql postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        echo "  User '$DB_USER' already exists"
    else
        psql postgres -c "CREATE USER \"$DB_USER\" WITH PASSWORD '$DB_PASSWORD' CREATEDB;" && echo "  User '$DB_USER' created"
    fi

    # Ensure CREATEDB privilege (needed for isolated worktree databases)
    psql postgres -c "ALTER USER \"$DB_USER\" CREATEDB;" 2>/dev/null || true

    # Check if database exists, create if not
    if psql postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
        echo "  Database '$DB_NAME' already exists"
    else
        psql postgres -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";" && echo "  Database '$DB_NAME' created"
    fi

    psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE \"$DB_NAME\" TO \"$DB_USER\";" 2>/dev/null || true
else
    sudo -u postgres psql -c "CREATE USER \"$DB_USER\" WITH PASSWORD '$DB_PASSWORD' CREATEDB;" 2>/dev/null || echo "  User '$DB_USER' may already exist"
    sudo -u postgres psql -c "ALTER USER \"$DB_USER\" CREATEDB;" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";" 2>/dev/null || echo "  Database '$DB_NAME' may already exist"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE \"$DB_NAME\" TO \"$DB_USER\";" 2>/dev/null || true
fi

echo "PostgreSQL configured."
echo ""

# ============================================
# Configure PgBouncer
# ============================================

echo "[3/7] Configuring PgBouncer..."

if [[ "$OS" == "macos" ]]; then
    PGBOUNCER_CONF="/opt/homebrew/etc/pgbouncer.ini"
    PGBOUNCER_USERLIST="/opt/homebrew/etc/userlist.txt"
else
    PGBOUNCER_CONF="/etc/pgbouncer/pgbouncer.ini"
    PGBOUNCER_USERLIST="/etc/pgbouncer/userlist.txt"
fi

# Backup existing config
if [[ -f "$PGBOUNCER_CONF" ]]; then
    sudo cp "$PGBOUNCER_CONF" "${PGBOUNCER_CONF}.backup.$(date +%s)"
fi

# Function to update or add a setting in pgbouncer.ini
update_pgbouncer_setting() {
    local key="$1"
    local value="$2"
    local conf="$3"

    if sudo grep -q "^${key}\s*=" "$conf" 2>/dev/null; then
        # Setting exists, update it
        if [[ "$OS" == "macos" ]]; then
            sudo sed -i '' "s|^${key}\s*=.*|${key} = ${value}|" "$conf"
        else
            sudo sed -i "s|^${key}\s*=.*|${key} = ${value}|" "$conf"
        fi
    elif sudo grep -q "^;\s*${key}\s*=" "$conf" 2>/dev/null; then
        # Setting exists but is commented out, uncomment and update it
        if [[ "$OS" == "macos" ]]; then
            sudo sed -i '' "s|^;\s*${key}\s*=.*|${key} = ${value}|" "$conf"
        else
            sudo sed -i "s|^;\s*${key}\s*=.*|${key} = ${value}|" "$conf"
        fi
    else
        # Setting doesn't exist, add it to [pgbouncer] section
        if [[ "$OS" == "macos" ]]; then
            sudo sed -i '' "/^\[pgbouncer\]/a\\
${key} = ${value}
" "$conf"
        else
            sudo sed -i "/^\[pgbouncer\]/a ${key} = ${value}" "$conf"
        fi
    fi
}

# Add database entry to [databases] section if not present
if ! sudo grep -q "^${DB_NAME}\s*=" "$PGBOUNCER_CONF" 2>/dev/null; then
    # Check if [databases] section exists
    if sudo grep -q "^\[databases\]" "$PGBOUNCER_CONF" 2>/dev/null; then
        # Add after [databases] line
        if [[ "$OS" == "macos" ]]; then
            sudo sed -i '' "/^\[databases\]/a\\
${DB_NAME} = host=localhost port=5432 dbname=${DB_NAME}
" "$PGBOUNCER_CONF"
        else
            sudo sed -i "/^\[databases\]/a ${DB_NAME} = host=localhost port=5432 dbname=${DB_NAME}" "$PGBOUNCER_CONF"
        fi
    else
        # Add [databases] section at the beginning
        echo -e "[databases]\n${DB_NAME} = host=localhost port=5432 dbname=${DB_NAME}\n" | sudo tee -a "$PGBOUNCER_CONF" > /dev/null
    fi
    echo "  Added database entry for '$DB_NAME'"
else
    echo "  Database entry for '$DB_NAME' already exists"
fi

# Update PgBouncer settings (modifies existing config, doesn't overwrite)
echo "  Updating PgBouncer settings..."
update_pgbouncer_setting "listen_addr" "127.0.0.1" "$PGBOUNCER_CONF"
update_pgbouncer_setting "listen_port" "6432" "$PGBOUNCER_CONF"
if [[ "$OS" == "macos" ]]; then
    update_pgbouncer_setting "auth_type" "md5" "$PGBOUNCER_CONF"
else
    update_pgbouncer_setting "auth_type" "plain" "$PGBOUNCER_CONF"
fi
update_pgbouncer_setting "auth_file" "$PGBOUNCER_USERLIST" "$PGBOUNCER_CONF"
update_pgbouncer_setting "pool_mode" "transaction" "$PGBOUNCER_CONF"
update_pgbouncer_setting "default_pool_size" "20" "$PGBOUNCER_CONF"
update_pgbouncer_setting "min_pool_size" "5" "$PGBOUNCER_CONF"
update_pgbouncer_setting "reserve_pool_size" "5" "$PGBOUNCER_CONF"
update_pgbouncer_setting "max_client_conn" "1000" "$PGBOUNCER_CONF"
update_pgbouncer_setting "max_db_connections" "50" "$PGBOUNCER_CONF"
# CRITICAL: Deallocate prepared statements for asyncpg compatibility with transaction pooling
update_pgbouncer_setting "server_reset_query" "DEALLOCATE ALL" "$PGBOUNCER_CONF"
# CRITICAL: Enable server_reset_query for transaction pooling mode (default only runs in session mode)
update_pgbouncer_setting "server_reset_query_always" "1" "$PGBOUNCER_CONF"

# Create/update userlist.txt
# On macOS, PgBouncer requires md5-hashed passwords: "md5" + md5(password + username)
# On Linux, plain text works fine
if [[ "$OS" == "macos" ]]; then
    PGBOUNCER_PASSWORD="md5$(printf '%s%s' "$DB_PASSWORD" "$DB_USER" | md5 -q)"
else
    PGBOUNCER_PASSWORD="$DB_PASSWORD"
fi

# Check if user already exists in userlist
if sudo grep -q "^\"${DB_USER}\"" "$PGBOUNCER_USERLIST" 2>/dev/null; then
    # Update existing user password
    if [[ "$OS" == "macos" ]]; then
        sudo sed -i '' "s|^\"${DB_USER}\".*|\"${DB_USER}\" \"${PGBOUNCER_PASSWORD}\"|" "$PGBOUNCER_USERLIST"
    else
        sudo sed -i "s|^\"${DB_USER}\".*|\"${DB_USER}\" \"${PGBOUNCER_PASSWORD}\"|" "$PGBOUNCER_USERLIST"
    fi
    echo "  Updated password for user '$DB_USER' in userlist.txt"
else
    # Add new user
    echo "\"${DB_USER}\" \"${PGBOUNCER_PASSWORD}\"" | sudo tee -a "$PGBOUNCER_USERLIST" > /dev/null
    echo "  Added user '$DB_USER' to userlist.txt"
fi

# Set permissions
if [[ "$OS" != "macos" ]]; then
    sudo chmod 640 "$PGBOUNCER_USERLIST"
    sudo chown postgres:postgres "$PGBOUNCER_USERLIST"
    sudo chown postgres:postgres "$PGBOUNCER_CONF"
fi

echo "PgBouncer configured."
echo ""

# ============================================
# Start PgBouncer
# ============================================

echo "[4/7] Starting PgBouncer..."

if [[ "$OS" == "macos" ]]; then
    # Use sudo to run as LaunchDaemon (start at boot) instead of LaunchAgent (start at login)
    brew services restart pgbouncer
elif [[ "$OS" == "debian" ]] || [[ "$OS" == "redhat" ]]; then
    sudo systemctl enable pgbouncer
    sudo systemctl restart pgbouncer
fi

echo "PgBouncer started."
echo ""

# ============================================
# Configure Redis
# ============================================

echo "[5/7] Configuring Redis..."

# Increase database count to 165 to support multi-codebase isolation:
#   DBs 0-1:   Main app (cache + ARQ)
#   DBs 2-14, 30-164: ADW worktrees, leased machine-wide (adws/adw_modules/resources.py, ADW_REDIS_DBS)
#   DBs 15+:   E2E test isolation (15 DBs per codebase index: 15-29, 30-44, ...)
# With 150 DBs we support up to 9 simultaneous codebase indexes for e2e tests.
REDIS_DATABASES=165

if [[ "$OS" == "darwin" ]]; then
    # macOS: already started via brew services, set databases via CLI
    redis-cli CONFIG SET databases "$REDIS_DATABASES" 2>/dev/null || true
    # Persist to redis.conf if writable
    REDIS_CONF="$(brew --prefix)/etc/redis.conf"
    if [[ -f "$REDIS_CONF" ]]; then
        if grep -q "^databases " "$REDIS_CONF"; then
            sed -i '' "s/^databases .*/databases $REDIS_DATABASES/" "$REDIS_CONF"
        else
            echo "databases $REDIS_DATABASES" >> "$REDIS_CONF"
        fi
    fi
elif [[ "$OS" == "debian" ]]; then
    REDIS_CONF="/etc/redis/redis.conf"
    if [[ -f "$REDIS_CONF" ]]; then
        sudo sed -i "s/^databases .*/databases $REDIS_DATABASES/" "$REDIS_CONF"
    fi
    sudo systemctl enable redis-server
    sudo systemctl restart redis-server
elif [[ "$OS" == "redhat" ]]; then
    REDIS_CONF="/etc/redis/redis.conf"
    if [[ -f "$REDIS_CONF" ]]; then
        sudo sed -i "s/^databases .*/databases $REDIS_DATABASES/" "$REDIS_CONF"
    fi
    sudo systemctl enable redis
    sudo systemctl restart redis
fi

echo "Redis configured (databases=$REDIS_DATABASES)."
echo ""

# ============================================
# Verify Installation
# ============================================

echo "==================================="
echo "Verifying installation..."
echo "==================================="
echo ""

ERRORS=0

# Retry helper: wait up to N seconds for a check command to succeed
wait_for_service() {
    local name="$1"
    local check_cmd="$2"
    local max_attempts=10
    for i in $(seq 1 $max_attempts); do
        if eval "$check_cmd" > /dev/null 2>&1; then
            echo "$name OK"
            return 0
        fi
        sleep 1
    done
    echo "$name FAILED"
    ERRORS=$((ERRORS + 1))
    return 1
}

# Check PostgreSQL
if [[ "$OS" == "macos" ]]; then
    PG_ISREADY="/opt/homebrew/opt/postgresql@15/bin/pg_isready"
else
    PG_ISREADY="pg_isready"
fi

wait_for_service "PostgreSQL (5432):" "$PG_ISREADY -h localhost -p 5432"

# Check PgBouncer (use nc to check port since pg_isready may not work with PgBouncer)
wait_for_service "PgBouncer (6432): " "nc -z localhost 6432"

# Check Redis
wait_for_service "Redis (6379):     " "redis-cli ping 2>/dev/null | grep -q PONG"

# Check GitHub CLI (minimum version 2.21.0 required for label commands and full comment fields)
GH_MIN_VERSION="2.21.0"
if command -v gh &> /dev/null; then
    GH_VERSION=$(gh --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
    if [[ -n "$GH_VERSION" ]]; then
        # Compare versions: split into major.minor.patch
        IFS='.' read -r GH_MAJ GH_MIN GH_PAT <<< "$GH_VERSION"
        IFS='.' read -r REQ_MAJ REQ_MIN REQ_PAT <<< "$GH_MIN_VERSION"
        if [[ "$GH_MAJ" -gt "$REQ_MAJ" ]] || \
           [[ "$GH_MAJ" -eq "$REQ_MAJ" && "$GH_MIN" -gt "$REQ_MIN" ]] || \
           [[ "$GH_MAJ" -eq "$REQ_MAJ" && "$GH_MIN" -eq "$REQ_MIN" && "$GH_PAT" -ge "$REQ_PAT" ]]; then
            echo "GitHub CLI:        OK (v${GH_VERSION})"
        else
            echo "GitHub CLI:        OUTDATED (v${GH_VERSION}, need >= v${GH_MIN_VERSION})"
            if [[ "$OS" == "macos" ]]; then
                echo "  Update: brew upgrade gh"
            else
                echo "  Update with: GH_LATEST=\$(curl -sI https://github.com/cli/cli/releases/latest -o /dev/null -w '%{redirect_url}' | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+') && curl -sL https://github.com/cli/cli/releases/download/v\${GH_LATEST}/gh_\${GH_LATEST}_linux_amd64.tar.gz | tar xz -C /tmp && cp /tmp/gh_\${GH_LATEST}_linux_amd64/bin/gh ~/.local/bin/gh"
            fi
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo "GitHub CLI:        UNKNOWN VERSION"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "GitHub CLI:        NOT INSTALLED"
    ERRORS=$((ERRORS + 1))
fi

echo ""

if [[ $ERRORS -eq 0 ]]; then
    echo "==========================================="
    echo "All services running!"
    echo "==========================================="
    echo ""

    # ============================================
    # Configure Application
    # ============================================

    if [[ "$USE_EXISTING_CONFIG" == true ]]; then
        echo "Using existing config.json (no changes made)"
    else
        if [[ ! -f "$CONFIG_FILE" ]] && [[ -f "$CONFIG_EXAMPLE" ]]; then
            echo "Creating config.json from example..."
            cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
        fi

        if [[ -f "$CONFIG_FILE" ]]; then
            echo "Updating config.json with database credentials..."

            # Use a temporary file for the sed operation
            if [[ "$OS" == "macos" ]]; then
                sed -i '' "s/\"user\": \"[^\"]*\"/\"user\": \"$DB_USER\"/" "$CONFIG_FILE"
                sed -i '' "s/\"password\": \"[^\"]*\"/\"password\": \"$DB_PASSWORD\"/" "$CONFIG_FILE"
                sed -i '' "s/\"db\": \"[^\"]*\"/\"db\": \"$DB_NAME\"/" "$CONFIG_FILE"
            else
                sed -i "s/\"user\": \"[^\"]*\"/\"user\": \"$DB_USER\"/" "$CONFIG_FILE"
                sed -i "s/\"password\": \"[^\"]*\"/\"password\": \"$DB_PASSWORD\"/" "$CONFIG_FILE"
                sed -i "s/\"db\": \"[^\"]*\"/\"db\": \"$DB_NAME\"/" "$CONFIG_FILE"
            fi
            echo "config.json updated."
        elif [[ -f "$CONFIG_EXAMPLE" ]]; then
            echo "Creating config.json from example..."
            cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
            if [[ "$OS" == "macos" ]]; then
                sed -i '' "s/\"user\": \"[^\"]*\"/\"user\": \"$DB_USER\"/" "$CONFIG_FILE"
                sed -i '' "s/\"password\": \"[^\"]*\"/\"password\": \"$DB_PASSWORD\"/" "$CONFIG_FILE"
                sed -i '' "s/\"db\": \"[^\"]*\"/\"db\": \"$DB_NAME\"/" "$CONFIG_FILE"
            else
                sed -i "s/\"user\": \"[^\"]*\"/\"user\": \"$DB_USER\"/" "$CONFIG_FILE"
                sed -i "s/\"password\": \"[^\"]*\"/\"password\": \"$DB_PASSWORD\"/" "$CONFIG_FILE"
                sed -i "s/\"db\": \"[^\"]*\"/\"db\": \"$DB_NAME\"/" "$CONFIG_FILE"
            fi
            echo "config.json created."
        else
            echo "Warning: config.json.example not found at $CONFIG_EXAMPLE"
            echo "You will need to create config.json manually."
        fi
    fi

    # ============================================
    # Install Application Dependencies
    # ============================================

    echo ""
    echo "[6/7] Installing application dependencies..."

    # Backend
    cd "$PROJECT_ROOT/app/backend"

    # On macOS, add postgresql to PATH for pg_config (needed by psycopg2)
    if [[ "$OS" == "macos" ]]; then
        export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"
    fi

    # Ensure uv is available (installer adds to ~/.local/bin or ~/.cargo/bin)
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    # Use Python 3.12 specifically (project requirement)
    uv venv --python 3.12
    source .venv/bin/activate
    uv pip install -r requirements.txt

    echo "  Backend dependencies installed."

    # Run migrations
    echo "  Running database migrations..."
    make migrate
    echo "  Migrations complete."

    # Frontend
    cd "$PROJECT_ROOT/app/frontend"
    npm install
    echo "  Frontend dependencies installed."

    cd "$PROJECT_ROOT"

    echo "Application dependencies installed."

    # ============================================
    # Generate Secure Config Values
    # ============================================

    echo ""
    echo "[7/7] Generating secure config values..."

    cd "$PROJECT_ROOT/app/backend"
    source .venv/bin/activate

    python -c "
import json, secrets
from cryptography.fernet import Fernet

config_path = 'config.json'
try:
    with open(config_path) as f:
        config = json.load(f)
except FileNotFoundError:
    print('  config.json not found — skipping secret generation')
    exit(0)

changed = False

if config.get('jwt', {}).get('secret') == 'your-secret-key-change-in-production':
    config['jwt']['secret'] = secrets.token_urlsafe(64)
    changed = True
    print('  Generated new JWT secret')

enc_key = config.get('encryption', {}).get('key', '')
if enc_key.startswith('generate-with:') or enc_key == '':
    config['encryption']['key'] = Fernet.generate_key().decode()
    changed = True
    print('  Generated new encryption key')

if changed:
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    print('  config.json updated with secure values')
else:
    print('  config.json already has custom values — no changes made')
"

    cd "$PROJECT_ROOT"

    echo "Secure config values configured."

    echo ""
    echo "==========================================="
    echo "Setup complete!"
    echo "==========================================="
    echo ""
    echo "Database credentials:"
    echo "  Database: $DB_NAME"
    echo "  User:     $DB_USER"
    echo "  Password: ****"
    echo ""
    echo "Services:"
    echo "  PostgreSQL: localhost:5432"
    echo "  PgBouncer:  localhost:6432"
    echo "  Redis:      localhost:6379"
    echo ""
    echo "Next steps:"
    echo "  1. Fill out .env based on .env.sample"
    echo "  2. Fill out app/backend/config.json"
    echo "  3. Fill out app/frontend/.env based on app/frontend/.env.sample"
    echo "  4. Start the application with: ./scripts/start.sh"
    echo ""
else
    echo "==========================================="
    echo "Some services failed to start."
    echo "Check logs with:"
    if [[ "$OS" == "macos" ]]; then
        echo "  brew services list"
        echo "  cat /opt/homebrew/var/log/postgresql@15.log"
        echo "  cat /opt/homebrew/var/log/pgbouncer.log"
    else
        echo "  sudo journalctl -u postgresql"
        echo "  sudo journalctl -u pgbouncer"
        echo "  sudo journalctl -u redis-server"
    fi
    echo "==========================================="
    exit 1
fi
