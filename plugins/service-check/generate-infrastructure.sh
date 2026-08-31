#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

HARBR_ROOT="${HARBR_ROOT:-/srv/docker/harbr}"
SERVICE_CHECK_SOURCE="${SERVICE_CHECK_SOURCE:-/var/lib/service-check/status.json}"
INFRASTRUCTURE_OUTPUT="${1:-${HARBR_ROOT}/api/v1/infrastructure.json}"
TMP_ROOT="${HARBR_ROOT}/state/.api-build"
STALE_AFTER_SECONDS="${STALE_AFTER_SECONDS:-300}"

if (( EUID == 0 )); then
  echo "Refusing to publish Harbr Infrastructure as root." >&2
  exit 1
fi

for command in jq mktemp install mv rm dirname; do
  command -v "$command" >/dev/null 2>&1 || { echo "Required command missing: $command" >&2; exit 1; }
done

[[ -r "$SERVICE_CHECK_SOURCE" ]] || {
  echo "service-check record is not readable by $(id -un): $SERVICE_CHECK_SOURCE" >&2
  exit 1
}
jq -e 'type == "object"' "$SERVICE_CHECK_SOURCE" >/dev/null
[[ "$STALE_AFTER_SECONDS" =~ ^[0-9]+$ ]] && (( STALE_AFTER_SECONDS >= 30 )) || {
  echo "STALE_AFTER_SECONDS must be an integer of at least 30." >&2
  exit 1
}

mkdir -p "$TMP_ROOT" "$(dirname "$INFRASTRUCTURE_OUTPUT")"
[[ -w "$TMP_ROOT" && -w "$(dirname "$INFRASTRUCTURE_OUTPUT")" ]] || {
  echo "Harbr build and API directories must be writable by $(id -un)." >&2
  exit 1
}

build_dir="$(mktemp -d "$TMP_ROOT/infrastructure.XXXXXX")"
chmod 0700 "$build_dir"
cleanup() { rm -rf -- "$build_dir"; }
trap cleanup EXIT
candidate="$build_dir/infrastructure.json"

