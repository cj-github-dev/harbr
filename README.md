# Harbr

**Recovery begins with confidence.**

Harbr is a read-only recovery-confidence platform.

Its purpose is to answer one question:

> Can I recover right now?

Harbr v4 Founder's Edition begins with the Lac du Flambeau site and the
existing Docker backup implementation.

## Web experience

The interface is intentionally small: plain HTML, CSS, JavaScript, and JSON.
It has no package dependencies, build step, or generated frontend output.

The Docker Compose service exposes the UI and read-only JSON API together.
Run `docker compose up -d`, then open `http://localhost:8088`. The experience
reads live documents from `/api/v1/`; it never inspects the host directly.

## API source and runtime ownership

Harbr keeps source data and generated deployment data in separate locations:

- `api/bootstrap/v1/` contains source-controlled bootstrap/example API
  documents. These make a fresh clone usable before its first backup refresh.
- `state/sites/` contains source-controlled site configuration.
- `state/recovery/prerequisites.json` contains the curated, source-controlled
  host recovery requirement model. It is not a dump of installed packages.
- `api/v1/` contains the active published runtime API. Its JSON files are
  generated, ignored by Git, and served read-only by Nginx.
- `state/.api-build/` contains ignored, per-refresh temporary build
  directories. A successful or failed refresh removes its own build directory.

The refresh must run as the normal deployment user that owns the checkout and
Harbr runtime files—for example, the `harbr` service account or the existing
deployment account. It deliberately refuses to run as root. Configure the
systemd unit with `User=<deployment-user>` and `Group=<deployment-group>`; do
not call the refresh through unrestricted `sudo` or a root timer.

### Deployed refresh launcher and permissions

On `dockerhost`, `docker-backup.timer` schedules
`docker-backup.service` at 10:30. The service runs
`/usr/local/sbin/docker-backup.sh` as `root`; that script does not invoke
`refresh-api.sh`. Keep this root backup job unchanged. A successful backup
instead starts a separate `harbr-api-refresh.service` through systemd's
`OnSuccess=` relationship. The refresh runs as the deployment user `chris`,
so its root refusal does not interrupt either scheduled service.

The refresh reads a sanitized `/etc/harbr/backup-api.conf` instead of the
root-only `/etc/docker-backup.conf`. It also needs read access to status and
history metadata, directory-list access to the backup root, and rclone
credentials that can list the configured OneDrive retention directories. It
does not need the Docker socket or access to archive contents.

Install the launcher and its permissions as follows:

```bash
cd /srv/docker/harbr
./scripts/preflight-refresh-host.sh
sudo groupadd --force harbr-api
sudo usermod --append --groups harbr-api chris
sudo install -d -o root -g harbr-api -m 0750 /etc/harbr
sudo grep -E '^(BACKUP_ROOT|RCLONE_REMOTE|RCLONE_ROOT|LOCAL_RETENTION|ONEDRIVE_DAILY_RETENTION|ONEDRIVE_WEEKLY_RETENTION|ONEDRIVE_MONTHLY_RETENTION)=' /etc/docker-backup.conf | sudo tee /etc/harbr/backup-api.conf >/dev/null
sudo chown root:harbr-api /etc/harbr/backup-api.conf
sudo chmod 0640 /etc/harbr/backup-api.conf
sudo ./scripts/install-rclone-remote.sh
sudo setfacl -m g:harbr-api:rx /var/lib/docker-backup
sudo setfacl -m g:harbr-api:r /var/lib/docker-backup/status.json /var/lib/docker-backup/history.jsonl
sudo setfacl -d -m g:harbr-api:r-X /var/lib/docker-backup
sudo install -o root -g root -m 0644 deploy/systemd/harbr-api-refresh.service /etc/systemd/system/harbr-api-refresh.service
sudo install -d -o root -g root -m 0755 /etc/systemd/system/docker-backup.service.d
sudo install -o root -g root -m 0644 deploy/systemd/docker-backup.service.d/harbr-api-refresh.conf /etc/systemd/system/docker-backup.service.d/harbr-api-refresh.conf
sudo systemctl daemon-reload
```

