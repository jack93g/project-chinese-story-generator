#!/usr/bin/env bash
# Dumps the production database, encrypted, to ~/backups on the Droplet.
#
# Install by hand as ~deploy/db-backup.sh (outside the repo checkout, like
# deploy.sh, so a deploy or rollback to an older SHA can't change or remove
# what cron runs) and schedule it in the deploy user's crontab:
#
#   17 3 * * 0 /home/deploy/db-backup.sh >> /home/deploy/backups/backup.log 2>&1
#
# The dump is piped straight from pg_dump into age, so no plaintext copy of
# the database ever touches the disk. The Droplet holds only the age
# *public* key (the recipient): it can write backups but not read them back.
# The private key lives on your laptop and in the password manager.
#
# This is only half of "off-VM": copies here die with the Droplet. Pull them
# to your laptop regularly (docs/runbook.md, "Backups").
set -euo pipefail

app_dir="${APP_DIR:-$HOME/app}"
backup_dir="${BACKUP_DIR:-$HOME/backups}"
recipient_file="${AGE_RECIPIENT_FILE:-$HOME/.config/story-backup/recipient.txt}"
# Days of backups kept on the Droplet: with the weekly schedule, the last 4.
# The laptop copy keeps its own, longer history; this only bounds disk use
# here.
keep_days="${KEEP_DAYS:-28}"

if ! command -v age >/dev/null; then
  echo "age is not installed (sudo apt install age)" >&2
  exit 1
fi
if [[ ! -s "$recipient_file" ]]; then
  echo "no age recipient at $recipient_file" >&2
  exit 1
fi

umask 077
mkdir -p "$backup_dir"

cd "$app_dir"
# The prod override requires IMAGE_TAG; the checked-out commit is the one
# that's deployed (see docs/droplet-setup.md).
export IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse HEAD)}"
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
final="$backup_dir/db-$stamp.dump.age"
partial="$final.partial"
trap 'rm -f "$partial"' EXIT

echo "==> $(date -u +%FT%TZ) dumping to $final"
# Custom format (-Fc): compressed, and pg_restore can restore it selectively.
# --no-owner/--no-acl: the dump restores cleanly under whatever role the
# target database uses, e.g. after a password or user change.
# Credentials come from the db container's own environment, so nothing
# secret appears on this command line.
"${compose[@]}" exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' \
  | age -R "$recipient_file" > "$partial"

# pipefail above fails the script if pg_dump fails; this also catches a
# dump that "succeeded" but produced nothing useful.
if [[ "$(wc -c < "$partial")" -lt 1024 ]]; then
  echo "backup is suspiciously small; keeping the previous backups" >&2
  exit 1
fi
mv "$partial" "$final"
echo "==> wrote $(du -h "$final" | cut -f1)"

# Only prune after a good backup, so a run of failures never deletes the
# last good copies.
find "$backup_dir" -name 'db-*.dump.age' -mtime +"$keep_days" -print -delete
