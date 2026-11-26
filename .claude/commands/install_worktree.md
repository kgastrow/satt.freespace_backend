# Install Worktree

This command sets up an isolated worktree environment with custom port, database, and Redis configuration.

## Parameters
- Worktree path: {0}
- Backend port: {1}
- Frontend port: {2}
- Database name: {3} (isolated database for this workflow)

## Read
- .env.sample (from parent repo)
- ./app/backend/.env.sample (from parent repo)

## Steps

1. **Navigate to worktree directory**
   ```bash
   cd {0}
   ```

2. **Extract ADW ID and get the Redis database**
   The ADW ID is the directory name of the worktree (e.g., `20260112111050-f320e7a7` from `trees/20260112111050-f320e7a7/`).

   Get the worktree's Redis database number from the machine-wide resource registry (shared by every codebase
   on this machine, so parallel worktrees in any codebase never share a database). From the parent repo root:
   ```bash
   uv run adws/adw_resources.py redis <adw_id>
   ```
   It prints the number (`redis_db`). Never compute it yourself: the registry hands each ADW its own database
   (with `ADW_RESOURCES=static` the command prints the old static per-codebase number). Databases 0-1 (main app)
   and 15-29 (e2e tests) are never handed out.

3. **Create port configuration file**
   Create `.ports.env` with:
   ```
   BACKEND_PORT={1}
   FRONTEND_PORT={2}
   VITE_BACKEND_URL=http://localhost:{1}
   ```

4. **Copy and update .env files**
   - Copy `.env` from parent repo if it exists
   - Append `.ports.env` contents to `.env`
   - Copy `app/backend/config.json` from parent repo if it exists
   - Update `app/backend/config.json` (CRITICAL - these prevent startup failures from security checks):
     - Set `"debug": true` (enables uvicorn auto-reload on file changes)
     - Set `"port": {1}` (use worktree's backend port)
     - Set `"database.db": "{3}"` (use isolated database for this workflow, format: `appdb_{codebase_index}_{hash}`)
     - Remove `"database.pgbouncer_port"` if present (bypass PgBouncer, connect directly to PostgreSQL)
     - Set `"redis.url": "redis://localhost:6379/<redis_db>"` (use isolated Redis database)
     - Set `"redis.arq_url": "redis://localhost:6379/<redis_db>"` (same database for ARQ)
     - **Generate and set a random JWT secret** (CRITICAL: default value causes startup failure):
       ```bash
       JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
       ```
       Set `"jwt.secret": "<generated_secret>"`
     - **Set CORS allowed origins** (CRITICAL: wildcard '*' causes startup failure):
       Use the assigned frontend port `{2}` for CORS. Set:
       `"cors.allowed_origins": "http://localhost:{2},http://127.0.0.1:{2},http://localhost:5173,http://127.0.0.1:5173"`
     - **Generate and set encryption key** (CRITICAL: missing key causes startup failure):
       ```bash
       ENCRYPTION_KEY=$(python3 -c "from base64 import urlsafe_b64encode; import os; print(urlsafe_b64encode(os.urandom(32)).decode())")
       ```
       Set `"encryption.key": "<generated_key>"`
   - Append `.ports.env` contents to `app/backend/.env`

5. **Create Playwright output directory**
   ```bash
   mkdir -p playwright-output
   ```
   This directory is used by direct Playwright runners for screenshots and videos.

6. **Install backend dependencies**
   ```bash
   cd app/backend

   # On macOS, add postgresql to PATH for pg_config (needed by psycopg2)
   if [[ "$OSTYPE" == "darwin"* ]]; then
       export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"
   fi

   # Use Python 3.12 specifically (project requirement)
   uv venv --python 3.12
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

7. **Install frontend dependencies**
   ```bash
   cd ../frontend && npm install
   ```

8. **Run database migrations**
   Apply all migrations to the isolated database:
   ```bash
   cd ../backend
   source .venv/bin/activate
   make migrate
   ```
   This creates all required tables in the isolated database.

## Error Handling
- If parent .env files don't exist, create minimal versions from .env.sample files
- Ensure all paths are absolute to avoid confusion
- If migration fails, report the error but continue - the database may already be up to date

## Report
- List all files created/modified
- Show port assignments
- Show database name being used
- Show Redis database number being used
- Confirm dependencies installed
- Confirm migrations applied
- Note any missing parent .env files that need user attention
