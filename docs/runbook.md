# Operations Runbook

Known procedures for operating production: `api.huaben.app` on the single
Droplet described in [droplet-setup.md](droplet-setup.md). Every
procedure here is meant to be followed as written. If one turns out to be
wrong, fix this file in the same PR as whatever else changes.

Each procedure that must be rehearsed has an entry in the
[rehearsal log](#rehearsal-log) at the bottom. An unrehearsed procedure is a
guess.

## Contents

- [Conventions](#conventions)
- [Deploy a new version](#deploy-a-new-version)
- [Update the deploy or backup script](#update-the-deploy-or-backup-script)
- [Migration policy](#migration-policy)
- [Roll back application code](#roll-back-application-code)
- [Restart the worker](#restart-the-worker)
- [Inspect and retry a failed generation request](#inspect-and-retry-a-failed-generation-request)
- [Scheduled Skritter sync](#scheduled-skritter-sync)
- [Backups](#backups)
- [Restore from a backup](#restore-from-a-backup)
- [Rotate a secret](#rotate-a-secret)
- [Login accounts](#login-accounts)
- [Abuse response](#abuse-response)
- [Patching](#patching)
- [Rehearsal log](#rehearsal-log)

## Conventions

Everything "on the Droplet" means an SSH session as `deploy` with your admin
key (not the CI key, which can only run the deploy script). The commands in
this runbook use `deploy@api.huaben.app`, so tell SSH which key that host
uses, in `~/.ssh/config` on your laptop:

```
Host story api.huaben.app
    HostName api.huaben.app
    User deploy
    IdentityFile ~/.ssh/story_droplet
    IdentitiesOnly yes
```

Then `ssh deploy@api.huaben.app` (or `ssh story`) logs in. Without it, SSH
offers only your default keys and the Droplet answers "Permission denied
(publickey)".

**Root access** is `sudo` as `deploy` (passwordless). DigitalOcean's web
console doesn't work: it logs in as root over SSH, which is disabled. If
`sudo` ever stops working, the break-glass route is the `docker` group, which
`deploy` is in and which is root-equivalent. This starts a root shell on the
host itself; `exit` leaves it:

```bash
docker run --rm -it --entrypoint chroot -v /:/host postgres:17 /host /bin/bash
```

Production compose commands always need both files and `IMAGE_TAG`. The rest
of this runbook uses these two helpers from `~deploy/.bashrc`. A Droplet built
by Terraform gets them from `infra/terraform/cloud-init.yaml`; on one built by
hand, add them once, then `source ~/.bashrc`. If you change them, change both
places.

```bash
# Production compose, pinned to the image of the checked-out (deployed) commit.
dc() { (cd ~/app && IMAGE_TAG="$(git rev-parse HEAD)" docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"); }
# psql on the production database; credentials come from the db container.
dbsql() { dc exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' sh "$@"; }
```

`dbsql` opens an interactive prompt to paste queries into; arguments go to
`psql`, so `dbsql -c 'SELECT count(*) FROM stories;'` runs a single query. Every SQL snippet below is read-only unless it's wrapped in
`BEGIN; ... COMMIT;`.

## Deploy a new version

Merging to `main` deploys. There is nothing to run by hand.
`deploy-backend.yml` builds the image tagged with the commit SHA, pushes it to
GHCR, and SSHes to the Droplet, where `~deploy/deploy.sh` (a copy of
[scripts/droplet-deploy.sh](../scripts/droplet-deploy.sh)) does this, in order:

1. Checks out the SHA, refusing anything not on `origin/main`.
2. Pulls the image, restoring the previous checkout if the pull fails.
3. **Runs `alembic upgrade head`** (the `migrate` service) while the old API
   and worker are still serving. If the migration fails, the script stops here
   and the old version keeps running on the old schema. (Skipped on a
   rollback past a migration, see [Roll back](#roll-back-application-code).)
4. Recreates **both** `api` and `worker` on the new image, only after step 3
   has succeeded.
5. Waits for `/health` and checks that the worker is running.

Order matters: new code never starts against an old schema, and the old code
runs against the new schema for the length of steps 3–4. That's why
migrations have to be additive (next section).

**Check it worked:** the Actions run is green, then:

```bash
curl -s https://api.huaben.app/health
ssh deploy@api.huaben.app 'cd app && git rev-parse HEAD'   # should be the merged SHA
```

**If the run is red:** read the log. The script prints the previous SHA. If
it failed at or after step 4, the new containers are already live, so decide
whether to roll back ([below](#roll-back-application-code)) or fix forward.
If it failed before step 4, nothing that's running changed.

**If the merge changed `scripts/droplet-deploy.sh` or `scripts/db-backup.sh`**,
the deploy doesn't pick that up on its own. Follow
[Update the deploy or backup script](#update-the-deploy-or-backup-script).

## Update the deploy or backup script

Two scripts run on the Droplet from their **own copies** in the `deploy`
user's home, not from the git checkout in `~/app`:

| Script in the repo | Copy the Droplet runs | Run by |
| --- | --- | --- |
| `scripts/droplet-deploy.sh` | `~/deploy.sh` | every deploy (the CI key can run only this) |
| `scripts/db-backup.sh` | `~/db-backup.sh` | the weekly cron job |

A merge to `main` updates `~/app` but never these copies. So after a merge
that changes either script, the Droplet keeps running the old version until
you copy the new one over.

**Why copies?**

- **The CI key stays limited.** The key GitHub Actions uses is locked to
  `/home/deploy/deploy.sh`, so that file is everything CI can do on the
  server. If it lived in `~/app`, whatever code was being deployed would decide
  what it does. As a copy, only someone logged in over SSH can change it.
- **A rollback doesn't roll back the scripts.** A deploy checks out the target
  commit in `~/app`. Rolling back to an older commit would otherwise also bring
  back an older deploy script (missing later fixes) or remove the backup script
  if that commit predates it.
- **A running script isn't edited under itself.** Bash reads a script as it
  runs, so a deploy that checked out a new version of its own script could end
  up running a mix of old and new lines.

**When:** only after a merge that changes one of the two files above. You
don't need to do anything for other code, and nothing for
`scripts/db-restore.sh`, which you run by hand straight from `~/app`.

**How**, on the Droplet, after the merge's deploy has finished (don't copy
over `~/deploy.sh` while a deploy is running). Do only the script(s) the merge
changed. Read each `diff` before running the `cp` under it.

```bash
cd ~/app && git rev-parse HEAD                # must be the merged SHA, i.e. the deploy has run
```

Deploy script:

```bash
diff ~/deploy.sh scripts/droplet-deploy.sh    # read what changes
cp scripts/droplet-deploy.sh ~/deploy.sh
diff ~/deploy.sh scripts/droplet-deploy.sh && echo "deploy.sh up to date"
```

Backup script (if `~/db-backup.sh` doesn't exist yet, backups were never set
up: do [Backups → One-time setup](#one-time-setup) instead):

```bash
diff ~/db-backup.sh scripts/db-backup.sh      # read what changes
cp scripts/db-backup.sh ~/db-backup.sh
diff ~/db-backup.sh scripts/db-backup.sh && echo "db-backup.sh up to date"
```

`cp` onto an existing file keeps its permissions, so no `chmod` is needed.

**Check it works:**

- Deploy script, **from your laptop** (in the repo): redeploy what's already
  live. This runs the new copy without changing anything.
  ```bash
  git fetch origin
  gh workflow run deploy-backend.yml --ref main -f sha=$(git rev-parse origin/main)
  gh run watch
  gh run view --log | grep -o '==> .*'   # the deploy script's own lines
  ```
  `gh run watch` shows only job status; the last line of the log output should
  be `==> deployed <sha>`.
- Backup script, on the Droplet: run `~/db-backup.sh` once and check that a
  new file appears in `~/backups/`.

## Migration policy

Rolling back reverts the code, not the schema: an older image runs against
the newest schema. And during every deploy, the old code briefly runs against
the new schema. So every migration must be one the **previous** release can
live with.

**Allowed by default (additive):** new tables; new nullable columns; new
columns with a server default; new indexes; widening a type (e.g.
`VARCHAR(50)` → `TEXT`).

**Not allowed without the destructive procedure below:** dropping or renaming
a table or column; narrowing a type; making a column `NOT NULL` with no
default; adding a `CHECK`/`UNIQUE`/FK constraint that rows written by the old
code could violate (the old code is still writing during the deploy and after
a rollback).

**Renames and drops are two releases ("expand, then contract"):**

1. Release N adds the new column/table and changes the code to use it (and to
   backfill, if needed). The old column stays.
2. Release N+1, only after N has been live long enough that you'd never roll
   back past it, drops the old column. This moves the rollback floor to N.

**A destructive migration must, before it merges:**

- have a working `downgrade()`, tested locally from a copy of production
  data (restore a backup locally, see [Restore](#restore-from-a-backup)):
  ```bash
  .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head
  ```
- say in the PR description that it's destructive, which release it contracts,
  and the new rollback floor;
- be deployed right after a fresh manual backup (`~/db-backup.sh` on the
  Droplet).

Reviewing a PR with a migration: read `upgrade()` against the lists above.
`op.drop_*`, `op.alter_column(..., new_column_name=...)`, `nullable=False`
without `server_default`, and `op.create_check_constraint` are the lines to
stop on.

## Roll back application code

Use this when a deploy is live and broken, and fixing forward will take longer
than the rollback.

1. **Pick the target SHA.** Usually the previous deploy. Find it from the
   failed run's log ("previous release was ..."), or:
   ```bash
   gh run list --workflow deploy-backend.yml --branch main --status success --limit 5 \
     --json headSha,displayTitle,createdAt
   ```
   It must be on `main` and built by this workflow. Nothing older than the
   workflow's first run has an image (see the rollback floor in
   [droplet-setup.md](droplet-setup.md#deploy-pipeline)).
2. **Check the schema is compatible.** List migrations added since the
   target:
   ```bash
   git diff --stat <target-sha> origin/main -- alembic/versions/
   ```
   If they're all additive, go ahead. If one is destructive, the target is
   below the rollback floor; follow that migration's PR notes instead.
3. **Run the rollback.** Actions → *Deploy backend* → *Run workflow* → branch
   `main` → paste the full 40-character SHA into `sha`. Or:
   ```bash
   gh workflow run deploy-backend.yml --ref main -f sha=<target-sha>
   gh run watch
   gh run view --log | grep -o '==> .*'   # the deploy script's own lines
   ```
   The build is skipped (`gh run watch` shows it with `-` rather than `✓`) and
   the same deploy script runs against the old tag; the log ends with
   `==> deployed <target-sha>`.
   If the rollback crosses a migration, the database is at a revision the old
   image doesn't know. The script sees that (`alembic show` can't find it)
   and skips migrations, logging "newer than this image's migrations:
   skipping (rollback)". Otherwise `alembic upgrade head` is a no-op.

4. **Verify:** `curl -s https://api.huaben.app/health`; on the Droplet
   `cd ~/app && git rev-parse HEAD` shows the target;
   `dc ps --format '{{.Service}} {{.Image}}'` shows the target tag on both
   `api` and `worker`; load a story on the site.
5. **Roll forward** once the fix is merged. The merge to `main` deploys the
   new head automatically.

> **Gotcha:** any merge to `main` while rolled back deploys `main`'s head,
> which may still contain the bug. Revert or fix on `main` first.

**Rehearse** against a known-good pair of SHAs: roll back to the previous
deploy, verify, then roll forward by re-running the workflow with the current
`main` SHA. Record both run URLs in the [rehearsal log](#rehearsal-log).

## Restart the worker

The worker can be restarted without touching the API:

```bash
dc restart worker            # waits for a request in flight to finish (up to 90s)
dc ps worker                 # "Up ..." (not "Restarting")
dc logs --tail=20 worker
```

The logs should end with the old worker stopping and the new one starting:

```
Received SIGTERM; stopping after the current request.
Worker stopped.
Worker started (poll every 5s, reclaim every 5m, stale after 15m).
```

Check `dc ps worker` again after ~10 seconds: `Up 10 seconds` means it's
staying up; `Restarting` means it's crashing on startup (see the last bullet
below).

- `restart` keeps the existing container, **including its environment**. After
  editing `.env`, use `dc up -d --no-deps --force-recreate worker` instead. `restart`
  won't pick the change up.
- On SIGTERM (any stop, restart or deploy) the worker finishes the request
  it's working on, then exits. `stop_grace_period: 90s` in
  `docker-compose.yml` outlasts the provider's 60s request timeout, so a
  stop normally leaves nothing behind. A restart can take up to 90 seconds
  if a generation is mid-call.
- If a worker dies anyway (OOM kill, host crash, `docker kill`), its request
  is left `running`. Any worker requeues `running` requests that started more
  than 15 minutes ago (`--stale-after-minutes`): at startup and then every 5
  minutes (`--reclaim-interval-minutes`). So an orphan is back in `queued`
  (or `failed`, if it had used all 3 attempts) within about 20 minutes, with
  nothing to do by hand. It counts towards the cap of 3 active requests
  until then. To check for one:
  `SELECT id, started_at FROM story_generation_requests WHERE status = 'running';`
- If the worker won't stay up, `dc logs worker` usually shows why. Most often
  it's a missing/renamed `.env` value, or the provider/model combination isn't
  in `provider_registry.py`'s allowlist (the worker refuses to start).

## Inspect and retry a failed generation request

The frontend shows that a request failed. The detail lives in two tables:

- `story_generation_requests`: one row per request. `status`,
  `attempt_count` (max 3), `error_code` (the exception class name, e.g.
  `ProviderError`, `InsufficientVocabularyCoverage`), `error_message`,
  `started_at`/`completed_at`, the `provider`/`model` it ran against, `usage`
  (tokens and latency, on success), and `validation_report`.
- `raw_generation_payloads`: one row per attempt (`attempt_number`), holding
  the request body sent to the provider (`request_body`), the HTTP
  `response_status`, and the response body (`payload`). Both bodies are
  redacted before storage (see
  [redaction.py](../story_generator/generation/redaction.py)): headers are
  never stored, and any key containing `authorization`, `api_key`, `token`,
  `secret` or `password` reads `[REDACTED]`. So these are safe to read and
  paste into an issue, but not to publish (they contain your vocabulary and
  story text).

```sql
-- Recent failures
SELECT id, attempt_count, error_code, left(error_message, 120) AS error,
       provider, model, completed_at
FROM story_generation_requests
WHERE status = 'failed'
ORDER BY completed_at DESC
LIMIT 10;

-- Every attempt for one request (replace 42)
SELECT attempt_number, response_status, fetched_at,
       jsonb_pretty(payload) AS response
FROM raw_generation_payloads
WHERE generation_request_id = 42
ORDER BY attempt_number;

-- What was asked for: the prompt and the selected words
SELECT jsonb_pretty(request_body) FROM raw_generation_payloads
WHERE generation_request_id = 42 ORDER BY attempt_number DESC LIMIT 1;
SELECT jsonb_pretty(selected_vocabulary_snapshot), validation_report
FROM story_generation_requests WHERE id = 42;
```

Reading the error:

| `error_code` / `response_status` | Usually means | Retry? |
| --- | --- | --- |
| 401/403 | provider key revoked or wrong | No: [rotate](#rotate-a-secret) the key first |
| 402 / "insufficient credits" | provider account out of credit | After topping up |
| 429 | provider rate limit | Yes, after a pause |
| 5xx, timeout | provider outage | Yes |
| `InsufficientVocabularyCoverage` | the story didn't use enough of the requested words (see `validation_report`) | Yes (the output varies), but repeated failures point at the prompt or model |
| anything else | a bug; read the full `error_message` and `dc logs worker` | Only after a fix |

**Retry** with the frontend's *Retry* button, or the API:

```bash
read -rs API_KEY   # paste the key; keeps it out of shell history
curl -s -X POST -H "X-API-Key: $API_KEY" https://api.huaben.app/story-generations/42/retry
```

Retry only accepts `failed` requests with `attempt_count < 3` (409
otherwise). It also respects the 3-active-requests cap (429). A request
that's used all 3 attempts can't be retried. Start a new one with the same
settings from the frontend instead.

## Scheduled Skritter sync

**What:** cron on the Droplet runs `sync-skritter --all` every morning, so
words added in Skritter reach the app without anyone remembering to sync.

- **Daily (Mon–Sat):** fetches only words not already in the database. The
  words already there are just linked to their lists. It usually makes a
  handful of requests and takes seconds.
- **Weekly (Sun, `--refresh`):** re-fetches every word, one request per word
  (about 15 minutes for ~2,000 words), to pick up definition or reading edits
  made in Skritter.

**Safe to overlap:** a PostgreSQL advisory lock allows one sync at a time.
A sync that starts while another is running logs "Another Skritter sync is
already running. Skipping this run." and exits 0. That covers a manual
`dc run --rm api sync-skritter ...` too. If a sync dies mid-run (container
killed, Droplet rebooted), its run stays `running` until the next sync,
which marks it `failed` with "Interrupted".

**Deletions in Skritter:** nothing is deleted from the database, because
saved stories and past generation requests still refer to the words and lists.

- A word removed from a list is unlinked from that list at the next sync, so
  new stories from that list stop using it. The word itself stays.
- A list deleted in Skritter is archived (`vocabulary_lists.archived_at`) by
  the next full (`--all`) sync. It disappears from the Generate page and the
  API, and new stories can't use it. If it reappears in Skritter, the next
  full sync un-archives it.
- Safeguards: if Skritter returns a list with no words, or no lists at all,
  the sync keeps what's stored and logs a warning. A bad response can't wipe
  your vocabulary. If you really did empty a list, its old words stay linked
  until you add one word back.

**Raw payloads:** raw Skritter responses are kept for the 10 most recent
runs only (plus the one in progress). Older runs keep their `sync_runs` row.

### Cron setup

On the Droplet, `crontab -e` and add (times are UTC, after the Sunday
backup at 03:17):

```
23 4 * * 1-6 cd /home/deploy/app && IMAGE_TAG=$(git rev-parse HEAD) docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api sync-skritter --all >> /home/deploy/sync.log 2>&1
23 4 * * 0 cd /home/deploy/app && IMAGE_TAG=$(git rev-parse HEAD) docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api sync-skritter --all --refresh >> /home/deploy/sync.log 2>&1
```

Cron doesn't read `~/.bashrc`, so these spell out what `dc` does. They run
the image of the deployed commit, so a rollback also rolls back the sync code.

**After a rollback** to a commit older than the scheduled sync (before
`--refresh` existed), the Sunday line fails with an argparse error. Comment
it out until you roll forward. The daily line still works, but on old code
it re-fetches every word and keeps every raw payload.

### Checking the sync

The Generate page shows when vocabulary was last synced under the list picker.
It turns red when the last sync failed or is more than two days old. From
the Droplet:

```bash
tail -n 30 ~/sync.log
dbsql -c "SELECT id, status, started_at, completed_at, left(error_message, 120) FROM sync_runs ORDER BY id DESC LIMIT 5;"
dbsql -c "SELECT id, name, archived_at FROM vocabulary_lists WHERE archived_at IS NOT NULL;"
```

**If it's failing:** an `HTTPStatusError` with 401 means the Skritter token
expired or was revoked. Replace it ([Rotate a secret](#rotate-a-secret)).
A failure naming one list is a partial failure: the other lists synced, so
read that list's error in `~/sync.log`.

## Backups

**What:** a weekly `pg_dump` (custom format) of the production database,
encrypted with [age](https://age-encryption.org) by
[scripts/db-backup.sh](../scripts/db-backup.sh). The dump goes straight into
the encryption, so no plaintext copy is ever written.

**Where:** first in `~deploy/backups/` on the Droplet (28 days kept, so the last 4), then
pulled to your laptop (90 days kept). The laptop copy is the off-VM copy: the
Droplet's copies die with the Droplet.

**Protection:**

- The Droplet holds only the age **public** key (the recipient). It can
  write backups but can't decrypt them, so a compromised Droplet doesn't
  expose past backups (beyond the live database it already has).
- The **private** key is on your laptop at `~/.config/story-backup/age-key.txt`
  (mode 600) and in the password manager. Without it the backups are useless,
  so the password manager copy is not optional.
- `~deploy/backups/` is mode 700, each file 600. On the laptop the files are
  encrypted, so ordinary disk backups of that folder (Time Machine etc.) are
  fine.

**What's worth protecting:** stories and generation history are the only data
that can't be recreated. Vocabulary can be re-imported from Skritter
(`sync-skritter --all`).

**Why weekly:** a restore can lose up to a week of stories. That's
acceptable for a single-user app. To narrow the gap before anything risky
(a destructive migration, a Postgres upgrade, OS patching), take a manual
backup first. If losing a week ever starts to matter, change the cron line
to daily (`17 3 * * *`); the 28-day retention then keeps 28 backups on the Droplet.

### One-time setup

On your laptop:

```bash
brew install age
mkdir -p ~/.config/story-backup ~/Backups/huaben && chmod 700 ~/.config/story-backup ~/Backups/huaben
age-keygen -o ~/.config/story-backup/age-key.txt   # prints "Public key: age1..."
```

Save the whole `age-key.txt` in the password manager now.

On the Droplet (the public key is not secret):

```bash
sudo apt install age                                  # Terraform-built Droplets have it already
mkdir -p ~/.config/story-backup ~/backups && chmod 700 ~/.config/story-backup ~/backups
echo 'age1...' > ~/.config/story-backup/recipient.txt # the public key from above
cp ~/app/scripts/db-backup.sh ~/db-backup.sh && chmod 755 ~/db-backup.sh
~/db-backup.sh                                        # first run, by hand
crontab -e
```

Add this line to the crontab (Sundays, 03:17 UTC):

```
17 3 * * 0 /home/deploy/db-backup.sh >> /home/deploy/backups/backup.log 2>&1
```

### Weekly (Mondays): pull and check

```bash
rsync -a --ignore-existing --include='db-*.dump.age' --exclude='*' \
  deploy@api.huaben.app:backups/ ~/Backups/huaben/
ls -t ~/Backups/huaben | head -3        # newest should be from this Sunday
find ~/Backups/huaben -name 'db-*.dump.age' -mtime +90 -delete

# Decrypts and reads the newest dump's table of contents, which proves it's
# a complete, decryptable dump without restoring it.
f=$(ls -t ~/Backups/huaben/db-*.dump.age | head -1)
age -d -i ~/.config/story-backup/age-key.txt "$f" | pg_restore --list > /dev/null && echo "ok: $f"
```

If the newest file is old, read `~deploy/backups/backup.log` on the Droplet.
Cron failures are silent otherwise.

A manual backup (e.g. before a destructive migration or a Postgres upgrade)
is just `~/db-backup.sh` on the Droplet.

## Restore from a backup

[scripts/db-restore.sh](../scripts/db-restore.sh) runs on the Droplet and
reads a decrypted dump from stdin. You decrypt on the laptop and stream it
over SSH, so the private key never leaves the laptop.

### Rehearsal: restore next to the live database

Touches nothing that's running. Do this after setting up backups, and again
every few months:

```bash
f=$(ls -t ~/Backups/huaben/db-*.dump.age | head -1)
age -d -i ~/.config/story-backup/age-key.txt "$f" \
  | ssh deploy@api.huaben.app 'bash ~/app/scripts/db-restore.sh restore_check'
```

It prints row counts and the Alembic version of the restored copy. Compare
them with the live database (`dbsql`, then the same counts), allowing for
anything created since the backup. Then drop the copy:

```bash
ssh deploy@api.huaben.app 'bash ~/app/scripts/db-restore.sh --drop restore_check'
```

### For real: replace the live database

Use this when the live data is lost or corrupted. It restores into a staging
database first, while the site keeps running. Only if that succeeds does it
stop `api` and `worker`, swap the databases by rename (the old one is kept,
not dropped), run migrations, start both again, and wait for `/health`.

```bash
age -d -i ~/.config/story-backup/age-key.txt ~/Backups/huaben/db-<stamp>.dump.age \
  | ssh deploy@api.huaben.app 'bash ~/app/scripts/db-restore.sh --replace-live'
```

Check the site, then drop the kept database it names
(`db-restore.sh --drop <name>_before_restore_<stamp>`).

**If it fails after the swap** (the script says the API isn't healthy), undo
the swap by hand. The api and worker are down at that point anyway:

```bash
dc stop api worker
dbsql   # psql prompt, connected to the live db; switch to the maintenance db first:
```

```sql
\c postgres
ALTER DATABASE <live> RENAME TO <live>_restoring;
ALTER DATABASE <live>_before_restore_<stamp> RENAME TO <live>;
```

```bash
dc up -d --no-deps api worker
```

**If the Droplet itself is gone:** follow
[Rebuild from scratch](droplet-setup.md#rebuild-from-scratch) in
droplet-setup.md. Its step 9 restores the newest laptop backup with
`--replace-live`.

## Rotate a secret

The rule for all of them: **after editing `~/app/.env`, recreate both
services**. `restart` keeps the old environment:

```bash
nano ~/app/.env                            # mode stays 600
dc up -d --no-deps --force-recreate api worker
curl -s https://api.huaben.app/health
```

Update the password manager in the same sitting, and only revoke the old
value once the new one is proven working.

| Secret | Where to get a new one | Also do |
| --- | --- | --- |
| `API_ACCESS_KEY` | `openssl rand -hex 32` | Check `grep '^API_ACCESS_KEY=' ~/app/.env` shows the new key (nano saves with `Ctrl+O`, Enter). The browser doesn't use it (it logs in), so prove it with `curl -s -o /dev/null -w '%{http_code}\n' -H "X-API-Key: $NEW_KEY" https://api.huaben.app/stories` → `200`. The old key stops working immediately. |
| Login password | See [Login accounts](#login-accounts) | Not in `.env`; stored hashed in the database. |
| `OPENAI_API_KEY` (OpenRouter) | Provider dashboard → new key | Queue one story to prove it, then delete the old key in the dashboard. |
| `SKRITTER_ACCESS_TOKEN` | Skritter account settings | Only `sync-skritter` uses it; prove with `dc run --rm api sync-skritter --list-id <id>`. |
| DB password (`POSTGRES_PASSWORD`) | `openssl rand -hex 24` (letters and digits only) | See below: `.env` alone doesn't change it. |
| CI deploy key (`DEPLOY_SSH_KEY`) | See below | |
| Admin SSH key | See below | |
| Backup age key | See below | |

**DB password.** `POSTGRES_PASSWORD` only sets the password when the data
volume is first created. Changing `.env` alone locks the api and worker out.
Change the role's password first, then `.env`:

```bash
dc exec db sh -c 'psql -U "$POSTGRES_USER" -d postgres'
#   postgres=# \password          -- prompts twice; not echoed or logged
#   postgres=# \q
nano ~/app/.env                   # set POSTGRES_PASSWORD to the same value
dc up -d --no-deps --force-recreate api worker
```

The `db` container can keep its old `POSTGRES_PASSWORD` environment. Inside
the container it connects over the local socket, which doesn't use the
password.

**CI deploy key.** New key on the laptop
(`ssh-keygen -t ed25519 -f ~/.ssh/story_ci_deploy_new -N "" -C ci-deploy`).
Append its forced-command line to `~deploy/.ssh/authorized_keys` next to the
old one (same format as in
[droplet-setup.md](droplet-setup.md#rebuild-from-scratch)). Set the
`production` Environment secret `DEPLOY_SSH_KEY` to the new private key.
Prove it by redeploying the current SHA:

```bash
gh workflow run deploy-backend.yml --ref main -f sha=$(git rev-parse origin/main)
```

Then delete the old line from `authorized_keys` and the old key files.

**Admin SSH key.** New passphrase-protected key, append its public key to
`~deploy/.ssh/authorized_keys`, and prove a login **in a new terminal**
before removing the old line. Update `TF_VAR_admin_ssh_public_key` so a
rebuilt Droplet gets it. `ssh_keys` is in `ignore_changes`, so the plan only
touches the `digitalocean_ssh_key` resource. Read the plan anyway, and stop
on anything that replaces the Droplet.

**Backup age key.** New `age-keygen` on the laptop, then put the new public
key in `~/.config/story-backup/recipient.txt` on the Droplet. Keep the old
private key (in the password manager) until the last backup made with it has
aged out (90 days).

**Cloud provider tokens** (`DIGITALOCEAN_TOKEN`, `CLOUDFLARE_API_TOKEN`) only
ever live in your shell for a Terraform run. Rotate them in each dashboard;
nothing on the Droplet uses them.

## Login accounts

The site's login accounts live in the `users` table. There's no sign-up page
and no emailed password reset: both are done on the Droplet. The password is
prompted for twice (at least 12 characters) and never appears in shell
history. Keep it in the password manager.

```bash
dc run --rm api manage-users create <name>          # first account, after the release that added login
dc run --rm api manage-users set-password <name>    # forgotten or leaked password
```

`set-password` also logs that account out everywhere, which makes it the way
to cut off a stolen session cookie. To log out every session for every
account without changing passwords (in `dbsql`):

```sql
BEGIN;
UPDATE auth_sessions SET revoked_at = now() WHERE revoked_at IS NULL;
COMMIT;
```

## Abuse response

Signs: requests you didn't make, the provider bill jumping, the 3-request cap
always full.

1. **Stop the spending first.** Queued requests just wait:
   ```bash
   dc stop worker
   ```
2. **Cut off access.** [Rotate `API_ACCESS_KEY`](#rotate-a-secret) (every
   request with the old key gets 401 from then on). Then change each login's
   password with `manage-users set-password`, which also ends its sessions
   (see [Login accounts](#login-accounts)).
3. **Look at the volume:**
   ```sql
   SELECT date_trunc('hour', created_at) AS hour, status, count(*),
          sum((usage->>'total_tokens')::int) AS tokens
   FROM story_generation_requests
   WHERE created_at > now() - interval '48 hours'
   GROUP BY 1, 2 ORDER BY 1 DESC, 2;
   ```
   Then check the provider dashboard's activity/cost page for the same
   window. It's the source of truth for money. `usage` is only recorded on
   success, so failed attempts cost tokens that don't show here. Access logs:
   `dc logs --since 48h api` (client addresses there are Caddy's, not the
   caller's).
4. **Drain the queue.** Prefer cancelling (keeps the audit trail) over
   deleting:
   ```sql
   BEGIN;
   UPDATE story_generation_requests
   SET status = 'failed', started_at = now(), completed_at = now(),
       -- Retry only accepts attempt_count < 3, so this makes the
       -- cancellation final rather than one click from being requeued.
       attempt_count = 3,
       error_code = 'OperatorCancelled',
       error_message = 'Cancelled by operator during abuse response'
   WHERE status = 'queued'
   RETURNING id, topic, created_at;
   COMMIT;   -- or ROLLBACK if the list looks wrong
   ```
   These rows then show as failed with no attempts actually made; the
   `OperatorCancelled` error code is what tells them apart.
   To remove the rows entirely instead, use `DELETE FROM
   story_generation_requests WHERE status = 'queued' RETURNING id;` in the
   same `BEGIN`/`COMMIT` wrapper. Queued rows have no stories or payloads
   attached yet.
5. If the **provider key** may have leaked too (e.g. spending that doesn't
   match the rows above), rotate `OPENAI_API_KEY` as well.
6. `dc up -d --no-deps worker`, then queue one story yourself to confirm things work.

## Patching

**Host OS.** Ubuntu's `unattended-upgrades` applies security updates
automatically. Check it's on with `systemctl is-active unattended-upgrades`.
Monthly, or when a notable CVE lands:

```bash
~/db-backup.sh
sudo apt update && sudo apt upgrade
[ -f /var/run/reboot-required ] && sudo reboot
```

All services have `restart: unless-stopped`, so they come back after a reboot
or a Docker engine upgrade. Afterwards: `dc ps` (all Up) and
`curl -s https://api.huaben.app/health`. Expect a minute or so of downtime.

**App image** (`FROM python:3.12`, a moving tag). Every build resolves the tag
again, so any deploy picks up the latest Python patch release and Debian
security updates. Normally that's enough. For an urgent base-image fix with no
code change to ship, rebuild the current `main` (*Run workflow* on `main`
with `sha` left empty). This overwrites that SHA's tag with the rebuilt image,
so a later rollback to it gets the patched build (which is what you want).

**Postgres** (`postgres:17`, moving within 17.x). A minor update:

```bash
~/db-backup.sh
dc pull db && dc up -d db
dc up -d --no-deps --force-recreate api worker   # drop connections to the old server
```

A major version (18) can't reuse the data volume. That's a dump and restore
into a new volume (the [restore](#restore-from-a-backup) procedure plus a
compose change). Plan it as a separate piece of work.

**Caddy** (pinned in `docker-compose.prod.yml`). Bump the tag in a PR. After
it deploys, `dc up -d caddy` by hand (deploys don't recreate Caddy), then
check TLS: `curl -sI https://api.huaben.app/health`.

**GitHub Actions** pins are bumped by Dependabot PRs against `dev`.

## Rehearsal log

Record each rehearsal here (date, what was done, evidence, anything the
procedure got wrong and the fix). The rollback and restore entries matter
most: they prove code and data can both be recovered.

| Date | Procedure | Evidence | Notes |
| --- | --- | --- | --- |
| 2026-09-23 | Backup + both restore modes, on a local copy of the prod compose stack (not the Droplet) | Scripts run end to end: encrypted dump, pruning, scratch restore, `--replace-live` swap with health check, and the manual undo | Stand-in for `age` was used; not a substitute for the production rehearsal below |
| 2026-09-24 | Deploy by merge (PR #65), then update the Droplet's `deploy.sh` copy and redeploy the live SHA to prove it (production) | [merge deploy](https://github.com/jack93g/project-chinese-story-generator/actions/runs/35977036214), [redeploy with new script](https://github.com/jack93g/project-chinese-story-generator/actions/runs/35977642641): `api`/`worker` left `Running`, `migrate` not re-run | Runbook's copy steps didn't cover a first install of `db-backup.sh` or say the check runs from the laptop; fixed |
| 2026-09-24 | Worker restart independent of the API (production) | `Received SIGTERM ... Worker stopped.` in 0.8s, `dc ps` Up | No startup log line, and output was buffered until exit; fixed with `PYTHONUNBUFFERED` and a startup message |
| 2026-09-24 | Backup setup, first backup, laptop pull and decrypt check (production) | `==> wrote`, then `pg_restore --list` OK on the laptop | `deploy` had no sudo and the web console can't log in as root; gave `deploy` passwordless sudo via the docker break-glass route. Runbook host needed an `~/.ssh/config` entry; both documented |
| 2026-09-24 | Restore rehearsal from a laptop backup into `restore_check` (production) | Row counts and Alembic version matched live; `restore_check` dropped | |
| 2026-09-24 | Rollback `8d919dc` → `56637e0` and roll forward (production) | [rollback](https://github.com/jack93g/project-chinese-story-generator/actions/runs/35981613467) (build skipped), [roll forward](https://github.com/jack93g/project-chinese-story-generator/actions/runs/35981959976); `git rev-parse` and `dc ps` image tags checked each way | `gh run watch` hides the script's `==>` lines; runbook now shows `gh run view --log` |
| 2026-09-24 | Rotate `API_ACCESS_KEY` (production) | `.env` holds the new key, the running `api` has the same value (hash compare), the site works with the new key | A two-key curl test was easy to paste in the wrong order and looked like a failure; runbook now checks `.env` and the site instead |