The preflight exits before installation with an explicit instruction to install
the `acl` package when `setfacl` is unavailable. The allowlisted backup-config
extraction keeps the deployed paths and retention
targets synchronized without exposing unrelated backup secrets. Repeat it when
those settings change. The rclone installer reads the root-owned configuration,
extracts only the `[OneDrive]` remote, verifies that no other remote is present,
and installs the result as `/var/lib/harbr/rclone/rclone.conf`. Its directory is
owned by `chris:chris` with mode `0700`, and the config is mode `0600`, so the
service can atomically persist refreshed OAuth tokens without exposing the
credentials to other users or the metadata-reader group. Run the installer
again when the source OneDrive credentials are deliberately replaced.
Unrelated root rclone remotes and credentials are never copied from the private
source configuration.

The backup root is already `chris:chris 0755`, which is sufficient for counting
its timestamped child directories; no recursive archive permission change is
needed. The ACLs allow members of `harbr-api` to read existing and newly created
metadata while the backup process retains root ownership. The systemd drop-in
reapplies the file ACL after every backup before the non-root refresh is
triggered, including when the backup script atomically replaces a metadata
file.

If an older deployment already has root-owned generated output, repair it once
before deploying this change:

```bash
sudo chown -R <deployment-user>:<deployment-group> api/v1 state/.api-build
sudo find api/v1 state/.api-build -type d -exec chmod 0755 {} +
sudo find api/v1 -type f -name '*.json' -exec chmod 0644 {} +
```

This preserves the active published API; it changes only ownership and modes.

Verify the service identity and every required input before relying on the
next scheduled run:

```bash
sudo -u chris -g harbr-api test -r /etc/harbr/backup-api.conf
sudo -u chris -g harbr-api test -r /var/lib/docker-backup/status.json
sudo -u chris -g harbr-api test -r /var/lib/docker-backup/history.jsonl
sudo -u chris -g harbr-api test -r /srv/storage/backups/docker
sudo -u chris -g chris test -w /var/lib/harbr/rclone
sudo -u chris -g chris test -w /var/lib/harbr/rclone/rclone.conf
sudo -u chris -g chris env RCLONE_CONFIG=/var/lib/harbr/rclone/rclone.conf rclone listremotes
sudo -u chris -g chris env RCLONE_CONFIG=/var/lib/harbr/rclone/rclone.conf rclone lsf --dirs-only "OneDrive:Docker Systems/LDF Backup Center/backups/daily"
sudo stat -c '%U:%G %a %n' /var/lib/harbr/rclone /var/lib/harbr/rclone/rclone.conf
sudo systemctl start harbr-api-refresh.service
sudo systemctl show harbr-api-refresh.service -p User -p Group -p Result
git status --short
```

The expected service properties are `User=chris`, `Group=chris`, and
`Result=success`; `rclone listremotes` must print only `OneDrive:`. The `lsf`
command must complete without a token-save permission error, including when
OneDrive refreshes its OAuth token. Afterward, the runtime directory and file
must remain `chris:chris` modes `0700` and `0600`, respectively, and Git status
must remain empty. Do not enable the oneshot service directly. The backup
service triggers it after each successful backup, and a failed backup does not
publish a misleading new API snapshot.

### Fresh deployment initialization

After cloning, initialize live API files from the tracked bootstrap documents
as the deployment user, then start the web service:

```bash
cd /srv/docker/harbr
HARBR_ROOT="$PWD" ./scripts/init-api.sh
docker compose up -d
```

Initialization validates and atomically copies only missing files, so it never
overwrites an active published API. The regular Docker adapter refresh later
generates into a private temporary directory, validates every JSON document,
and atomically publishes complete files into `api/v1/`.

To verify that normal generation does not dirty the checkout:

```bash
git status --short
./scripts/validate-api-refresh.sh
git status --short
```

Both status commands should be empty. Run the integration validator as the
deployment user; it intentionally refuses root execution.

The v4 experience retains Harbr's startup animation, Confidence Ring,
seasonal landscape, glass surfaces, typography, and responsive navigation.