# This is an allow-list transformation: private collector fields that are not
# explicitly selected below (including digests, paths, addresses, and secrets)
# cannot cross the public API boundary.
jq --argjson stale "$STALE_AFTER_SECONDS" '
  def sem: if . == "healthy" then "healthy" elif . == "warning" then "warning" elif . == "failure" then "failure" else "unknown" end;
  def upd: if . == "current" then "current" elif . == "update_available" then "update_available" else "unknown" end;
  def safe_string: if type == "string" and length > 0 then . else null end;
  def service:
    { service_id: (.service_id // .id // .name), name: (.display_name // .name // .service_id // .id),
      container_name: ((.container_name // null) | safe_string),
      status: ((.status // .runtime_status // "unknown") | sem),
      runtime_status: ((.runtime_status // .status // "unknown") | sem),
      health_status: ((.health_status // .docker_health // "unknown") | sem),
      image: ((.image.reference? // .image_reference // (if (.image | type) == "string" then .image else null end)) | safe_string),
      update_status: ((.image.update_status? // .update_status // .image_update_status // "unknown") | upd),
      software_version: ((.software_version // .version // null) | safe_string) };
  def project:
    { project_id: (.project_id // .id // .name), name: (.display_name // .name // .project_id // .id),
      status: ((.status // "unknown") | sem), services: [(.services // .containers // [])[] | service] };
  def docker:
    if . == null then null else
    { status: ((.status // .daemon_status // "unknown") | sem), daemon_status: ((.daemon_status // .status // "unknown") | sem),
      server_version: ((.server_version // .version // null) | safe_string), compose_version: ((.compose_version // null) | safe_string),
      projects: [(.projects // .compose_projects // [])[] | project] } end;
  def os: if . == null then null else {name: ((.name // .id // null) | safe_string), version: ((.version // .version_id // null) | safe_string), pretty_name: ((.pretty_name // null) | safe_string)} end;
  def vm:
    { vm_id: (.vm_id // .id // .name), name: (.display_name // .name // .vm_id // .id), status: ((.status // "unknown") | sem),
      runtime_status: ((.runtime_status // .status // "unknown") | sem), os: ((.os // null) | os),
      uptime_seconds: (if (.uptime_seconds | type) == "number" then .uptime_seconds else null end),
      reboot_required: (if (.reboot_required | type) == "boolean" then .reboot_required else null end),
      update_status: ((.update_status // "unknown") | upd), services: [(.services // [])[] | service], docker: ((.docker // null) | docker) };
  def host:
    { host_id: (.host_id // .id // .name), name: (.display_name // .name // .host_id // .id), role: (.role // .host_type // "appliance"),
      status: ((.status // "unknown") | sem), platform: ((.platform // null) | safe_string), model: ((.model // null) | safe_string),
      software_version: ((.software_version // null) | safe_string), uptime_seconds: (if (.uptime_seconds | type) == "number" then .uptime_seconds else null end),
      os: ((.os // null) | os), reboot_required: (if (.reboot_required | type) == "boolean" then .reboot_required else null end),
      systemd: (if .systemd == null then null else {status: ((.systemd.status // "unknown") | sem), failed_units: (.systemd.failed_units // .systemd.failed_count // 0)} end),
      package_updates: (if .package_updates == null then null else (.package_updates.metadata_status // "unknown") as $metadata | {status: ((.package_updates.status // "unknown") | sem), available: (.package_updates.available // .package_updates.total // 0), security: (.package_updates.security // 0), metadata_status: (if $metadata == "fresh" or $metadata == "stale" then $metadata else "unknown" end)} end),
      filesystems: [(.filesystems // [])[] | {filesystem_id: (.filesystem_id // .id // .label), label: (.label // .name // .filesystem_id // .id), status: ((.status // "unknown") | sem), used_percent: (if (.used_percent | type) == "number" then .used_percent else null end)}],
      docker: ((.docker // null) | docker), virtualization: (if .virtualization == null then null else {status: ((.virtualization.status // "unknown") | sem), virtual_machines: [(.virtualization.virtual_machines // .virtualization.vms // [])[] | vm]} end),
      services: [(.services // [])[] | service] };
  def sites_source: if (.sites | type) == "array" then .sites elif .site then [.site] elif .host then [{site_id:(.site_id // "unknown"), name:(.site_name // .site_id // "Unknown site"), status:(.status // .host.status // "unknown"), hosts:[.host]}] else [] end;
  { api_version: "v1", generated_at: (.generated_at // .checked_at // null), stale_after_seconds: $stale,
    status: ((.status // "unknown") | sem), summary: {},
    sites: [sites_source[] | {site_id:(.site_id // .id // .name), name:(.display_name // .name // .site_id // .id), status:((.status // "unknown") | sem), hosts:[(.hosts // [])[] | host]}] }
  | .summary = {
      sites:(.sites|length), hosts:([.sites[].hosts[]]|length),
      services:([.sites[].hosts[] | ((.docker.projects[]?.services[]?), (.services[]?), (.virtualization.virtual_machines[]?.services[]?), (.virtualization.virtual_machines[]?.docker.projects[]?.services[]?))]|length),
      healthy_services:([.sites[].hosts[] | ((.docker.projects[]?.services[]?), (.services[]?), (.virtualization.virtual_machines[]?.services[]?), (.virtualization.virtual_machines[]?.docker.projects[]?.services[]?)) | select(.runtime_status=="healthy")]|length),
      warning_services:([.sites[].hosts[] | ((.docker.projects[]?.services[]?), (.services[]?), (.virtualization.virtual_machines[]?.services[]?), (.virtualization.virtual_machines[]?.docker.projects[]?.services[]?)) | select(.runtime_status=="warning")]|length),
      failed_services:([.sites[].hosts[] | ((.docker.projects[]?.services[]?), (.services[]?), (.virtualization.virtual_machines[]?.services[]?), (.virtualization.virtual_machines[]?.docker.projects[]?.services[]?)) | select(.runtime_status=="failure")]|length),
      image_updates:([.sites[].hosts[] | ((.docker.projects[]?.services[]?), (.virtualization.virtual_machines[]?.docker.projects[]?.services[]?)) | select(.update_status=="update_available")]|length),
      package_updates:([.sites[].hosts[].package_updates.available // 0]|add // 0), security_updates:([.sites[].hosts[].package_updates.security // 0]|add // 0),
      reboots_required:([.sites[].hosts[] | select(.reboot_required==true)]|length) }
' "$SERVICE_CHECK_SOURCE" > "$candidate"

# Validate the normalized contract before publication. The repository validator
# additionally checks this fixture against the JSON Schema when jsonschema is available.
jq -e '
  .api_version == "v1" and (.stale_after_seconds >= 30) and
  ([.status, .sites[].status, .sites[].hosts[].status] | all(. == "healthy" or . == "warning" or . == "failure" or . == "unknown")) and
  ([.sites[].site_id, .sites[].hosts[].host_id] | all(type == "string" and length > 0)) and
  ([.sites[].hosts[].docker?.projects[]?.services[]?.update_status] | all(. == "current" or . == "update_available" or . == "unknown"))
' "$candidate" >/dev/null

publish_temp="$(dirname "$INFRASTRUCTURE_OUTPUT")/.infrastructure.json.publish.$$"
install -m 0644 "$candidate" "$publish_temp"
mv -f "$publish_temp" "$INFRASTRUCTURE_OUTPUT"
echo "Harbr Infrastructure published from the service-check record."
