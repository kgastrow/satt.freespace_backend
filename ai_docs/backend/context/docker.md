# Docker Context

## Files

| File | Purpose |
|------|---------|
| `app/backend/docker-compose.yml` | Development - hardcoded credentials, exposed ports |
| `app/backend/docker-compose.prod.yml` | Production - env vars, resource limits, nginx |

## Services

| Service | Port (ext/int) | Purpose |
|---------|----------------|---------|
| postgres | 5432 (dev only) | PostgreSQL 15 database |
| pgbouncer | 6432/5432 | Connection pooler (required for production) |
| redis | 6379 (dev only) | Cache (db 0) and job queue (db 1) |
| api | 8000 | FastAPI server |
| worker | - | ARQ background jobs |
| nginx | 80, 443 | Reverse proxy (prod only) |

## Commands

```bash
# Development
make up / make down / make logs   # Manage dev services
make build                        # Build images

# Production
docker-compose -f docker-compose.prod.yml up -d
make build-prod

# Cleanup
make clean-docker                 # Remove volumes and images
```

## Environment Variables (Production)

Production uses environment variables with shell parameter expansion:

```bash
# Required (fails startup if missing)
DB_PASSWORD=secret                # ${DB_PASSWORD:?Database password required}

# Optional with defaults
DB_USER=appuser                   # ${DB_USER:-appuser}
DB_NAME=appdb                     # ${DB_NAME:-appdb}
```

The `:?` syntax makes `DB_PASSWORD` mandatory - container won't start without it.

## Configuration Differences

### PgBouncer Pool Sizes

| Setting | Dev | Prod | Notes |
|---------|-----|------|-------|
| MAX_CLIENT_CONN | 100 | 200 | Max client connections |
| DEFAULT_POOL_SIZE | 20 | 40 | Connections per database |
| MIN_POOL_SIZE | 5 | 10 | Minimum idle connections |
| RESERVE_POOL_SIZE | 5 | 10 | Burst capacity |

### Redis Configuration

**Development**: Basic AOF persistence only
```
redis-server --appendonly yes
```

**Production**: Memory limits with LRU eviction
```
redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
```

### Uvicorn Workers

**Development**: Single worker (default via Dockerfile)

**Production**: Multi-worker with performance optimizations
```yaml
command: >
  uvicorn main:app
  --host 0.0.0.0
  --port 8000
  --workers 4
  --loop uvloop
  --http httptools
```

Rule of thumb: `workers = 2 * CPU cores + 1`

## Docker Config File

Use service names (not localhost) in `config.docker.json`:

```json
{
  "database": { "host": "pgbouncer", "port": 5432 },
  "redis": { "url": "redis://redis:6379/0", "arq_url": "redis://redis:6379/1" }
}
```

## Migrations in Docker

Always run migrations directly against PostgreSQL, not PgBouncer:

```bash
# From host (dev - postgres port exposed)
DATABASE_URL=postgresql://appuser:password@localhost:5432/appdb alembic upgrade head

# Inside container (prod)
docker-compose -f docker-compose.prod.yml exec api \
  alembic -c /app/alembic.ini upgrade head
# Or connect directly to postgres service
docker-compose exec postgres psql -U appuser -d appdb
```

**Important**: PgBouncer's transaction pooling mode doesn't support DDL operations well.

## Security

- Non-root user (`appuser`) in all containers
- Config mounted read-only (`:ro`)
- Secrets via environment variables, never in config files
- Production: PostgreSQL/Redis ports not exposed externally
- Production: Resource limits on api/worker containers

## Gotchas

| Issue | Solution |
|-------|----------|
| DB connection fails | Check PgBouncer: `docker-compose logs pgbouncer` |
| Worker not processing | Verify Redis: `docker-compose exec redis redis-cli ping` |
| Code changes not reflected | Rebuild: `docker-compose up -d --build api` |
| Need clean slate | Reset volumes: `docker-compose down -v` |
| Prod won't start | Check `DB_PASSWORD` is set in environment |
| Migrations fail via PgBouncer | Run directly against postgres (port 5432) |

## Adding Services

1. Add to both `docker-compose.yml` and `docker-compose.prod.yml`
2. Include health check
3. Set appropriate `depends_on` conditions
4. Add resource limits in prod file
5. Update `config.docker.json.example` if config needed