### Infrastructure

`/api/v1/infrastructure.json` is Harbr's read-only, multi-site operational
view. Its hierarchy is `sites[] → hosts[] → optional capabilities`: Docker
projects and services, platform services, filesystems, and virtualization with
stable VM entities. Docker is optional, so the same v1 contract can represent
the LDF Docker host, a Lake Forest Synology platform with containers and VMs,
Linux VMs, hypervisors, and appliances without coupling the browser to a
collector.

The initial adapter is `plugins/service-check/generate-infrastructure.sh`.
It reads the external collector's private record from
`/var/lib/service-check/status.json` (override with
`SERVICE_CHECK_SOURCE`), selects only public fields, validates the normalized
document, and atomically publishes it through a private `state/.api-build`
directory. It never runs health/package/registry/systemd checks, reads the
Docker socket, or modifies the collector source. Digests, image IDs,
management addresses, Compose paths, logs, credentials, secrets, and other
unselected private fields cannot cross the allow-list transformation.

The publisher must run as the normal Harbr deployment user, never root. That
user needs read/search permission on the source file and its parent directory;
provision this on the host with an existing appropriate group or ACL. Harbr
does not assume or create a user/group and does not weaken file permissions.
If the source is unreadable or transformation/validation fails, the adapter
exits nonzero before its atomic rename and leaves the last valid public file
intact.

Infrastructure timestamps carry a 300-second freshness window. The Experience
calculates freshness in the browser and polls only this resource every 60
seconds with `cache: no-store`. Missing, failed, or stale data preserves useful
last-known details but changes current confidence to the neutral/unknown
presentation. Infrastructure never changes Restore Confidence.

Statuses aggregate from workloads through hosts and sites using `healthy`,
`warning`, `failure`, and `unknown`. Runtime health remains separate from image
maintenance: a healthy service can report `update_available`, causing an
attention-level project/host/site without presenting the service as failed.

After service-check has written a record, publish and inspect it with:

```bash
cd /srv/docker/harbr
chmod +x plugins/service-check/generate-infrastructure.sh
SERVICE_CHECK_SOURCE=/var/lib/service-check/status.json \
  HARBR_ROOT="$PWD" ./plugins/service-check/generate-infrastructure.sh
jq empty api/v1/infrastructure.json
jq '{generated_at,status,summary,sites}' api/v1/infrastructure.json
```

To verify source permissions without displaying private content, run:

```bash
sudo -u "$(stat -c '%U' /srv/docker/harbr)" test -r /var/lib/service-check/status.json
```

If that check fails, an administrator must grant the deployment identity
read/search access using the host's established access-control policy before
running the adapter. Do not make the API publisher root or expose the private
record through Nginx.

### Confidence Ring configuration

`ui/experience/config/confidence-ring.json` is the authoritative approved
export from the Confidence Ring Lab. Future visual or motion tuning begins in
the Lab; after approval, export the complete configuration into that file and
run `python scripts/generate-confidence-ring-css.py`. The generated
`confidence-ring.generated.css` maps every exported value to shared production
CSS custom properties and must not be edited directly. Repository validation
fails when the export, mapping, and generated CSS drift apart.

The Lab term `living-light` is named **Confidence Sweep** in the product. Its
rotation period comes directly from the approved export. The production-only
orbit inset and mask geometry move the sweep outside the central copy so it
cannot overlap the label, confidence level, or explanation; this is the sole
approved visual departure from the exported configuration.

All values in the current schema-version-1 export are consumed by the
production ring. If a future export introduces a value that production cannot
yet use, preserve it in the JSON and document the reason here before updating
the explicit generator mapping—never silently discard it or add a preset.

First-party Reference Center guides live in
`ui/experience/data/reference.json`. The format is intentionally plain JSON:
each entry has a stable ID, title, summary, and ordered sections containing
headings and paragraphs. The UI also presents every resource published by the
API index with a formatted view and raw JSON view.

### Host recovery inventory

