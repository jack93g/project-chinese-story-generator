#!/usr/bin/env bash
# Read-only access to the encrypted backups, for the laptop's weekly pull
# (scripts/pull-backups.sh).
#
# Install this by hand as ~deploy/backup-serve.sh (outside the repo checkout,
# like deploy.sh, so a deploy can never change what this key can do) and lock
# the laptop's backup key to it in ~deploy/.ssh/authorized_keys:
#
#   command="/home/deploy/backup-serve.sh",restrict ssh-ed25519 AAAA... backup-pull
#
# sshd then runs this script for that key whatever the client asks for,
# passing the client's command line in SSH_ORIGINAL_COMMAND. Only two are
# accepted:
#
#   list                      names of the finished backups, one per line
#   get db-<stamp>.dump.age   that backup's bytes on stdout
#
# The files are age-encrypted and this key can't write or delete anything, so
# a stolen copy of it exposes nothing readable.
set -euo pipefail

backup_dir="$HOME/backups"
name_pattern='^db-[0-9]{8}T[0-9]{6}Z\.dump\.age$'
request="${SSH_ORIGINAL_COMMAND:-}"

case "$request" in
  list)
    cd "$backup_dir"
    # Finished backups only: db-backup.sh writes to *.partial and renames.
    # With no backups the glob stays literal, fails the pattern, and prints
    # nothing.
    for file in db-*.dump.age; do
      if [[ "$file" =~ $name_pattern ]]; then
        printf '%s\n' "$file"
      fi
    done
    ;;
  "get "*)
    file="${request#get }"
    if ! [[ "$file" =~ $name_pattern ]]; then
      echo "refusing: not a backup file name" >&2
      exit 1
    fi
    exec cat "$backup_dir/$file"
    ;;
  *)
    echo "refusing: expected 'list' or 'get db-<stamp>.dump.age'" >&2
    exit 1
    ;;
esac
