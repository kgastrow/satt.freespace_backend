#!/usr/bin/env bash
# Freespace nightly PostgreSQL backup (BF-83).
#
#   1. pg_dump (custom format, compressed) straight to PostgreSQL, NOT PgBouncer
#   2. keep FREESPACE_BACKUP_RETENTION_DAYS (default 14) days locally
#   3. copy the dump off the host (rsync/scp target and/or rclone remote)
#
# Any failure writes one "ERROR:" line to stderr (journal) and exits non-zero.
# No credentials live here or on the command line: use PGPASSFILE (.pgpass)
# and an SSH key / rclone config referenced from the environment file.
#
# Environment (normally /etc/freespace/backup.env, mode 0600):
#   FREESPACE_BACKUP_DIR              required  local directory for dumps
#   FREESPACE_BACKUP_RETENTION_DAYS   optional  default 14
#   FREESPACE_BACKUP_OFFSITE          off-host rsync target "user@host:/path/"
#   FREESPACE_BACKUP_OFFSITE_METHOD   optional  rsync (default) | scp
#   FREESPACE_BACKUP_RCLONE_REMOTE    off-host rclone destination "remote:path"
#   FREESPACE_BACKUP_SSH_KEY          optional  private key file for rsync/scp
#   FREESPACE_BACKUP_SSH_KNOWN_HOSTS  optional  known_hosts file (host key pinned)
#   FREESPACE_BACKUP_ALLOW_LOCAL_ONLY optional  "true" to run with no off-host copy
#   PGHOST PGPORT PGUSER PGDATABASE   required  direct PostgreSQL connection
#   PGPASSFILE (or PGPASSWORD)        required  credentials
# At least one of OFFSITE / RCLONE_REMOTE is required unless ALLOW_LOCAL_ONLY=true.
# Both set means both are used; a failure of either fails the run.
# Under deploy/freespace-backup.service (ProtectHome=true, ProtectSystem=strict)
# the SSH key, known_hosts, .pgpass and rclone config must live under
# /etc/freespace/, not in a home directory.
set -Eeuo pipefail
umask 077

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() {
  printf '%s ERROR: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
  exit 1
}
trap 'fail "backup aborted at line ${LINENO} (exit $?)"' ERR

require_var() {
  local name=$1
  [[ -n "${!name:-}" ]] || fail "required environment variable ${name} is not set"
}

for name in FREESPACE_BACKUP_DIR PGHOST PGUSER PGDATABASE; do
  require_var "$name"
done
if [[ -n "${PGPASSFILE:-}" ]]; then
  [[ -r "$PGPASSFILE" ]] || fail "PGPASSFILE is not readable"
elif [[ -z "${PGPASSWORD:-}" && ! -r "${HOME:-/nonexistent}/.pgpass" ]]; then
  fail "no database credentials: set PGPASSFILE (preferred) or provide ~/.pgpass"
fi

retention_days=${FREESPACE_BACKUP_RETENTION_DAYS:-14}
[[ "$retention_days" =~ ^[0-9]+$ && "$retention_days" -ge 1 ]] \
  || fail "FREESPACE_BACKUP_RETENTION_DAYS must be a positive integer"
method=${FREESPACE_BACKUP_OFFSITE_METHOD:-rsync}
[[ "$method" == rsync || "$method" == scp ]] \
  || fail "FREESPACE_BACKUP_OFFSITE_METHOD must be rsync or scp"
offsite=${FREESPACE_BACKUP_OFFSITE:-}
rclone_remote=${FREESPACE_BACKUP_RCLONE_REMOTE:-}
if [[ -z "$offsite" && -z "$rclone_remote" && "${FREESPACE_BACKUP_ALLOW_LOCAL_ONLY:-}" != "true" ]]; then
  fail "no off-host destination: set FREESPACE_BACKUP_OFFSITE and/or FREESPACE_BACKUP_RCLONE_REMOTE (or FREESPACE_BACKUP_ALLOW_LOCAL_ONLY=true)"
fi

export PGPORT=${PGPORT:-5432}
# PgBouncer's default port is 6432; a dump through it is not consistent.
[[ "$PGPORT" != 6432 ]] || fail "PGPORT 6432 looks like PgBouncer; connect to PostgreSQL directly (5432)"

for tool in pg_dump find; do
  command -v "$tool" >/dev/null 2>&1 || fail "required tool not found: ${tool}"
done
if [[ -n "$offsite" ]]; then
  command -v "$method" >/dev/null 2>&1 || fail "required tool not found: ${method}"
  if [[ "$method" == scp ]]; then
    command -v ssh >/dev/null 2>&1 || fail "required tool not found: ssh"
  fi
fi
if [[ -n "$rclone_remote" ]]; then
  command -v rclone >/dev/null 2>&1 || fail "required tool not found: rclone"
fi

mkdir -p "$FREESPACE_BACKUP_DIR" || fail "cannot create ${FREESPACE_BACKUP_DIR}"
[[ -w "$FREESPACE_BACKUP_DIR" ]] || fail "${FREESPACE_BACKUP_DIR} is not writable"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
final="${FREESPACE_BACKUP_DIR}/freespace_${PGDATABASE}_${stamp}.dump"
partial="${final}.partial"
trap 'rm -f "$partial"; fail "backup aborted at line ${LINENO} (exit $?)"' ERR

log "dumping database to ${final}"
pg_dump --format=custom --compress=6 --no-password --file="$partial" \
  || fail "pg_dump failed"
[[ -s "$partial" ]] || fail "pg_dump produced an empty file"
if command -v pg_restore >/dev/null 2>&1; then
  pg_restore --list "$partial" >/dev/null || fail "dump failed verification (pg_restore --list)"
fi
mv "$partial" "$final"
trap 'fail "backup aborted at line ${LINENO} (exit $?)"' ERR
log "dump complete ($(wc -c <"$final") bytes)"

ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=yes)
[[ -z "${FREESPACE_BACKUP_SSH_KEY:-}" ]] || ssh_opts+=(-i "$FREESPACE_BACKUP_SSH_KEY" -o IdentitiesOnly=yes)
[[ -z "${FREESPACE_BACKUP_SSH_KNOWN_HOSTS:-}" ]] || ssh_opts+=(-o "UserKnownHostsFile=${FREESPACE_BACKUP_SSH_KNOWN_HOSTS}")

if [[ -n "$offsite" ]]; then
  log "copying off host (${method})"
  if [[ "$method" == rsync ]]; then
    rsync -t -e "ssh ${ssh_opts[*]}" "$final" "$offsite" || fail "rsync to off-host target failed"
  else
    scp -q "${ssh_opts[@]}" "$final" "$offsite" || fail "scp to off-host target failed"
  fi
fi
if [[ -n "$rclone_remote" ]]; then
  log "copying off host (rclone)"
  rclone copy "$final" "$rclone_remote" || fail "rclone copy failed"
fi

# Local retention runs only after the copy succeeded, so a failing off-host
# destination never costs us the local history.
log "removing local dumps older than ${retention_days} days"
find "$FREESPACE_BACKUP_DIR" -maxdepth 1 -type f \
  \( -name 'freespace_*.dump' -o -name 'freespace_*.dump.partial' \) \
  -mtime "+$((retention_days - 1))" -delete || fail "local retention cleanup failed"

log "backup finished: $(basename "$final")"
