#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID == 0 )); then
  echo "Run this validation as the normal Harbr deployment user, not root." >&2
  exit 1
fi

for command in git jq find stat mktemp install ln; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Required command missing: $command" >&2
    exit 1
  }
done

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_PARENT="$(mktemp -d)"
TEST_ROOT="$TEST_PARENT/harbr"
cleanup() {
  rm -rf -- "$TEST_PARENT"
}
trap cleanup EXIT

mkdir -p \
  "$TEST_ROOT/api/bootstrap/v1" \
  "$TEST_ROOT/plugins/docker" \
  "$TEST_ROOT/plugins/service-check" \
  "$TEST_ROOT/scripts/fixtures" \
  "$TEST_ROOT/scripts" \
  "$TEST_ROOT/state/recovery" \
  "$TEST_ROOT/state/sites" \
  "$TEST_ROOT/backups/2026-08-04_10-30-00" \
  "$TEST_ROOT/stubs"

cp "$SOURCE_ROOT/.gitignore" "$SOURCE_ROOT/VERSION" "$TEST_ROOT/"
cp "$SOURCE_ROOT/api/bootstrap/v1/"*.json "$TEST_ROOT/api/bootstrap/v1/"
cp "$SOURCE_ROOT/state/sites/LDF.json" "$TEST_ROOT/state/sites/"
cp "$SOURCE_ROOT/state/recovery/prerequisites.json" "$TEST_ROOT/state/recovery/"
cp "$SOURCE_ROOT/plugins/docker/refresh-api.sh" "$TEST_ROOT/plugins/docker/"
cp "$SOURCE_ROOT/plugins/docker/generate-inventory.sh" "$TEST_ROOT/plugins/docker/"
cp "$SOURCE_ROOT/plugins/service-check/generate-infrastructure.sh" "$TEST_ROOT/plugins/service-check/"
cp "$SOURCE_ROOT/scripts/fixtures/service-check-v0.3.json" "$TEST_ROOT/scripts/fixtures/"
cp "$SOURCE_ROOT/scripts/init-api.sh" "$TEST_ROOT/scripts/"

cat > "$TEST_ROOT/backup.conf" <<'EOF'
BACKUP_ROOT="__BACKUP_ROOT__"
RCLONE_REMOTE="test"
RCLONE_ROOT="harbr"
LOCAL_RETENTION=3
ONEDRIVE_DAILY_RETENTION=7
ONEDRIVE_WEEKLY_RETENTION=4
ONEDRIVE_MONTHLY_RETENTION=12
EOF
sed -i "s|__BACKUP_ROOT__|$TEST_ROOT/backups|" "$TEST_ROOT/backup.conf"

cat > "$TEST_ROOT/status.json" <<'EOF'
{
  "status": "success",
  "message": "Validation backup completed.",
  "completed_at": "2026-08-04T10:32:10-05:00",
  "started_at": "2026-08-04T10:30:00-05:00",
  "backup_id": "2026-08-04_10-30-00",
  "duration_seconds": 130,
  "container_downtime_seconds": 18,
  "archive_size_bytes": 643454624,
  "local_verified": true,
  "cloud_status": "synchronized"
}
EOF

cp "$TEST_ROOT/status.json" "$TEST_ROOT/history.jsonl"

cat > "$TEST_ROOT/stubs/rclone" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$TEST_ROOT/stubs/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "Unknown"
EOF
chmod 0755 "$TEST_ROOT/stubs/rclone" "$TEST_ROOT/stubs/systemctl"

git -C "$TEST_ROOT" init -q
git -C "$TEST_ROOT" config user.name "Harbr Validation"
git -C "$TEST_ROOT" config user.email "validation@harbr.invalid"
git -C "$TEST_ROOT" add .
git -C "$TEST_ROOT" commit -qm "validation fixture"

HARBR_ROOT="$TEST_ROOT" "$TEST_ROOT/scripts/init-api.sh"

run_refresh() {
  PATH="$TEST_ROOT/stubs:$PATH" \
  HARBR_ROOT="$TEST_ROOT" \
  BACKUP_CONFIG="$TEST_ROOT/backup.conf" \
  BACKUP_STATUS="$TEST_ROOT/status.json" \
  BACKUP_HISTORY="$TEST_ROOT/history.jsonl" \
  SITE_CONFIG="$TEST_ROOT/state/sites/LDF.json" \
  "$TEST_ROOT/plugins/docker/refresh-api.sh"
}

run_refresh
run_refresh

jq -e '.resources.inventory == "/api/v1/inventory.json"' "$TEST_ROOT/api/v1/index.json" >/dev/null
jq -e '.resources.infrastructure == "/api/v1/infrastructure.json"' "$TEST_ROOT/api/v1/index.json" >/dev/null
jq -e '.inventory_status == "generated" and (.components | length) > 0' "$TEST_ROOT/api/v1/inventory.json" >/dev/null

