# Freespace restore (companion to `freespace_backup.sh`, BF-83)

Backups are `pg_dump --format=custom` files named
`freespace_<database>_<UTC timestamp>.dump`, kept 14 days in
`FREESPACE_BACKUP_DIR` and copied off the host. Retention on the off-host
destination is the destination's own policy (the script only trims the local
directory); set it to at least 14 days.

Dumps hold personal information (hashed device ids, FCM tokens). Treat every copy
like the database itself: mode 0600, encrypted destination, no e-mail.

## Restore into a new database (always do this first)

Connect directly to PostgreSQL (port 5432), never through PgBouncer.

```bash
export PGHOST=... PGPORT=5432 PGUSER=... PGPASSFILE=/etc/freespace/pgpass
createdb freespace_restore
pg_restore --list freespace_freespace_20261126T021500Z.dump | head   # sanity check
pg_restore --no-owner --exit-on-error --dbname=freespace_restore \
    freespace_freespace_20261126T021500Z.dump
psql freespace_restore -c "select count(*) from site;"
```

Fetch the dump first if only the off-host copy survives:
`rsync -t user@backup-host:/srv/freespace/freespace_freespace_<stamp>.dump .`
or `rclone copy remote:path/<file> .`.

## Replace the live database (disaster recovery)

1. Stop writers: `systemctl stop freespace-api freespace-worker`.
2. Keep the broken database for inspection:
   `psql -d postgres -c "ALTER DATABASE freespace RENAME TO freespace_broken;"`.
3. `createdb freespace` and `pg_restore --no-owner --dbname=freespace <dump>`
   (add `--role=<owner>` or run as the application owner so ownership is right).
4. Check the alembic revision matches the deployed code:
   `psql freespace -c "select * from alembic_version;"`. If the code is newer,
   run `make migrate`.
5. Flush the Freespace Redis caches so no stale availability or settings are
   served: `redis-cli --scan --pattern 'freespace:*' | xargs -r redis-cli del`.
6. `systemctl start freespace-api freespace-worker` and check `GET /health`.

## What a restore does not bring back

- Engine state is in the database and is restored with it (BN-4). Advisories
  sent after the dump's time may be sent again if the site is still above its
  trigger; the per-device cooldown and daily cap are rebuilt from `push_send`.
- Devices that registered or erased themselves after the dump are out of sync.
  Erasure requests honoured after the dump date must be re-applied: run the
  daily purge, and ask affected users to use "erase my data" again if needed.
- Redis content (rate limits, caches) is rebuilt on its own.

## Test the restore

Restore the newest dump into a scratch database at least once a quarter and
run `select max(received_at) from site_snapshot;` to confirm the dump is current.
