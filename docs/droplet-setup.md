# Droplet Setup

How the production server is built: a single DigitalOcean Droplet running
the API, the background worker and PostgreSQL with Docker Compose, behind
Caddy for HTTPS. It was first set up by hand, and that setup is recorded
below step by step. The same setup is now reproduced by Terraform (see
[Infrastructure as code](#infrastructure-as-code-terraform)), and this
document is the reference to check it against.

Day-to-day operating procedures are in [runbook.md](runbook.md). No secrets
or IP addresses are recorded here.

## What was created by hand

| Item | Choice |
| --- | --- |
| Provider / product | DigitalOcean Droplet |
| Image | Ubuntu 24.04 LTS x64 (`ubuntu-24-04-x64`) |
| Size | Regular SSD, 2GB RAM / 1 vCPU / 50GB (~$12/mo) |
| Hostname | `story-droplet` |
| IPv6 | Off (extra public address to firewall and DNS for no benefit) |
| Backups / monitoring | DigitalOcean backups off; encrypted weekly `pg_dump` instead (see [runbook.md](runbook.md#backups)) |
| Authentication | SSH key only; a dedicated ed25519 key, passphrase-protected |
| Cloud firewall | Inbound TCP 22, 80, 443 from anywhere; outbound default (allow all) |

## Host configuration

1. `apt update && apt upgrade`. During the upgrade, the modified
   `sshd_config` prompt was answered "keep the local version".
2. `deploy` user: no password, the same public key in
   `~/.ssh/authorized_keys` (mode 700 `.ssh`, 600 file). Member of the
   `docker` group.
3. Docker Engine and the compose plugin installed from Docker's official apt
   repository (signing key in `/etc/apt/keyrings/docker.asc`, source in
   `/etc/apt/sources.list.d/docker.sources`), not Ubuntu's `docker.io`.
4. SSH hardening in `/etc/ssh/sshd_config.d/00-hardening.conf`:

   ```
   PermitRootLogin no
   PasswordAuthentication no
   ```

   The `00-` prefix matters: the first value SSH reads wins, and the main
   `sshd_config` sets `PermitRootLogin yes`. Verified with
   `sshd -T | grep -Ei 'permitrootlogin|passwordauthentication'`, by
   confirming a root login is refused and `deploy` still works, and again
   after a reboot.

## Application stack

- The repo is cloned to `~/app` as `deploy` (public repo, so no credential is
  needed to clone). The `.env` is created by hand over SSH, mode 600, with a
  production-only Postgres password (`openssl rand -hex 24`, letters and
  digits only) and `API_ACCESS_KEY`; values live in the password manager.
  `CORS_ALLOWED_ORIGINS` lists both `https://huaben.app` and
  `https://www.huaben.app` explicitly.
- Run with both compose files, always:
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.
  Plain `docker compose up` would republish `db` and `api` on `127.0.0.1`.
- `docker-compose.prod.yml` removes the `db` and `api` port mappings, so only
  Caddy (pinned to `caddy:2.11.4`, the version proven on the Droplet) is
  published, on 80 and 443. Postgres is never published.
- Caddy terminates TLS for `api.huaben.app` (automatic Let's Encrypt
  certificate, kept in the `caddy_data` volume), enforces a 64KB request body
  limit, sets security headers, and proxies to `api:8000` on the internal
  Docker network.
- DNS is at Cloudflare: an A record `api.huaben.app` -> the Droplet, **DNS
  only** (grey cloud, not proxied), so Caddy can answer the certificate
  challenge and the firewall model stays simple.

## API access control

Every route except `GET /health` requires an `X-API-Key` header equal to
`API_ACCESS_KEY` (constant-time compare, 401 otherwise); the API refuses to
start without it and the interactive docs are disabled. The frontend prompts
for the key at runtime and stores it in the browser's `localStorage`; it is
never in the build or a `NEXT_PUBLIC_*` variable. Generation create/retry
return 429 at 3 queued+running requests and are rate limited to 10/min per
API process; `topic` is capped at 200 characters.

## Verified in production

- `/health` 200; `/stories` 401 without or with a wrong key, 200 with the key.
- Postgres (5432) and the API port (8000) are not reachable from the internet.
- CORS preflight from both frontend origins succeeds and echoes the origin; an
  unlisted origin gets no `access-control-allow-origin`.
- End to end on the live site: Skritter sync, story generation by the
  deployed worker against the deployed database, and reading the story.

## Gotcha: a missing firewall rule looks like an app outage

After the first frontend deploy, the site could not load data. The cause was
the cloud firewall having no inbound rule for 443: DNS, SSH and port 80 all
worked, and the API simply timed out. A **timeout** points at a firewall
dropping packets; a **refused** connection points at nothing listening. First
checks when the API is unreachable: `nc -z <ip> 443`, then the firewall's
inbound rules, then `docker compose ... ps` and the Caddy logs on the box.
Terraform (below) should define all three inbound rules explicitly.

## Infrastructure as code (Terraform)

`infra/terraform/` (Droplet, firewall, SSH key, DNS record) reproduces this
setup from code, provider auth (`DIGITALOCEAN_TOKEN`, `CLOUDFLARE_API_TOKEN`),
the admin public key (`TF_VAR_admin_ssh_public_key`) and the Cloudflare zone
ID (`TF_VAR_cloudflare_zone_id`, from the domain's Overview page) supplied
only as shell env vars, never committed. First-boot provisioning (`deploy` user,
Docker, SSH hardening) is replayed by `cloud-init.yaml`, passed as the
Droplet's `user_data`.

The real Droplet, firewall, SSH key and DNS record were each `terraform
import`ed rather than recreated, so Terraform adopted the hand-built
resources without touching them. `user_data` and `ssh_keys` are in the
Droplet's `lifecycle.ignore_changes`: DigitalOcean doesn't report back which
SSH keys or `user_data` an existing Droplet was created with, so declaring
them in config after import otherwise reads as "these differ" and Terraform
plans to destroy and recreate the Droplet (`ssh_keys` is a force-replacement
field) — which would take the real database with it, since Postgres's data
lives only in a Docker volume on the Droplet's own disk, nothing separate.
Always read `terraform plan` in full before `apply` on this resource, and
stop on any `forces replacement`/`destroy` line.

**State**: local `terraform.tfstate`, gitignored (state can hold sensitive
values and must never be committed). Since it's local-only, it's the single
source of truth for what Terraform manages — back it up (e.g. to the
password manager) after a real `apply`, since losing it means Terraform no
longer recognizes the existing infrastructure and would try to create a
duplicate of everything on the next `apply`. `.terraform.lock.hcl` (pins
provider versions) is committed; `.terraform.tfvars`/`.terraform/` are not.

**Proof that `apply` builds this from a clean state**, not just imports it:
run the same config in an isolated scratch directory (own state, own
throwaway resource names, e.g. `story-droplet-test`/`api-test.huaben.app`),
apply for real, verify SSH/Docker/sudo/hardening exactly as below, then
`terraform destroy` it. Never run this against the real Droplet's state.

### Gotcha: cloud-init failures are silent unless you go looking

The `user_data` script errored twice before working, and neither failure was
visible from the outside — `apply` succeeds either way, since DigitalOcean
just accepts the boot script and cloud-init runs it after `apply` returns:

1. `groups: [docker, sudo]` on the `deploy` user tried to add it to the
   `docker` group at user-creation time, before the `docker-ce` package
   (which creates that group) was installed by `runcmd` — `useradd` failed
   outright, so `deploy` never got created at all. Fix: grant `sudo` via the
   user's own `sudo:` directive instead of group membership, and only
   `usermod -aG docker deploy` after Docker is actually installed.
2. A single em dash in a `runcmd` comment corrupted into an invalid
   character somewhere in the Terraform → DigitalOcean → cloud-init
   hand-off, which made cloud-init treat the *entire* `user_data` as invalid
   YAML and silently apply none of it (logged as "empty cloud config").
   Fix: keep `cloud-init.yaml` plain ASCII.

Diagnosis, since SSH failures alone don't distinguish these: DigitalOcean's
web console ("Launch Droplet Console") logs in as root over SSH, so it works
only while root login is still allowed, which was the case here because the
hardening step never ran. On a correctly provisioned Droplet
(`PermitRootLogin no`) it fails with "All configured authentication methods
failed"; use `sudo` as `deploy` instead (see the runbook's Conventions). From
there,
`grep -iE "error|fail|warn" /var/log/cloud-init.log` finds the actual cause,
and `curl http://169.254.169.254/metadata/v1/user-data` (from inside the
Droplet) shows the exact raw script DigitalOcean received, for comparing
against what's on disk.

## Deploy pipeline

`.github/workflows/deploy-backend.yml` runs on every push to `main`: it builds
the image, pushes it to `ghcr.io/jack93g/project-chinese-story-generator`
tagged with the full git SHA (never `latest`), then SSHes to the Droplet to
deploy that SHA. The Droplet never builds images. All actions are pinned to
commit SHAs.

On the Droplet, `scripts/droplet-deploy.sh` (installed by hand as
`~deploy/deploy.sh`, outside the repo checkout so a deploy can't rewrite the
script that runs it) does, in order: check out the SHA (so the compose files
and Caddyfile match the image), `pull`, run migrations while the old
containers still serve, `up -d` for **both** `api` and `worker`, then wait for
`/health`. `docker-compose.prod.yml` reads the tag from `IMAGE_TAG`, which has
no default: a missing tag fails loudly rather than deploying something
unintended.

**Rollback** is the same pipeline: Actions -> "Deploy backend" -> Run workflow
-> paste an older full SHA into `sha`. The build is skipped (the image is
already in GHCR) and the script redeploys that tag. Migrations are not
reversed; they stay additive so an older image works against a newer schema.
If the rollback crosses a migration, the script skips `alembic upgrade head`
(the older image doesn't know the database's revision and would fail on it).
A red deploy run does **not** mean the previous release is still live: the
script has already replaced the api and worker containers by the time the
health checks run. On failure it prints the previous SHA; redeploy that via
the workflow's `sha` input. The script also refuses any SHA that is not on
`origin/main`. It relies on Docker Compose 2.24+ (for `!reset` in the prod
override), which the Droplet's Docker apt repo provides.

The earliest SHA you can roll back to is the commit that first ran this
workflow: only SHAs built by it have an image in GHCR, and older commits' compose
files have no `image:`/`IMAGE_TAG` support at all.

**What CI can do if its key leaks.** The CI key is a dedicated, passphrase-less
key whose `authorized_keys` line forces the deploy script, so it cannot open a
shell or run anything else; the script accepts only a 40-character SHA. That is
tighter than the `deploy` user's own access (which is root-equivalent through
the `docker` group). The key lives only in the `production` GitHub Environment,
restricted to `main`; the Droplet's host key is pinned in an Environment
variable so CI can't be steered to an impostor host.

### One-time setup (by hand)

1. **CI key**, on your laptop (no passphrase, CI can't type one):
   `ssh-keygen -t ed25519 -f ~/.ssh/story_ci_deploy -N "" -C ci-deploy`
2. **Droplet**: copy `scripts/droplet-deploy.sh` to `~deploy/deploy.sh`
   (`chmod 755`), then append this one line to `~deploy/.ssh/authorized_keys`,
   with the contents of `story_ci_deploy.pub` in place of `AAAA...`:
   `command="/home/deploy/deploy.sh",restrict ssh-ed25519 AAAA... ci-deploy`
3. **GitHub** -> Settings -> Environments -> New environment `production`;
   under "Deployment branches" choose "Selected branches" -> `main`. Add:
   - secret `DEPLOY_SSH_KEY` = contents of `~/.ssh/story_ci_deploy` (private)
   - variable `DROPLET_HOST` = the Droplet's IP or `api.huaben.app`
   - variable `DROPLET_HOST_KEY` = the output of
     `ssh-keyscan -t ed25519 <host>`, run with **exactly the same host string**
     as `DROPLET_HOST` (a `known_hosts` line is keyed by host, so an IP in one
     and the domain in the other fails every deploy under strict host-key
     checking). Compare its fingerprint against the one your first SSH login
     showed.
4. **GHCR visibility**: after the first push, GitHub -> your profile ->
   Packages -> the image -> Package settings -> change visibility to public
   (the image holds only code, no secrets), so `docker compose pull` on the
   Droplet needs no registry credential.

Nothing else is needed on the Droplet: the script fetches and checks out each
SHA itself, over HTTPS with no credential (the repo is public; if it ever goes
private, the Droplet needs a read-only deploy key or token).

The installed `~deploy/deploy.sh` is a hand-made copy, so it does not update
itself: after changing `scripts/droplet-deploy.sh`, copy it over again (and
compare with `diff`) before relying on the change. Only `api` and `worker` are
recreated by a deploy; changes to `db` or `caddy` (including the Caddyfile)
are applied by hand with `docker compose ... up -d caddy`. Because `docker-compose.prod.yml` requires `IMAGE_TAG`, compose
commands you run by hand there need it too; the checked-out commit is the
deployed one, so `export IMAGE_TAG=$(git rev-parse HEAD)` first.

## Known trade-offs

- Membership of the `docker` group is effectively root-equivalent (a user
  who can start containers can mount the host filesystem). `deploy` limits
  accidents and scope but is not a hard boundary against a stolen key, so
  the deploy key must be protected as carefully as a root credential.
- `deploy` has passwordless `sudo`: cloud-init adds it on Terraform-built
  Droplets, and the hand-built Droplet got the same rule afterwards in
  `/etc/sudoers.d/90-deploy` (`deploy ALL=(ALL) NOPASSWD:ALL`). Given `docker`
  group membership is already root-equivalent, this doesn't meaningfully
  widen what a stolen key can do. It does matter in practice: with root SSH
  login disabled, DigitalOcean's web console can't log in either, so `sudo`
  is the normal route to root.

## Operating it

Day-to-day procedures (deploy, rollback, worker restarts, failed requests,
backup/restore, secret rotation, abuse response, patching) and the log of
rehearsals are in [runbook.md](runbook.md).
