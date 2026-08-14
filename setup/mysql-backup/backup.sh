#!/bin/sh
set -u

MYSQL_HOST="${MYSQL_HOST:-mysql}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
BACKUP_DATABASES="${BACKUP_DATABASES:-aware_android aware_ios}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
# The dashboard's own tables, kept out of every archive. Each one summarises the
# `_id` values of the deployment that built it, so restoring one describes rows
# the target may not have; the API rebuilds them all from the restored data.
# Mirrors CACHE_TABLES in analytics_api/app/services/dump_stream.py.
BACKUP_SKIP_TABLES="${BACKUP_SKIP_TABLES:-record_counts coverage_hourly device_enrolment}"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

case "$BACKUP_INTERVAL_SECONDS" in
  ""|*[!0-9]*) BACKUP_INTERVAL_SECONDS=86400 ;;
esac

case "$BACKUP_RETENTION_DAYS" in
  ""|*[!0-9]*) BACKUP_RETENTION_DAYS=30 ;;
esac

log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

run_backup() {
  if [ -z "$MYSQL_PASSWORD" ]; then
    log "MYSQL_PASSWORD is empty; skipping backup"
    return 1
  fi

  mkdir -p "$BACKUP_DIR"

  stamp="$(date -u '+%Y-%m-%d-%H%M%S')"
  output_path="$BACKUP_DIR/aware-db-$stamp.sql.gz"
  sql_tmp="$BACKUP_DIR/aware-db-$stamp.sql.tmp"
  gzip_tmp="$output_path.tmp"

  log "Starting MySQL backup for: $BACKUP_DATABASES"

  ignore_flags=""
  for database in $BACKUP_DATABASES; do
    for table in $BACKUP_SKIP_TABLES; do
      ignore_flags="$ignore_flags --ignore-table=$database.$table"
    done
  done

  # Intentional word splitting: BACKUP_DATABASES is a space-separated database
  # list, and ignore_flags one option per skipped table.
  if ! MYSQL_PWD="$MYSQL_PASSWORD" mysqldump \
    --host="$MYSQL_HOST" \
    --port="$MYSQL_PORT" \
    --user="$MYSQL_USER" \
    --single-transaction \
    --routines \
    --triggers \
    $ignore_flags \
    --databases $BACKUP_DATABASES \
    --result-file="$sql_tmp"; then
    rm -f "$sql_tmp" "$gzip_tmp"
    log "MySQL backup failed during dump"
    return 1
  fi

  if ! gzip -c "$sql_tmp" > "$gzip_tmp"; then
    rm -f "$sql_tmp" "$gzip_tmp"
    log "MySQL backup failed during compression"
    return 1
  fi

  mv "$gzip_tmp" "$output_path"
  rm -f "$sql_tmp"

  find "$BACKUP_DIR" -type f -name 'aware-db-*.sql.gz' -mtime +"$BACKUP_RETENTION_DAYS" -delete
  log "MySQL backup saved: $output_path"
}

log "Daily MySQL backup service started"

while true; do
  run_backup || true
  log "Next MySQL backup in $BACKUP_INTERVAL_SECONDS seconds"
  sleep "$BACKUP_INTERVAL_SECONDS"
done
