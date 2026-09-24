# Droplet Setup

How the production backend is hosted: what runs where, how to get access, how
to rebuild it from nothing, and why it's configured the way it is. Day-to-day
procedures (deploys, rollbacks, backups, secret rotation) are in
[runbook.md](runbook.md). No secrets or IP addresses are recorded here.

## What's running

```
 Browser (https://huaben.app, static frontend on GitHub Pages)
    │  HTTPS, session cookie (browser) or X-API-Key header (scripts)
    ▼
 Cloudflare DNS: api.huaben.app ──► Droplet public IP (DNS only, not proxied)
    │
    ▼
 DigitalOcean cloud firewall: inbound 22, 80, 443 only
    │
 ┌──┴──────────────────────── Droplet: Ubuntu 24.04, 2GB RAM ────────────┐
 │  Docker Compose, from ~/app (a checkout of this repo)                 │
 │                                                                       │
 │  caddy :80/:443 ──► api :8000 ──► db (PostgreSQL 17, data volume)     │
 │                                    ▲                                  │
 │                         worker ────┘──► AI provider (OpenAI API)      │
 └───────────────────────────────────────────────────────────────────────┘
    ▲
    │  SSH (deploy key, can only run the deploy script)
 GitHub Actions: build image ──► GHCR (ghcr.io/jack93g/project-chinese-story-generator)
```

- **Droplet**: DigitalOcean's name for a virtual machine. There is exactly one;
  the API, the worker and the database all run on it.
- **Caddy**: web server in front of the API. It gets and renews the HTTPS
  certificate automatically, and it's the only container reachable from the
  internet.
- **api / worker**: the same Docker image, started with different commands.
  The API answers requests; the worker generates stories in the background.
- **db**: PostgreSQL in a container. Its data lives in a Docker volume on the
  Droplet's own disk, so **deleting the Droplet deletes the database**. Backups
  are in the runbook.
- **GHCR**: GitHub Container Registry, where built images are stored, tagged by
  git commit SHA. It's public, so the Droplet can pull without a credential
  (the image contains code only, never secrets).
- **Terraform** (`infra/terraform/`) defines the Droplet, firewall, SSH key and
  DNS record as code. **cloud-init** is the first-boot script
  (`infra/terraform/cloud-init.yaml`) that DigitalOcean runs once on a new
  Droplet to create the `deploy` user, install Docker and harden SSH.