minimal_path="$TEST_ROOT/inventory-minimal-path"
mkdir -p "$minimal_path"
for command in bash jq date mktemp dirname mv rm head awk; do
  ln -s "$(command -v "$command")" "$minimal_path/$command"
done
PATH="$minimal_path" \
HARBR_ROOT="$TEST_ROOT" \
PREREQUISITES_CONFIG="$TEST_ROOT/state/recovery/prerequisites.json" \
SITE_CONFIG="$TEST_ROOT/state/sites/LDF.json" \
  "$TEST_ROOT/plugins/docker/generate-inventory.sh" "$TEST_ROOT/minimal-inventory.json"
jq -e '
  .inventory_status == "generated"
  and any(.components[]; .detected.status == "missing" or .detected.status == "unavailable")
' "$TEST_ROOT/minimal-inventory.json" >/dev/null

cp "$TEST_ROOT/scripts/fixtures/service-check-v0.3.json" "$TEST_ROOT/service-check.json"
HARBR_ROOT="$TEST_ROOT" SERVICE_CHECK_SOURCE="$TEST_ROOT/service-check.json" \
  "$TEST_ROOT/plugins/service-check/generate-infrastructure.sh" "$TEST_ROOT/infrastructure-generated.json"
jq -e '
  .status == "warning"
  and (.sites[0] | .site_id == "LDF" and .status == "warning")
  and (.sites[0].hosts[0] | .host_id == "ldf-dockerhost" and .status == "warning"
    and .reboot_required == true and .systemd.status == "healthy" and .systemd.failed_units == 0
    and .package_updates.available == 0 and .package_updates.security == 0)
  and (.summary | .hosts == 1 and .services == 7 and .healthy_services == 7
    and .warning_services == 0 and .failed_services == 0 and .image_updates == 1 and .reboots_required == 1)
  and (.sites[0].hosts[0].docker.projects[] | select(.project_id == "nginx-proxy-manager") | .status == "warning")
  and (.sites[0].hosts[0].docker.projects[].services[] | select(.service_id == "db") |
    .name == "npm-db" and .container_name == "npm-db" and .runtime_status == "healthy" and .health_status == "unknown"
    and .image == "mariadb:10.11" and .update_status == "update_available")
  and (.sites[0].hosts[0].docker.projects[].services[] | select(.service_id == "npm") |
    .name == "nginx-p-m" and .container_name == "nginx-p-m" and .runtime_status == "healthy" and .health_status == "unknown"
    and .image == "jc21/nginx-proxy-manager:latest" and .update_status == "current")
  and (.sites[0].hosts[0].docker.projects[].services[] | select(.service_id == "jellyfin") |
    .container_name == "jellyfin" and .runtime_status == "healthy" and .health_status == "healthy")
  and (.sites[0].hosts[0].docker.projects[].services[] | select(.service_id == "pihole") |
    .container_name == "pihole" and .runtime_status == "healthy" and .health_status == "healthy")
' "$TEST_ROOT/infrastructure-generated.json" >/dev/null
for forbidden in local_digest remote_digest image_id management_ip compose_directory compose_file secret registry_credentials runtime_state health started_at; do
  ! grep -q "\"$forbidden\"" "$TEST_ROOT/infrastructure-generated.json"
done
cp "$TEST_ROOT/infrastructure-generated.json" "$TEST_ROOT/infrastructure-before.json"
if HARBR_ROOT="$TEST_ROOT" SERVICE_CHECK_SOURCE="$TEST_ROOT/missing.json" "$TEST_ROOT/plugins/service-check/generate-infrastructure.sh" "$TEST_ROOT/infrastructure-generated.json"; then
  echo "Infrastructure adapter unexpectedly accepted a missing source" >&2; exit 1
fi
cmp "$TEST_ROOT/infrastructure-before.json" "$TEST_ROOT/infrastructure-generated.json"

for file in "$TEST_ROOT/api/v1/"*.json; do
  jq empty "$file"
  [[ -w "$file" ]] || {
    echo "Generated file is not writable: $file" >&2
    exit 1
  }
  [[ "$(stat -c '%U' "$file")" == "$(id -un)" ]] || {
    echo "Generated file has unexpected owner: $file" >&2
    exit 1
  }
done

[[ -w "$TEST_ROOT/api/v1" && -w "$TEST_ROOT/state/.api-build" ]]
[[ -z "$(git -C "$TEST_ROOT" status --porcelain --untracked-files=no)" ]] || {
  echo "Refresh modified source-controlled files:" >&2
  git -C "$TEST_ROOT" status --short >&2
  exit 1
}

echo "Harbr API refresh validation passed."
