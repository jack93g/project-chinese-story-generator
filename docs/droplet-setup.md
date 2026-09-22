# Droplet Setup (M5-4, manual)

Record of the manual provisioning done for M5-4, written so the Terraform
that follows can be checked against it and M5-5 can build the runbook from
it. Decisions behind these choices are in
[deployment-decisions.md](deployment-decisions.md). No secrets or IP
addresses are recorded here.

## What was created by hand

| Item | Choice |
| --- | --- |
| Provider / product | DigitalOcean Droplet |
| Image | Ubuntu 24.04 LTS x64 (`ubuntu-24-04-x64`) |
| Size | Regular SSD, 2GB RAM / 1 vCPU / 50GB (~$12/mo) |
| Hostname | `story-droplet` |
| IPv6 | Off (extra public address to firewall and DNS for no benefit) |
| Backups / monitoring | Off (backup and restore is M5-5) |
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
setup from code, provider auth (`DIGITALOCEAN_TOKEN`, `CLOUDFLARE_API_TOKEN`)
and the admin public key (`TF_VAR_admin_ssh_public_key`) supplied only as
shell env vars, never committed. First-boot provisioning (`deploy` user,
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
web console ("Launch Droplet Console") gives root access independent of
SSH/cloud-init succeeding at all. From there,
`grep -iE "error|fail|warn" /var/log/cloud-init.log` finds the actual cause,
and `curl http://169.254.169.254/metadata/v1/user-data` (from inside the
Droplet) shows the exact raw script DigitalOcean received, for comparing
against what's on disk.

## Known trade-offs

- Membership of the `docker` group is effectively root-equivalent (a user
  who can start containers can mount the host filesystem). `deploy` limits
  accidents and scope but is not a hard boundary against a stolen key, so
  the deploy key must be protected as carefully as a root credential.
- `deploy` has passwordless `sudo` (added via cloud-init). Given `docker`
  group membership is already root-equivalent, this doesn't meaningfully
  widen what a stolen key can do — it just avoids going through the
  DigitalOcean console for OS-level changes.

## Still to do

- Deploy pipeline (GHCR image tagged by git SHA, restart API and worker).
- Deploy hardening: dedicated deploy key in a GitHub Environment restricted
  to `main`.
