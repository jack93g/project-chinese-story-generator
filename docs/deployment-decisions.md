# Deployment Decisions

Milestone 5 decision record: where things run, how secrets are supplied, the
release path, expected cost, and the rollback approach. Written before any
M5 infrastructure exists so later tickets (M5-1 through M5-6) build against
settled decisions instead of re-litigating them.

## Frontend hosting

GitHub Pages, behind the already-purchased domain, with DNS records managed
at the domain registrar (no move to a third-party DNS provider). Static
export from the Next.js app, published automatically on merge to `main`
(M5-3).

## API, worker, and database hosting

A single DigitalOcean Droplet, 2GB RAM / 50GB SSD tier (~$12/mo), running
the same Docker Compose stack built in M5-1: one API container, one worker
container, one self-hosted Postgres container with a persistent volume.

- Self-managed rather than a managed platform (App Platform) or managed
  database, specifically to learn the underlying concepts — provisioning,
  networking, backup/restore — rather than delegate them.
- 2GB rather than the 1GB tier: 1GB leaves too little headroom for
  Postgres, the API process, the worker process, and Docker's own overhead
  to coexist without risking the OOM killer under load.
- No Kubernetes: one API service, one worker service, one database has no
  multi-node scheduling problem for an orchestrator to solve, and the
  learning goal here is Terraform/operations, not cluster mechanics.
- Provisioned manually first to prove the setup works, then expressed in
  Terraform (M5-4) so the same infrastructure is reproducible from code.

## Secrets

GitHub Secrets holds exactly one thing: the deployment SSH key used by
GitHub Actions to reach the Droplet. It never holds application secrets.

Application secrets live only in a `.env` file on the Droplet:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_PROVIDER_LABEL`
- `OPENAI_MODEL`
- `OPENAI_BASE_URL`
- `SKRITTER_ACCESS_TOKEN`

`.env` is created and updated manually over SSH — not automated through
CI. This is a deliberate trade-off: keeping CI from ever holding application
secrets (so a leaked Actions secret can't expose the OpenAI key or database
credentials) is worth more here than the convenience of auto-synced
secrets, given how rarely these values actually change.

Mitigation for the obvious weakness (secrets existing only on one box): the
names above are documented here and in the M5-5 runbook, and the actual
values are also kept in a password manager, so recreating the Droplet means
looking up known values rather than reconstructing an undocumented list.

CI test secrets (e.g. `TEST_DATABASE_URL` for the M5-2 database-backed test
job) are a separate, synthetic concern and are stored as ordinary GitHub
Actions secrets — they gate CI only and never touch production data.

## Release path

```
PR → tests + lint (M5-2 CI) → code review → merge to main
  → GitHub Actions builds a Docker image, tagged with the git SHA
  → image pushed to GitHub Container Registry (ghcr.io)
  → GitHub Actions runs `alembic upgrade head` against the production
    database before new code starts serving
  → GitHub Actions SSHes to the Droplet
  → `docker compose pull` + `docker compose up -d` restarts BOTH the
    API and worker services on the new image
```

GHCR rather than Docker Hub: it authenticates with the `GITHUB_TOKEN`
Actions already has, so no extra registry credential is needed. Both
application services are restarted, not just one — the API and worker run
from the same image and both must pick up a new version.

## Rollback

Rollback reuses the forward-deploy job rather than being a separate
procedure: the deploy workflow accepts a `workflow_dispatch` ref/SHA input,
defaulting to the triggering commit. Rolling back means running that same
workflow pointed at an older, already-built SHA tag:

```
docker compose pull <previous-sha-tag> && docker compose up -d
```

No rebuild is required, since every past image remains in `ghcr.io` tagged
by SHA.

Database schema is the part code rollback can't fix by itself. Migrations
are kept additive/backward-compatible by default (new columns rather than
renamed or dropped ones), so an older application version continues to
work against a newer schema after a rollback. A migration that must be
destructive gets a tested `alembic downgrade` step before it ships, not
improvised after the fact. Full backup/restore and rollback rehearsal is
M5-5's job; this section states the design M5-5 implements against.

## Expected cost

| Item | Cost |
| --- | --- |
| DigitalOcean Droplet (2GB/50GB) | ~$12/mo |
| Domain registration | Already purchased; renewal only, not counted here |
| GitHub Actions minutes | Within free tier at this project's scale |
| GitHub Container Registry | Free at this project's scale |
| GitHub Pages | Free |
| **Total recurring** | **~$12/mo**, within the $10–25/mo budget |

## Deliberately out of scope

Managed database, managed compute platform (App Platform/ECS/GKE), a
dedicated secrets manager, and Kubernetes are all explicitly not used.
Each would trade learning value and/or budget for convenience this project
doesn't need yet; revisit only if operational pain or a team forming around
the project justifies it.
