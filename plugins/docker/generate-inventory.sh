#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

HARBR_ROOT="${HARBR_ROOT:-/srv/docker/harbr}"
PREREQUISITES_CONFIG="${PREREQUISITES_CONFIG:-${HARBR_ROOT}/state/recovery/prerequisites.json}"
SITE_CONFIG="${SITE_CONFIG:-${HARBR_ROOT}/state/sites/LDF.json}"
OUTPUT="${1:-${HARBR_ROOT}/api/v1/inventory.json}"

if (( EUID == 0 )); then
  echo "Refusing to generate Harbr inventory as root. Run as the deployment user." >&2
  exit 1
fi

for required_command in jq date mktemp dirname mv rm; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "Required inventory command missing: $required_command" >&2
    exit 1
  }
done

for source_file in "$PREREQUISITES_CONFIG" "$SITE_CONFIG"; do
  [[ -r "$source_file" ]] || {
    echo "Inventory source is not readable: $source_file" >&2
    exit 1
  }
  jq empty "$source_file"
done

output_dir="$(dirname "$OUTPUT")"
[[ -d "$output_dir" && -w "$output_dir" ]] || {
  echo "Inventory output directory is not writable: $output_dir" >&2
  exit 1
}

work_dir="$(mktemp -d "$output_dir/.inventory.XXXXXX")"
cleanup() {
  rm -rf -- "$work_dir"
}
trap cleanup EXIT

components_file="$work_dir/components.jsonl"
units_file="$work_dir/units.jsonl"
: > "$components_file"
: > "$units_file"

first_line() {
  "$@" 2>/dev/null | head -n 1 || true
}

os_value() {
  local key="$1"
  if [[ ! -r /etc/os-release ]] || ! command -v awk >/dev/null 2>&1; then
    return 0
  fi
  awk -F= -v key="$key" '$1 == key { value = substr($0, index($0, "=") + 1); gsub(/^"|"$/, "", value); print value; exit }' /etc/os-release
}

component_version() {
  local component_id="$1"
  case "$component_id" in
    debian-base) os_value VERSION_ID ;;
    bash) first_line bash --version ;;
    coreutils) first_line stat --version ;;
    findutils) first_line find --version ;;
    ca-certificates) ;;
    curl) first_line curl --version ;;
    gpg) first_line gpg --version ;;
    docker-engine) first_line docker --version ;;
    docker-compose) first_line docker compose version ;;
    git) first_line git --version ;;
    github-cli) first_line gh --version ;;
    rclone) first_line rclone version ;;
    jq) first_line jq --version ;;
    sed) first_line sed --version ;;
    tar) first_line tar --version ;;
    gzip) first_line gzip --version ;;
    xz-utils) first_line xz --version ;;
    acl) first_line setfacl --version ;;
    systemd) first_line systemctl --version ;;
  esac
}

while IFS= read -r definition; do
  component_id="$(jq -r '.id' <<< "$definition")"
  package_name="$(jq -r '.package // empty' <<< "$definition")"
  command_name="$(jq -r '.command // empty' <<< "$definition")"
  package_status="not-applicable"
  package_version=""

  if [[ -n "$package_name" ]]; then
    if command -v dpkg-query >/dev/null 2>&1; then
      package_result="$(dpkg-query -W -f='${db:Status-Abbrev}\t${Version}' "$package_name" 2>/dev/null || true)"
      if [[ "$package_result" == ii* ]]; then
        package_status="installed"
        package_version="${package_result#*$'\t'}"
      else
        package_status="missing"
      fi
    else
      package_status="unavailable"
    fi
  fi

  command_status="unavailable"
  if [[ -n "$command_name" ]]; then
    if command -v "$command_name" >/dev/null 2>&1; then
      command_status="available"
    else
      command_status="missing"
    fi
  elif [[ "$package_status" == "installed" ]]; then
    command_status="available"
  elif [[ "$package_status" == "missing" ]]; then
    command_status="missing"
  fi

  detected_version=""
  if [[ "$command_status" == "available" ]]; then
    detected_version="$(component_version "$component_id")"
    if [[ "$component_id" == "docker-compose" && -z "$detected_version" ]]; then
      command_status="missing"
    fi
  fi

  jq -nc \
    --argjson definition "$definition" \
    --arg status "$command_status" \
    --arg version "$detected_version" \
    --arg package_status "$package_status" \
    --arg package_version "$package_version" \
    '$definition + {
      detected: {
        status: $status,
        version: (if $version == "" then null else $version end),
        package_status: $package_status,
        package_version: (if $package_version == "" then null else $package_version end)
      }
    }' >> "$components_file"
