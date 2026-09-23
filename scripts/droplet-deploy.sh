#!/usr/bin/env bash
# Deploys one already-built image, by git SHA, on the Droplet.
#
# Install this by hand as ~deploy/deploy.sh (outside the repo checkout, so a
# deploy can never rewrite the script that runs it) and lock the CI key to it
# in ~deploy/.ssh/authorized_keys:
#
#   command="/home/deploy/deploy.sh",restrict ssh-ed25519 AAAA... ci-deploy
#
# sshd then runs this script for that key no matter what the client asks for,
# passing the client's command line in SSH_ORIGINAL_COMMAND. The only thing
# accepted from it is a 40-character git SHA.
#
# The same script is the rollback: run it (via the workflow's `sha` input)
# with an older SHA. Migrations are not reversed; they are kept additive so an
# older image still works against a newer schema.
set -euo pipefail

sha="${SSH_ORIGINAL_COMMAND:-${1:-}}"
if ! [[ "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "refusing: expected a full 40-character git SHA" >&2
  exit 1
fi

cd "$HOME/app"
export IMAGE_TAG="$sha"
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

echo "==> checking out $sha (compose files and Caddyfile must match the image)"
previous="$(git rev-parse HEAD)"
git fetch --quiet origin
# Only ever deploy what has been merged to main: a rollback target must be
# something main once contained, never a commit pushed from a side branch.
if ! git merge-base --is-ancestor "$sha" origin/main; then
  echo "refusing: $sha is not on origin/main" >&2
  exit 1
fi
git checkout --quiet --detach "$sha"

echo "==> pulling images"
"${compose[@]}" pull --quiet migrate api worker

# Migrate first, while the old API/worker keep serving: new code never starts
# against an old schema, and additive migrations keep the old code working.
echo "==> running migrations"
"${compose[@]}" run --rm migrate

# Recreate both the API and the worker, never just one, on the new image.
# Named explicitly so db and caddy are left alone: changes to them (e.g. the
# Caddyfile) are deliberate manual steps, not something a code deploy bounces.
echo "==> restarting api and worker"
"${compose[@]}" up -d --remove-orphans api worker

echo "==> waiting for /health"
for _ in $(seq 1 30); do
  if "${compose[@]}" exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" \
    >/dev/null 2>&1; then
    # The API answering says nothing about the worker, which has no port to
    # probe: after a short settle, make sure it is running and not restarting.
    sleep 5
    if "${compose[@]}" ps --status running --services | grep -qx worker; then
      echo "==> deployed $sha"
      exit 0
    fi
    echo "worker is not running after deploying $sha" >&2
    echo "previous release was $previous (redeploy it via the workflow's sha input)" >&2
    "${compose[@]}" logs --tail=40 worker >&2
    exit 1
  fi
  sleep 2
done

echo "health check failed after deploying $sha" >&2
echo "previous release was $previous (redeploy it via the workflow's sha input)" >&2
"${compose[@]}" logs --tail=40 api worker >&2
exit 1
