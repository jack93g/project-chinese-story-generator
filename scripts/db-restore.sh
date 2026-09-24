#!/usr/bin/env bash
# Restores a pg_dump (custom format, already decrypted) read from stdin.
#
# Decrypt on your laptop and stream it over SSH, so the backup's private key
# never goes to the Droplet (docs/runbook.md, "Restore"):
#
#   age -d -i ~/.config/story-backup/age-key.txt db-<stamp>.dump.age \
#     | ssh deploy@api.huaben.app 'bash ~/app/scripts/db-restore.sh restore_check'
#
# Two modes:
#
#   db-restore.sh <scratch_db>     Rehearsal. Restores into a separate
#                                  database next to the live one, prints row
#                                  counts, and touches nothing that's running.
#                                  Drop it afterwards with --drop <scratch_db>.
#
#   db-restore.sh --replace-live   Real restore. Restores into a staging
#                                  database first; only if that succeeds are
#                                  the api and worker stopped and the live
#                                  database swapped for it by rename. The old
#                                  database is kept (renamed, not dropped), so
#                                  the swap itself can be undone.
#
#   db-restore.sh --drop <db>      Drops a scratch or kept-aside database.
set -euo pipefail

app_dir="${APP_DIR:-$HOME/app}"
cd "$app_dir"
export IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse HEAD)}"
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

# Runs a shell snippet inside the db container, where POSTGRES_USER and
# POSTGRES_DB are already set; extra arguments arrive as $1, $2, ...
# `compose exec` forwards stdin, so everything except pg_restore gets
# /dev/null: otherwise an earlier command could swallow the dump.
in_db_stdin() {
  local snippet="$1"
  shift
  "${compose[@]}" exec -T db sh -c "$snippet" sh "$@"
}

in_db() {
  in_db_stdin "$@" </dev/null
}

# SQL on the maintenance database, so the target itself can be dropped or
# renamed while we're connected.
admin_sql() {
  in_db 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d postgres -c "$1"' "$1"
}

live_db="$(in_db 'printf %s "$POSTGRES_DB"')"

check_name() {
  if ! [[ "$1" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    echo "refusing: database name must be lowercase letters, digits, underscores" >&2
    exit 1
  fi
  if [[ "$1" == "$live_db" || "$1" == postgres || "$1" == template* ]]; then
    echo "refusing: $1 is not a scratch database (use --replace-live for the live one)" >&2
    exit 1
  fi
}

restore_into() {
  local target="$1"
  echo "==> restoring into $target"
  admin_sql "DROP DATABASE IF EXISTS $target"
  admin_sql "CREATE DATABASE $target"
  # --exit-on-error: a partial restore must fail loudly, not look finished.
  # --no-owner/--no-acl: objects belong to the role doing the restore.
  in_db_stdin 'pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --no-acl --exit-on-error' "$target"
}

summarise() {
  echo "==> contents of $1"
  in_db 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "
    SELECT (SELECT version_num FROM alembic_version) AS alembic_version,
           (SELECT count(*) FROM vocabulary_items) AS vocabulary_items,
           (SELECT count(*) FROM vocabulary_lists) AS vocabulary_lists,
           (SELECT count(*) FROM stories) AS stories,
           (SELECT count(*) FROM story_generation_requests) AS generation_requests,
           (SELECT max(created_at) FROM stories) AS newest_story"' "$1"
}

case "${1:-}" in
  --drop)
    check_name "${2:-}"
    admin_sql "DROP DATABASE IF EXISTS $2"
    echo "==> dropped $2"
    ;;

  --replace-live)
    staging="${live_db}_restoring"
    kept="${live_db}_before_restore_$(date -u +%Y%m%d%H%M%S)"
    check_name "$staging"

    # Everything that can fail slowly happens here, while the live site is
    # still up on the untouched database.
    restore_into "$staging"
    summarise "$staging"

    echo "==> stopping api and worker"
    "${compose[@]}" stop api worker </dev/null

    # Renames need no connections on either database; the api and worker
    # were the only clients.
    echo "==> swapping: $live_db -> $kept, $staging -> $live_db"
    admin_sql "ALTER DATABASE $live_db RENAME TO $kept"
    admin_sql "ALTER DATABASE $staging RENAME TO $live_db"

    # The backup may predate the running code's schema. Migrations are
    # additive, so bringing it forward is safe; if this fails, the api and
    # worker stay stopped rather than starting against the wrong schema.
    echo "==> running migrations"
    "${compose[@]}" run --rm migrate </dev/null

    echo "==> starting api and worker"
    "${compose[@]}" up -d --no-deps api worker </dev/null

    echo "==> waiting for /health"
    healthy=""
    for _ in $(seq 1 30); do
      if "${compose[@]}" exec -T api python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" \
        </dev/null >/dev/null 2>&1; then
        healthy=1
        break
      fi
      sleep 2
    done
    if [[ -z "$healthy" ]]; then
      echo "api is not healthy on the restored database" >&2
      echo "to undo the swap: stop api worker, rename $live_db back to ${staging}," >&2
      echo "rename $kept back to $live_db, start api worker (docs/runbook.md)" >&2
      exit 1
    fi

    echo "==> restored. The previous database is kept as $kept;"
    echo "    once you've checked the site, drop it with: $0 --drop $kept"
    ;;

  ""|-*)
    echo "usage: $0 <scratch_db> | --replace-live | --drop <db>   (dump on stdin)" >&2
    exit 1
    ;;

  *)
    check_name "$1"
    restore_into "$1"
    summarise "$1"
    echo "==> rehearsal done; drop it with: $0 --drop $1"
    ;;
esac
