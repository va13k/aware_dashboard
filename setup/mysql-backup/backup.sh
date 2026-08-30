#!/bin/sh
set -u

MYSQL_HOST="${MYSQL_HOST:-mysql}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
# What the connection asks of the server. Empty for the database this deployment
# runs, which is reached over the compose network and nowhere else; REQUIRED when
# the study kept this job while moving to a server it named, where the dump crosses
# a network anybody can sit on.
MYSQL_SSL_MODE="${MYSQL_SSL_MODE:-}"
BACKUP_DATABASES="${BACKUP_DATABASES:-aware_android aware_ios}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
# The dashboard's own tables, kept out of every archive. Each one summarises the
# `_id` values of the deployment that built it, so restoring one describes rows
# the target may not have; the API rebuilds them all from the restored data.
# Mirrors CACHE_TABLES in analytics_api/app/services/dump_stream.py.
BACKUP_SKIP_TABLES="${BACKUP_SKIP_TABLES:-record_counts coverage_hourly device_enrolment}"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
# How long to wait after an attempt that failed, rather than the full interval.
# What a dump needs is not all brought up by compose: the account it connects as is
# created by the deploy, so a service started first finds no account and fails. Made
# to wait a day for the next try, that ordering costs a study its daily archive.
BACKUP_RETRY_SECONDS="${BACKUP_RETRY_SECONDS:-300}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

case "$BACKUP_INTERVAL_SECONDS" in
  ""|*[!0-9]*) BACKUP_INTERVAL_SECONDS=86400 ;;
esac

case "$BACKUP_RETRY_SECONDS" in
  ""|*[!0-9]*) BACKUP_RETRY_SECONDS=300 ;;
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

  ssl_flags=""
  if [ -n "$MYSQL_SSL_MODE" ]; then
    ssl_flags="--ssl-mode=$MYSQL_SSL_MODE"
  fi

  # Intentional word splitting: BACKUP_DATABASES is a space-separated database
  # list, ignore_flags one option per skipped table, and ssl_flags empty where the
  # connection does not leave the deployment.
  #
  # --no-tablespaces and --set-gtid-purged=OFF are what let an account that may only
  # read take a dump: the first asks the server for tablespace metadata no study
  # needs and PROCESS to see, the second reads the replication position, which a
  # managed server has and hands out to nobody. Neither changes what is archived.
  if ! MYSQL_PWD="$MYSQL_PASSWORD" mysqldump \
    --host="$MYSQL_HOST" \
    --port="$MYSQL_PORT" \
    --user="$MYSQL_USER" \
    $ssl_flags \
    --single-transaction \
    --no-tablespaces \
    --set-gtid-purged=OFF \
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
  if run_backup; then
    wait_seconds="$BACKUP_INTERVAL_SECONDS"
  else
    wait_seconds="$BACKUP_RETRY_SECONDS"
  fi
  log "Next MySQL backup in $wait_seconds seconds"
  sleep "$wait_seconds"
done
