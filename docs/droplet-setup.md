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

## Known trade-offs

- Membership of the `docker` group is effectively root-equivalent (a user
  who can start containers can mount the host filesystem). `deploy` limits
  accidents and scope but is not a hard boundary against a stolen key, so
  the deploy key must be protected as carefully as a root credential.
- `deploy` has no `sudo`. OS-level changes go through the DigitalOcean web
  console until a better answer is needed.

## Still to do

- Terraform for the Droplet, firewall and DNS, with state handling documented.
- Deploy pipeline (GHCR image tagged by git SHA, restart API and worker).
- Deploy hardening: dedicated deploy key in a GitHub Environment restricted
  to `main`.
