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

## Known trade-offs

- Membership of the `docker` group is effectively root-equivalent (a user
  who can start containers can mount the host filesystem). `deploy` limits
  accidents and scope but is not a hard boundary against a stolen key, so
  the deploy key must be protected as carefully as a root credential.
- `deploy` has no `sudo`. OS-level changes go through the DigitalOcean web
  console until a better answer is needed.

## Still to do

- Clone the repo, create the `.env` by hand, and run the compose stack.
- Caddy for TLS in front of the API; DNS record to the Droplet.
- Terraform for the Droplet, firewall and DNS, with state handling documented.
- Deploy pipeline (GHCR image tagged by git SHA, restart API and worker).