| Setting | Value |
| --- | --- |
| Provider / region | DigitalOcean, `fra1` |
| Image | Ubuntu 24.04 LTS x64 (`ubuntu-24-04-x64`) |
| Size | `s-1vcpu-2gb`: 1 vCPU, 2GB RAM, 50GB SSD (~$12/mo) |
| Hostname | `story-droplet` |
| IPv6 | Off (another public address to firewall and point DNS at, for no benefit) |
| DigitalOcean backups / monitoring | Both off. The database is backed up with encrypted weekly `pg_dump`s instead ([runbook](runbook.md#backups)) |
| Login | SSH keys only, as the `deploy` user; root and password logins are refused |
| Cloud firewall | Inbound TCP 22, 80, 443 from anywhere; all outbound allowed |

## Getting access

- **SSH**: as `deploy`, with the admin key (`~/.ssh/story_droplet`, a
  passphrase-protected ed25519 key). The runbook's
  [Conventions](runbook.md#conventions) section has the `~/.ssh/config` entry
  and the `dc`/`dbsql` shell helpers every procedure uses.
- **Root**: `sudo` as `deploy` (no password). DigitalOcean's web console does
  **not** work: it logs in as root over SSH, which is disabled.
- **Secrets**: the Droplet's `~/app/.env` (mode 600) and the password manager.
  Nothing secret is in the repo, the image, GitHub (apart from the CI deploy
  key), or Terraform.
- **Accounts you need**: DigitalOcean, Cloudflare (DNS for `huaben.app`),
  GitHub (repo admin, for Environments and packages), and the AI provider.

## Rebuild from scratch

Use this to build a new Droplet, or to replace one that's gone. Each step says
where it runs. Expect about an hour.

1. **Laptop: create the infrastructure with Terraform.** Set the credentials
   as shell variables only (never in a file in the repo):

   ```bash
   export DIGITALOCEAN_TOKEN=...            # DigitalOcean → API → Tokens
   export CLOUDFLARE_API_TOKEN=...          # Cloudflare → My Profile → API Tokens (Edit zone DNS)
   export TF_VAR_admin_ssh_public_key="$(cat ~/.ssh/story_droplet.pub)"
   export TF_VAR_cloudflare_zone_id=...     # Cloudflare → huaben.app → Overview
   cd infra/terraform
   terraform init
   terraform plan      # read all of it; see "Terraform" below before any apply
   terraform apply
   ```

   The output gives `droplet_ipv4` and `api_url`. If an old Droplet's host key
   is in `~/.ssh/known_hosts`, remove it (`ssh-keygen -R api.huaben.app` and
   `ssh-keygen -R <old-ip>`).

2. **Laptop: check first boot worked** (a few minutes after `apply`; the
   Droplet reboots once at the end). `ssh deploy@api.huaben.app`, then:

   ```bash
   docker --version && docker compose version   # Compose must be 2.24+
   sudo -n true && echo "sudo ok"
   command -v age && type dc
   sudo sshd -T | grep -Ei 'permitrootlogin|passwordauthentication'   # both "no"
   ```

   If `ssh` fails or anything is missing, see
   [cloud-init failures are silent](#cloud-init-failures-are-silent).

3. **Droplet: clone the repo and write `.env`.**

   ```bash
   git clone https://github.com/jack93g/project-chinese-story-generator.git ~/app
   touch ~/app/.env && chmod 600 ~/app/.env && nano ~/app/.env
   ```

   `.env` needs these values (from the password manager):

   | Variable | Notes |
   | --- | --- |
   | `POSTGRES_USER`, `POSTGRES_DB` | Database role and name |
   | `POSTGRES_PASSWORD` | Production-only; `openssl rand -hex 24` (letters and digits only, since it's embedded in a URL) |
   | `API_ACCESS_KEY` | `openssl rand -hex 32`; every route except `/health` requires it |
   | `CORS_ALLOWED_ORIGINS` | `https://huaben.app,https://www.huaben.app` |
   | `OPENAI_API_KEY`, `OPENAI_PROVIDER_LABEL`, `OPENAI_MODEL`, `OPENAI_BASE_URL` | The AI provider; the combination must be in `provider_registry.py`'s allowlist or the worker won't start |
   | `SKRITTER_ACCESS_TOKEN` | For vocabulary sync |

   `DATABASE_URL` isn't needed: Compose builds it from the `POSTGRES_*` values.

4. **Droplet: install the deploy script and lock the CI key to it.**

   ```bash
   cp ~/app/scripts/droplet-deploy.sh ~/deploy.sh && chmod 755 ~/deploy.sh
   ```

   Append this line to `~/.ssh/authorized_keys`, with the contents of
   `~/.ssh/story_ci_deploy.pub` from your laptop in place of `ssh-ed25519
   AAAA...`:

   ```
   command="/home/deploy/deploy.sh",restrict ssh-ed25519 AAAA... ci-deploy
   ```

   No CI key yet? Create one on the laptop (no passphrase: CI can't type one):
   `ssh-keygen -t ed25519 -f ~/.ssh/story_ci_deploy -N "" -C ci-deploy`, and
   set it as `DEPLOY_SSH_KEY` in the next step.

5. **GitHub: point the deploy workflow at the Droplet.** Settings →
   Environments → `production` (create it if missing, with "Deployment
   branches" set to "Selected branches" → `main`):
   - secret `DEPLOY_SSH_KEY`: the private key `~/.ssh/story_ci_deploy`;
   - variable `DROPLET_HOST`: `api.huaben.app`;
   - variable `DROPLET_HOST_KEY`: the output of
     `ssh-keyscan -t ed25519 api.huaben.app`, with **exactly the same host
     string** as `DROPLET_HOST` (a mismatch fails every deploy). A new Droplet
     has a new host key, so this must be updated on every rebuild.

6. **Laptop: first deploy.** This pulls the image, starts the database, runs
   migrations (creating the empty schema), then starts `api` and `worker`:

   ```bash
   git fetch origin
   gh workflow run deploy-backend.yml --ref main -f sha=$(git rev-parse origin/main)
   gh run watch
   ```

7. **Droplet: start Caddy.** Deploys never start or restart it:

   ```bash
   dc up -d caddy
   ```

   It fetches the HTTPS certificate on first start, which needs the DNS record
   from step 1 to already point at this Droplet.

8. **Laptop: check it's live and locked down.**
   - `curl -s https://api.huaben.app/health` returns `{"status":"ok"}`.
   - `/stories` returns 401 without the key, 200 with it.
   - Postgres and the API port aren't reachable from outside:
     `nc -z -w 5 api.huaben.app 5432` and `nc -z -w 5 api.huaben.app 8000` both
     fail.

9. **Data and backups.** Set up backups (runbook →
   [Backups → One-time setup](runbook.md#one-time-setup)). If this replaces a
   Droplet that had data, restore the newest backup
   (runbook → [Restore from a backup](runbook.md#restore-from-a-backup)).
   Otherwise, import vocabulary: `dc run --rm api sync-skritter --all`.

10. **Frontend.** Nothing to do unless the API's URL changed; the site is
    built with `api.huaben.app` baked in. A restored backup brings its login
    accounts with it; on a fresh database, create one with
    `dc run --rm api manage-users create <name>` and log in on the site.

## How it's configured

### Host

On the original, hand-built Droplet these were done by hand. On a Terraform
Droplet, cloud-init does all of them.

- **`deploy` user**: SSH key login only, no password. It's in the `docker`
  group and has passwordless `sudo` (`/etc/sudoers.d/90-deploy` on the
  hand-built Droplet; cloud-init's `sudo:` setting on Terraform Droplets).
- **Docker** from Docker's own apt repository, not Ubuntu's older `docker.io`
  package. Compose 2.24+ is required: `docker-compose.prod.yml` uses `!reset`.
- **SSH hardening** in `/etc/ssh/sshd_config.d/00-hardening.conf`:

  ```
  PermitRootLogin no
  PasswordAuthentication no
  ```

  The `00-` prefix matters: SSH uses the first value it reads, and the main
  `sshd_config` sets `PermitRootLogin yes`. Check with
  `sudo sshd -T | grep -Ei 'permitrootlogin|passwordauthentication'`.
- **`age`** (for encrypting backups) and the runbook's `dc`/`dbsql` helpers in
  `~deploy/.bashrc`.
- On the hand-built Droplet, the first `apt upgrade` asked about the modified
  `sshd_config`; the answer was "keep the local version". cloud-init makes the
  same choice non-interactively.

### Application stack

- **Always run Compose with both files** (the `dc` helper does this):
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml ...`.
  `docker-compose.prod.yml` swaps local builds for the GHCR image, removes the
  `db` and `api` port mappings, and adds Caddy. Plain `docker compose up` would
  publish Postgres and the API on the Droplet's localhost.
- **`IMAGE_TAG` is required** and has no default, so a missing tag fails loudly
  instead of deploying something unintended. The checked-out commit in `~/app`
  is always the deployed one, which is how `dc` sets it.
- **Caddy** (pinned to `caddy:2.11.4`) serves `api.huaben.app` with an
  automatic Let's Encrypt certificate (kept in the `caddy_data` volume), caps
  request bodies at 64KB, sets security headers, and proxies to `api:8000` on
  Docker's internal network.
- **DNS** is a Cloudflare A record `api.huaben.app` → the Droplet, set to **DNS
  only** (grey cloud). If Cloudflare proxied it, Caddy couldn't complete the
  certificate challenge, and the firewall would see Cloudflare's addresses
  instead of visitors'.

### API access control

Every route except `GET /health` and `/auth/login`/`/auth/logout` requires
either a login session or an `X-API-Key` header matching `API_ACCESS_KEY`
(compared in constant time); anything else gets 401. The API refuses to start
without the key, and its interactive docs are disabled.

- **Browser:** the frontend shows a login form. `POST /auth/login` checks the
  password against an argon2 hash and sets a `session` cookie scoped to
  `api.huaben.app`. The cookie is `HttpOnly` (page scripts can't read it),
  `Secure` and `SameSite=Lax`, and lasts 30 days. `huaben.app` and
  `api.huaben.app` count as the same site, so the browser sends the cookie with
  the frontend's requests but not with other sites'. Only a SHA-256 hash of
  each session token is stored (`auth_sessions`). Logging out revokes it, and
  `manage-users set-password` revokes all of a user's sessions.
  Cookie-authenticated writes must also carry an `Origin` in
  `CORS_ALLOWED_ORIGINS`, else 403. Login attempts are limited to 10 a minute
  in total, not per caller.
- **Scripts and `curl`:** the `X-API-Key` header. The frontend no longer uses
  the key at all, so nothing secret is kept in the browser.
Creating or retrying a generation returns 429 when 3 are already queued or
running, and is rate limited to 10 per minute per API process. `topic` is
capped at 200 characters.

### Terraform

`infra/terraform/` manages the Droplet, the firewall (inbound 22, 80 and 443),
the admin SSH key and the DNS record. Credentials come only from the shell
variables in [Rebuild step 1](#rebuild-from-scratch); `*.tfvars` files are
gitignored in case one is ever created.

- **The existing Droplet was imported, not created.** The hand-built Droplet,
  firewall, key and DNS record were each `terraform import`ed, so Terraform
  adopted them without changing anything.
- **`user_data` and `ssh_keys` are ignored after creation**
  (`lifecycle.ignore_changes`). DigitalOcean doesn't report which SSH keys or
  boot script an existing Droplet was created with, so Terraform would always
  see them as "changed". Changing `ssh_keys` forces Terraform to destroy and
  recreate the Droplet, which would take the database with it. Side effects:
  edits to `cloud-init.yaml` only affect new Droplets, and a new admin key
  isn't pushed to an existing one (see the runbook's secret rotation).
- **Always read `terraform plan` in full** before `apply`, and stop on any
  `forces replacement` or `destroy` line for the Droplet.
- **State** (`terraform.tfstate`) is local and gitignored, because it can
  contain sensitive values. It's the only record of what Terraform manages:
  back it up (e.g. to the password manager) after every real `apply`. If it's
  lost, Terraform no longer recognises the existing resources and would try
  to create duplicates. `.terraform.lock.hcl` (provider versions) is
  committed.
- **Testing a clean build**: run the same config from a scratch copy of the
  directory with its own state and throwaway names (e.g. `story-droplet-test`,
  `api-test.huaben.app`), do [Rebuild step 2](#rebuild-from-scratch)'s checks,
  then `terraform destroy` it. Never do this with the real state file.

### Deploy pipeline

`.github/workflows/deploy-backend.yml` runs on every push to `main`. It builds
the image, pushes it to GHCR tagged with the full git SHA (never `latest`), then
SSHes to the Droplet and runs `~/deploy.sh <sha>`. The Droplet never builds
images. All GitHub Actions in the workflow are pinned to commit SHAs.

`~/deploy.sh` (a copy of `scripts/droplet-deploy.sh`), in order:

1. Refuses any SHA not on `origin/main`, then checks it out in `~/app`, so the
   compose files and Caddyfile match the image.
2. Pulls the image (restoring the previous checkout if that fails).
3. Runs migrations while the old containers are still serving. It skips them
   when rolling back past a migration, since the older image doesn't know the
   newer schema's revision.
4. Recreates `api` and `worker` on the new image. `db` and `caddy` are never
   touched by a deploy; changes to them (including the Caddyfile) are applied
   by hand with `dc up -d caddy` or `dc up -d db`.
5. Waits for `/health` and checks the worker stays up.

A red run doesn't mean the old release is still live: if it failed at step 4
or 5, the new containers are already running. The script prints the previous
SHA so you can redeploy it. **Rollback** is the same workflow run by hand with
an older SHA; the full procedure is in the
[runbook](runbook.md#roll-back-application-code). The oldest SHA you can roll
back to is the first one this workflow built, since older commits have no
image.

**Why the deploy script is a copy outside the repo.** The CI key can run only
`/home/deploy/deploy.sh`: its `authorized_keys` line forces that command, and
the script accepts nothing but a 40-character SHA. If the script lived in
`~/app`, the code being deployed would decide what CI is allowed to do. The
catch is that the copy doesn't update itself; the runbook's
[Update the deploy or backup script](runbook.md#update-the-deploy-or-backup-script)
covers when and how to copy it.

**If the CI key leaks**, it can only deploy commits already on `main`. It lives
only in the `production` GitHub Environment, which only `main` can use, and
the Droplet's host key is pinned in that Environment so CI can't be pointed at
an impostor server.

The Droplet fetches code over HTTPS without a credential because the repo is
public. If it ever goes private, the Droplet will need a read-only deploy key
or token.

## Gotchas

### A missing firewall rule looks like an app outage

After the first frontend deploy, the site couldn't load data: the firewall had
no inbound rule for 443. DNS, SSH and port 80 all worked; the API just timed
out. A **timeout** points at a firewall dropping packets; **connection
refused** points at nothing listening. When the API is unreachable, check in
this order: `nc -z -w 5 api.huaben.app 443`, the firewall's inbound rules,
`dc ps`, then `dc logs caddy`.

### cloud-init failures are silent

`terraform apply` succeeds even if the boot script fails: DigitalOcean accepts
it and runs it afterwards. It failed twice while this was being built:

1. **The `deploy` user was never created.** It was added to the `docker` group
   in the `users:` section, but that group only exists once Docker is
   installed, later on. The fix: give sudo with the user's own `sudo:`
   setting, and add it to `docker` only after installing Docker.
2. **Nothing ran at all.** An em dash in a comment got corrupted on the way to
   the Droplet, the whole file became invalid YAML, and cloud-init silently
   applied none of it ("empty cloud config" in its log). The fix: keep
   `cloud-init.yaml` plain ASCII.

To diagnose, log in and check the log:
`sudo grep -iE "error|fail|warn" /var/log/cloud-init.log`. To see exactly what
DigitalOcean passed in, run `curl http://169.254.169.254/metadata/v1/user-data`
on the Droplet. If SSH as `deploy` doesn't work at all, the hardening probably
never ran either, in which case DigitalOcean's web console (which logs in as
root) is the way in.

## Known trade-offs

- **The `docker` group is effectively root.** Anyone who can start containers
  can mount the host's disk. The `deploy` user limits accidents, but a stolen
  admin key is as bad as a stolen root key, so protect it accordingly.
- **Passwordless `sudo` for `deploy`** follows from that: it doesn't grant
  anything the `docker` group doesn't already, and it's the normal route to
  root now that root SSH (and so the web console) is disabled.
- **One server** holds the API, worker and database. It's simple and cheap, but
  losing the Droplet means restoring from the latest weekly backup.