`/api/v1/inventory.json` is generated on Linux by
`plugins/docker/generate-inventory.sh` during the existing non-root API refresh.
It merges the curated prerequisite definitions with safe detections for Debian,
kernel, architecture, curated package and command versions, relevant systemd
units, the current deployment identity, and the existence of the `harbr-api`
group. Missing commands and unavailable inspections are represented explicitly;
they do not abort inventory generation or the rest of the API refresh.

The bootstrap inventory deliberately reports `not-generated` with unknown host
facts rather than hard-coding a development or production host. A live refresh
replaces it atomically with generated data. The inventory schema is
`contracts/v1/inventory.schema.json`, and the resource is published through the
versioned API index so the existing Reference Center presents formatted and raw
views without frontend-specific host values.

The inventory never reads configuration contents, environment dumps, rclone
credentials, repository authentication, private keys, tokens, passwords, or
unrelated account records. Component requirements that cannot be detected from
the host remain manually maintained in `state/recovery/prerequisites.json`.

## Historical snapshots

`/api/v1/history.json` remains backward-compatible and keeps the existing run
metrics at the top level. A run may additionally include a `snapshot` with the
confidence evidence, backup story, and protection coverage recorded for that
point in time. The contract is defined in
`contracts/v1/history.schema.json`.

The Docker adapter builds confidence and story snapshots from each source
history record. It attaches current coverage to the newest run because that
coverage is measured during the same API generation. Older source records do
not contain retention counts, so their snapshot coverage is explicitly `null`
instead of borrowing the current value.

## Validation

Run the dependency-free repository validation with:

```powershell
python scripts/validate.py
python scripts/validate-json-schema.py contracts/v1/infrastructure.schema.json api/bootstrap/v1/infrastructure.json
node --check ui/experience/app.js
```

On the Linux deployment host, also run:

```bash
./scripts/validate-api-refresh.sh
mkdir -p state/.api-build
./plugins/docker/generate-inventory.sh state/.api-build/inventory-validation.json
jq -e '.inventory_status == "generated" and (.components | length) > 0' state/.api-build/inventory-validation.json
git status --short
```

The standalone inventory command must run as the deployment user on Linux. On
`dockerhost`, inspect `host`, `components`, `systemd_units`, and `identities` in
the resulting JSON; confirm missing tools are explicit, no credential content is
present, and the final Git status is empty. Then run the normal API refresh and
open the Inventory resource in the Reference Center before marking the PR ready.

The repository validator checks JSON parsing, internal resources, startup
sequence markup, archive interaction hooks, historical snapshots, the curated
prerequisite structure, safe inventory fields, inventory publication, semantic
Today at a Glance color coupling, and the required first-party documentation
set. It also confirms that every Confidence Ring export value has exactly one
mapping, that the generated CSS is current, and that both approved ring assets
retain their frozen hashes.
JavaScript syntax is checked directly by the browser-compatible Node parser
without adding a project dependency.

## Architecture

Harbr is divided into four layers:

1. **Core**
   - Converts implementation-specific backup facts into Harbr concepts.
   - Calculates Restore Confidence.
   - Produces versioned, sanitized data.

2. **API**
   - Publishes read-only JSON documents.
   - Is consumed by the web interface, PWA, and future native mobile apps.

3. **UI**
   - Presents the Harbr experience.
   - Does not inspect Docker, systemd, rclone, backup archives, or host files.

4. **Plugins**
   - Adapt implementation-specific systems to Harbr.
   - The first plugin is the Docker backup implementation.

## Product vocabulary

- Confidence Ring
- Restore Confidence
- Confidence History
- Backup Story
- Protection Coverage
- Reference Center
- Seasons

## Security

Harbr publishes sanitized operational status only.

It must never publish:

- credentials;
- tokens;
- webhook identifiers;
- internal IP addresses;
- environment variables;
- raw logs;
- archive downloads;
- local backup paths;
- recovery secrets;
- complete environment-variable dumps;
- unrelated host users or groups.

## Current site

- Site ID: `LDF`
- Name: Lac du Flambeau
- Edition: Founder's Edition
