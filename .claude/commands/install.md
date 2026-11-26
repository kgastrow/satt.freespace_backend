# Install & Prime

## Read
.env.sample (never read .env)
./app/backend/config.json.example (never read config.json)

## Read and Execute
.claude/commands/prime.md

## Run

Think through each of these steps to make sure you don't miss anything.

### 1. Check System Dependencies

First, check if the required services are running:

```bash
# Check PostgreSQL (use full path on macOS since postgresql@15 is keg-only)
if [[ "$OSTYPE" == "darwin"* ]]; then
    /opt/homebrew/opt/postgresql@15/bin/pg_isready -h localhost -p 5432 2>/dev/null && echo "PostgreSQL: OK" || echo "PostgreSQL: NOT RUNNING"
else
    pg_isready -h localhost -p 5432 2>/dev/null && echo "PostgreSQL: OK" || echo "PostgreSQL: NOT RUNNING"
fi

# Check PgBouncer (use nc since pg_isready doesn't work reliably with PgBouncer)
nc -z localhost 6432 2>/dev/null && echo "PgBouncer: OK" || echo "PgBouncer: NOT RUNNING"

# Check Redis
redis-cli ping 2>/dev/null | grep -q PONG && echo "Redis: OK" || echo "Redis: NOT RUNNING"
```

If any services are missing, **STOP and ask the user to run the system setup script**:

```bash
./scripts/setup-system-deps.sh
```

This script requires sudo and must be run manually by the user.

### 2. Update PgBouncer Userlist

If `app/backend/config.json` exists, extract the database credentials and ensure they are in the PgBouncer userlist so migrations and the app can connect through PgBouncer:

```bash
cd app/backend
if [[ -f config.json ]]; then
    DB_USER=$(python3 -c "import json; c=json.load(open('config.json')); print(c['database']['user'])")
    DB_PASSWORD=$(python3 -c "import json; c=json.load(open('config.json')); print(c['database']['password'])")

    if [[ "$OSTYPE" == "darwin"* ]]; then
        PGBOUNCER_USERLIST="/opt/homebrew/etc/userlist.txt"
        PGBOUNCER_PASSWORD="md5$(printf '%s%s' "$DB_PASSWORD" "$DB_USER" | md5 -q)"
    else
        PGBOUNCER_USERLIST="/etc/pgbouncer/userlist.txt"
        PGBOUNCER_PASSWORD="$DB_PASSWORD"
    fi

    # Update or add user in userlist
    if sudo grep -q "^\"${DB_USER}\"" "$PGBOUNCER_USERLIST" 2>/dev/null; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sudo sed -i '' "s|^\"${DB_USER}\".*|\"${DB_USER}\" \"${PGBOUNCER_PASSWORD}\"|" "$PGBOUNCER_USERLIST"
        else
            sudo sed -i "s|^\"${DB_USER}\".*|\"${DB_USER}\" \"${PGBOUNCER_PASSWORD}\"|" "$PGBOUNCER_USERLIST"
        fi
    else
        echo "\"${DB_USER}\" \"${PGBOUNCER_PASSWORD}\"" | sudo tee -a "$PGBOUNCER_USERLIST" > /dev/null
    fi

    # Restart PgBouncer to pick up userlist changes
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew services restart pgbouncer
    else
        sudo systemctl restart pgbouncer
    fi

    echo "PgBouncer userlist updated and service restarted"
fi
```

### 3. Install Application Dependencies

```bash
# Backend
cd app/backend

# On macOS, add postgresql to PATH for pg_config (needed by psycopg2)
if [[ "$OSTYPE" == "darwin"* ]]; then
    export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"
fi

# Use Python 3.12 specifically (project requirement)
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt

# Run migrations (only if database is available)
make migrate

# Frontend
cd ../frontend
npm install
```

### 4. Generate Secure Config Values

If `app/backend/config.json` exists, replace the default JWT secret and encryption key with securely generated values. Only replace if the current values are still the defaults (don't overwrite custom values).

```bash
cd app/backend
source .venv/bin/activate

python -c "
import json, secrets
from cryptography.fernet import Fernet

config_path = 'config.json'
try:
    with open(config_path) as f:
        config = json.load(f)
except FileNotFoundError:
    print('config.json not found — skipping secret generation')
    exit(0)

changed = False

if config.get('jwt', {}).get('secret') == 'your-secret-key-change-in-production':
    config['jwt']['secret'] = secrets.token_urlsafe(64)
    changed = True
    print('Generated new JWT secret')

enc_key = config.get('encryption', {}).get('key', '')
if enc_key.startswith('generate-with:') or enc_key == '':
    config['encryption']['key'] = Fernet.generate_key().decode()
    changed = True
    print('Generated new encryption key')

if changed:
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    print('config.json updated with secure values')
else:
    print('config.json already has custom values — no changes made')
"
```

## Report
- Output the work you've just done in a concise bullet point list.
- If system dependencies were missing, tell the user to run: `./scripts/setup-system-deps.sh` (this script prompts for db credentials and auto-configures config.json). After running the setup script, they should run `/install` again.
- Instruct the user to fill out the root level ./.env based on .env.sample.
- Instruct the user to fill out ./app/frontend/.env based on ./app/frontend/env.sample.
- Tell the user to start the application with: `./scripts/start.sh`
- Mention the url of the frontend application (http://localhost:5173) and backend API (http://localhost:8000)
- Mention: If you want to upload images to github during the review process setup cloudflare for public image access you can setup your cloudflare environment variables. See .env.sample for the variables.
- **Cross-Codebase Isolation**: Explain to the user that ADW workflows in **several codebases on the same machine** share one machine-wide resource registry (`~/.adw/resources.json`, see `adws/adw_modules/resources.py`): every workflow leases its own ports (9100-9199 / 9200-9299) and Redis database from it, and at most `ADW_MAX_WORKFLOWS` (default 4) workflows run at once across all codebases, so ports and Redis need no per-codebase setup. `uv run adws/adw_resources.py status` shows what is leased. `ADW_CODEBASE_INDEX` (unique per codebase: `0`, `1`, `2`, ...) and `ADW_MAX_CODEBASES` still name the isolated PostgreSQL databases and pick the Playwright e2e ports and Redis database, so keep them distinct when several codebases run e2e tests at once; the defaults (`0` and `1`) are fine for a single codebase. `ADW_RESOURCES=static` brings back the old static split of ports and Redis databases.