done < <(jq -c '.components[]' "$PREREQUISITES_CONFIG")

for unit_name in docker.service docker-backup.service docker-backup.timer harbr-api-refresh.service; do
  inspection_status="unavailable"
  load_state=""
  active_state=""
  unit_file_state=""
  if command -v systemctl >/dev/null 2>&1; then
    load_state="$(systemctl show "$unit_name" --property=LoadState --value 2>/dev/null || true)"
    active_state="$(systemctl show "$unit_name" --property=ActiveState --value 2>/dev/null || true)"
    unit_file_state="$(systemctl show "$unit_name" --property=UnitFileState --value 2>/dev/null || true)"
    if [[ -n "$load_state" || -n "$active_state" || -n "$unit_file_state" ]]; then
      inspection_status="available"
    fi
  fi
  jq -nc \
    --arg name "$unit_name" \
    --arg inspection_status "$inspection_status" \
    --arg load_state "$load_state" \
    --arg active_state "$active_state" \
    --arg unit_file_state "$unit_file_state" \
    '{
      name: $name,
      inspection_status: $inspection_status,
      load_state: (if $load_state == "" then null else $load_state end),
      active_state: (if $active_state == "" then null else $active_state end),
      unit_file_state: (if $unit_file_state == "" then null else $unit_file_state end)
    }' >> "$units_file"
done

deployment_user=""
deployment_group=""
harbr_api_member="false"
if command -v id >/dev/null 2>&1; then
  deployment_user="$(id -un 2>/dev/null || true)"
  deployment_group="$(id -gn 2>/dev/null || true)"
  if id -nG 2>/dev/null | tr ' ' '\n' | grep -qx 'harbr-api'; then
    harbr_api_member="true"
  fi
fi

harbr_group_exists="null"
if command -v getent >/dev/null 2>&1; then
  if getent group harbr-api >/dev/null 2>&1; then
    harbr_group_exists="true"
  else
    harbr_group_exists="false"
  fi
fi

debian_release="$(os_value PRETTY_NAME)"
debian_version_id="$(os_value VERSION_ID)"
kernel_version="$(command -v uname >/dev/null 2>&1 && uname -r 2>/dev/null || true)"
architecture="$(command -v uname >/dev/null 2>&1 && uname -m 2>/dev/null || true)"
site_id="$(jq -r '.site_id' "$SITE_CONFIG")"
site_name="$(jq -r '.site_name' "$SITE_CONFIG")"

output_temp="$work_dir/inventory.json"
jq -n \
  --arg site_id "$site_id" \
  --arg site_name "$site_name" \
  --arg generated_at "$(date --iso-8601=seconds)" \
  --arg debian_release "$debian_release" \
  --arg debian_version_id "$debian_version_id" \
  --arg kernel_version "$kernel_version" \
  --arg architecture "$architecture" \
  --slurpfile components "$components_file" \
  --slurpfile units "$units_file" \
  --arg deployment_user "$deployment_user" \
  --arg deployment_group "$deployment_group" \
  --argjson harbr_api_member "$harbr_api_member" \
  --argjson harbr_group_exists "$harbr_group_exists" \
  '{
    api_version: "v1",
    site_id: $site_id,
    inventory_status: "generated",
    generated_at: $generated_at,
    host: {
      site_name: $site_name,
      debian_release: (if $debian_release == "" then null else $debian_release end),
      debian_version_id: (if $debian_version_id == "" then null else $debian_version_id end),
      kernel_version: (if $kernel_version == "" then null else $kernel_version end),
      architecture: (if $architecture == "" then null else $architecture end)
    },
    components: $components,
    systemd_units: $units,
    identities: {
      deployment_user: (
        if $deployment_user == "" then null
        else {name: $deployment_user, primary_group: $deployment_group, member_of_harbr_api: $harbr_api_member}
        end
      ),
      harbr_api_group: {name: "harbr-api", exists: $harbr_group_exists}
    }
  }' > "$output_temp"

jq empty "$output_temp"
mv -f "$output_temp" "$OUTPUT"
echo "Harbr host inventory generated: $OUTPUT"
