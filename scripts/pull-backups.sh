#!/usr/bin/env bash
# Pulls the Droplet's encrypted backups to this laptop (the off-VM copy),
# checks the newest one is recent and decrypts to a complete dump, then pings
# a dead man's switch (healthchecks.io) so a missed week raises an alert.
#
# Runs weekly from launchd (scripts/install-backup-pull.sh), or by hand.
# macOS only (BSD date). Written for the bash 3.2 that ships with macOS.
#
# It connects as the `story-backups` host from ~/.ssh/config, whose key is
# locked on the Droplet to backup-serve.sh (list and read backups only); see
# docs/runbook.md, "Backups".
set -euo pipefail

# launchd starts jobs with a minimal PATH: add Homebrew's age and pg_restore.
export PATH="/opt/homebrew/opt/postgresql@17/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

ssh_host="${BACKUP_SSH_HOST:-story-backups}"
dest="${BACKUP_DEST:-$HOME/Backups/huaben}"
config_dir="$HOME/.config/story-backup"
age_key="${AGE_KEY_FILE:-$config_dir/age-key.txt}"
ping_url_file="${PING_URL_FILE:-$config_dir/ping-url}"
# Days kept here; longer than the Droplet's 28.
keep_days="${KEEP_DAYS:-90}"
# The backup runs weekly, so anything older than this means it stopped.
max_age_days="${MAX_AGE_DAYS:-8}"

name_pattern='^db-[0-9]{8}T[0-9]{6}Z\.dump\.age$'

ping_url=""
if [[ -s "$ping_url_file" ]]; then
  ping_url="$(tr -d '[:space:]' < "$ping_url_file")"
fi

# Healthchecks.io: the bare URL reports success, /fail reports failure. A
# failed ping never fails the run itself.
ping_check() {
  if [[ -n "$ping_url" ]]; then
    curl -fsS -m 10 --retry 3 -o /dev/null "$ping_url$1" || true
  fi
}
report_failure() {
  local status=$?
  if (( status != 0 )); then
    echo "FAILED (exit $status)" >&2
    ping_check /fail
  fi
}
trap report_failure EXIT

remote() {
  # -n: never read stdin, so a remote call can't swallow a caller's input.
  ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$ssh_host" "$@"
}

echo "==> $(date -u +%FT%TZ) pulling from $ssh_host to $dest"
mkdir -p "$dest"
chmod 700 "$dest"

names="$(remote list)"
for name in $names; do
  [[ "$name" =~ $name_pattern ]] || continue
  [[ -e "$dest/$name" ]] && continue
  remote "get $name" > "$dest/$name.partial"
  chmod 600 "$dest/$name.partial"
  mv "$dest/$name.partial" "$dest/$name"
  echo "pulled $name"
done

find "$dest" -name 'db-*.dump.age' -mtime +"$keep_days" -print -delete

# Stamps sort chronologically, so the last name is the newest backup.
newest="$(find "$dest" -name 'db-*.dump.age' | sort | tail -n 1)"
if [[ -z "$newest" ]]; then
  echo "no backups in $dest" >&2
  exit 1
fi

stamp="$(basename "$newest" .dump.age)"
stamp="${stamp#db-}"
age_days=$(( ($(date -u +%s) - $(date -j -u -f '%Y%m%dT%H%M%SZ' "$stamp" +%s)) / 86400 ))
if (( age_days > max_age_days )); then
  echo "newest backup is $age_days days old ($newest): is the Droplet's backup cron running?" >&2
  exit 1
fi

# Decrypt and read the whole dump, turning it into SQL that's thrown away:
# proves it decrypts and every part of it is readable, without restoring it
# or writing plaintext anywhere. (Not --list: that stops reading early, and
# the broken pipe would fail age under pipefail.)
age -d -i "$age_key" "$newest" | pg_restore -f /dev/null
echo "==> ok: $newest ($age_days days old) decrypts to a complete dump"
ping_check ""
