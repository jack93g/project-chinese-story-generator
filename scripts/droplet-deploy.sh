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
git fetch --quiet origin
git checkout --quiet --detach "$sha"

echo "==> pulling images"
"${compose[@]}" pull --quiet migrate api worker

# Migrate first, while the old API/worker keep serving: new code never starts
# against an old schema, and additive migrations keep the old code working.
echo "==> running migrations"
"${compose[@]}" run --rm migrate

# Recreate both the API and the worker, never just one, on the new image.
echo "==> restarting api and worker"
"${compose[@]}" up -d --remove-orphans

echo "==> waiting for /health"
for _ in $(seq 1 30); do
  if "${compose[@]}" exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" \
    >/dev/null 2>&1; then
    echo "==> deployed $sha"
    exit 0
  fi
  sleep 2
done

echo "health check failed after deploying $sha" >&2
"${compose[@]}" logs --tail=40 api worker >&2
exit 1
