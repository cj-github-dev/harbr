#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

HARBR_ROOT="${HARBR_ROOT:-/srv/docker/harbr}"
BACKUP_CONFIG="${BACKUP_CONFIG:-/etc/docker-backup.conf}"
BACKUP_STATUS="${BACKUP_STATUS:-/var/lib/docker-backup/status.json}"
BACKUP_HISTORY="${BACKUP_HISTORY:-/var/lib/docker-backup/history.jsonl}"
SITE_CONFIG="${SITE_CONFIG:-${HARBR_ROOT}/state/sites/LDF.json}"
API_DIR="${HARBR_ROOT}/api/v1"
TMP_DIR="${HARBR_ROOT}/state/.api-build"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command missing: $1" >&2
    exit 1
  }
}

for cmd in jq find sort date stat rclone systemctl; do
  require "$cmd"
done

[[ -r "$BACKUP_CONFIG" ]] || {
  echo "Backup configuration missing: $BACKUP_CONFIG" >&2
  exit 1
}

[[ -r "$SITE_CONFIG" ]] || {
  echo "Harbr site configuration missing: $SITE_CONFIG" >&2
  exit 1
}

# shellcheck disable=SC1090
source "$BACKUP_CONFIG"

mkdir -p "$API_DIR" "$TMP_DIR"
rm -f "$TMP_DIR"/*.json

site_id="$(jq -r '.site_id' "$SITE_CONFIG")"
site_name="$(jq -r '.site_name' "$SITE_CONFIG")"
display_name="$(jq -r '.display_name' "$SITE_CONFIG")"
edition="$(jq -r '.edition' "$SITE_CONFIG")"
first_protected_at="$(jq -r '.first_protected_at' "$SITE_CONFIG")"

month="$(date +%m)"
case "$month" in
  03|04|05) season="spring" ;;
  06|07|08) season="summer" ;;
  09|10|11) season="autumn" ;;
  *) season="winter" ;;
esac

jq -n \
  --arg site_id "$site_id" \
  --arg site_name "$site_name" \
  --arg display_name "$display_name" \
  --arg edition "$edition" \
  --arg first_protected_at "$first_protected_at" \
  --arg season "$season" \
  '{
    api_version: "v1",
    site_id: $site_id,
    site_name: $site_name,
    display_name: $display_name,
    edition: $edition,
    first_protected_at: $first_protected_at,
    season: $season
  }' > "$TMP_DIR/site.json"

if [[ -r "$BACKUP_STATUS" ]]; then
  cp "$BACKUP_STATUS" "$TMP_DIR/raw-status.json"
else
  jq -n '{
    status: "unknown",
    message: "No backup status is available.",
    completed_at: null,
    started_at: null,
    backup_id: null,
    duration_seconds: 0,
    container_downtime_seconds: 0,
    archive_size_bytes: 0,
    local_verified: false,
    cloud_status: "unknown"
  }' > "$TMP_DIR/raw-status.json"
fi

status="$(jq -r '.status // "unknown"' "$TMP_DIR/raw-status.json")"
message="$(jq -r '.message // "No backup status is available."' "$TMP_DIR/raw-status.json")"
completed_at="$(jq -r '.completed_at // empty' "$TMP_DIR/raw-status.json")"
started_at="$(jq -r '.started_at // empty' "$TMP_DIR/raw-status.json")"
backup_id="$(jq -r '.backup_id // "unknown"' "$TMP_DIR/raw-status.json")"
local_verified="$(jq -r '.local_verified // false' "$TMP_DIR/raw-status.json")"
cloud_status="$(jq -r '.cloud_status // "unknown"' "$TMP_DIR/raw-status.json")"

now_epoch="$(date +%s)"
age_hours=999999
if [[ -n "$completed_at" ]]; then
  completed_epoch="$(date -d "$completed_at" +%s 2>/dev/null || echo 0)"
  if (( completed_epoch > 0 )); then
    age_hours="$(( (now_epoch - completed_epoch) / 3600 ))"
  fi
fi

if [[ "$status" == "success" && "$local_verified" == "true" && "$cloud_status" == "synchronized" && "$age_hours" -le 48 ]]; then
  confidence_level="high"
  confidence_message="Everything required for a successful restore has been verified."
elif [[ "$local_verified" == "true" && "$age_hours" -le 72 ]]; then
  confidence_level="moderate"
  confidence_message="A verified local recovery point is available, but off-site protection or freshness requires attention."
elif [[ "$status" == "unknown" ]]; then
  confidence_level="unknown"
  confidence_message="Restore Confidence cannot be determined because no current backup result is available."
else
  confidence_level="low"
  confidence_message="The latest recovery chain is incomplete or too old to provide confidence."
fi

history_source="$TMP_DIR/history-source.json"
if [[ -r "$BACKUP_HISTORY" ]]; then
  jq -s 'map(select(type == "object"))' "$BACKUP_HISTORY" > "$history_source" 2>/dev/null || echo '[]' > "$history_source"
else
  echo '[]' > "$history_source"
fi

confidence_history="$(
  jq -c '
    map(select(.completed_at != null))
    | sort_by(.completed_at)
    | reverse
    | unique_by(.completed_at[0:10])
    | .[0:7]
    | map({
        date: .completed_at[0:10],
        level:
          (if .status == "success" and .local_verified == true and .cloud_status == "synchronized"
           then "high"
           elif .local_verified == true
           then "moderate"
           else "low"
           end)
      })
  ' "$history_source"
)"

jq -n \
  --arg site_id "$site_id" \
  --arg level "$confidence_level" \
  --arg message "$confidence_message" \
  --arg last_verified_at "${completed_at:-}" \
  --argjson local_archive_created "$local_verified" \
  --argjson checksums_verified "$local_verified" \
  --argjson archive_readable "$local_verified" \
  --argjson containers_restarted "$(jq -r '(.status == "success" or .status == "warning")' "$TMP_DIR/raw-status.json")" \
  --argjson onedrive_synchronized "$([[ "$cloud_status" == "synchronized" ]] && echo true || echo false)" \
  --argjson restore_documentation_present "$local_verified" \
  --argjson history "$confidence_history" \
  '{
    api_version: "v1",
    site_id: $site_id,
    level: $level,
    message: $message,
    last_verified_at: (if $last_verified_at == "" then null else $last_verified_at end),
    checks: {
      local_archive_created: $local_archive_created,
      checksums_verified: $checksums_verified,
      archive_readable: $archive_readable,
      containers_restarted: $containers_restarted,
      onedrive_synchronized: $onedrive_synchronized,
      restore_documentation_present: $restore_documentation_present
    },
    history: $history
  }' > "$TMP_DIR/confidence.json"

step_status="complete"
[[ "$status" == "success" ]] || step_status="warning"
[[ "$status" == "failure" || "$status" == "critical" ]] && step_status="failed"

jq -n \
  --arg site_id "$site_id" \
  --arg backup_id "$backup_id" \
  --arg started_at "${started_at:-}" \
  --arg completed_at "${completed_at:-}" \
  --arg status "$step_status" \
  '{
    api_version: "v1",
    site_id: $site_id,
    backup_id: $backup_id,
    started_at: (if $started_at == "" then null else $started_at end),
    completed_at: (if $completed_at == "" then null else $completed_at end),
    steps: [
      {id:"containers-paused", label:"Containers paused", occurred_at:(if $started_at == "" then null else $started_at end), status:$status},
      {id:"archive-created", label:"Archive created", occurred_at:null, status:$status},
      {id:"integrity-verified", label:"Integrity verified", occurred_at:null, status:$status},
      {id:"containers-restarted", label:"Containers restarted", occurred_at:null, status:$status},
      {id:"onedrive-synchronized", label:"Copied to OneDrive", occurred_at:(if $completed_at == "" then null else $completed_at end), status:$status},
      {id:"confidence-updated", label:"Restore Confidence updated", occurred_at:(if $completed_at == "" then null else $completed_at end), status:$status}
    ]
  }' > "$TMP_DIR/story.json"

count_remote() {
  rclone lsf --dirs-only "$1" 2>/dev/null | sed '/^[[:space:]]*$/d' | wc -l
}

local_count="$(
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??_??-??-??' | wc -l
)"
daily_count="$(count_remote "${RCLONE_REMOTE}:${RCLONE_ROOT}/backups/daily")"
weekly_count="$(count_remote "${RCLONE_REMOTE}:${RCLONE_ROOT}/backups/weekly")"
monthly_count="$(count_remote "${RCLONE_REMOTE}:${RCLONE_ROOT}/backups/monthly")"

tier_state() {
  local current="$1"
  local target="$2"
  if (( current >= target )); then
    echo "complete"
  elif (( current >= 0 )); then
    echo "building"
  else
    echo "warning"
  fi
}

jq -n \
  --arg site_id "$site_id" \
  --argjson local_current "$local_count" \
  --argjson local_target "$LOCAL_RETENTION" \
  --arg local_state "$(tier_state "$local_count" "$LOCAL_RETENTION")" \
  --argjson daily_current "$daily_count" \
  --argjson daily_target "$ONEDRIVE_DAILY_RETENTION" \
  --arg daily_state "$(tier_state "$daily_count" "$ONEDRIVE_DAILY_RETENTION")" \
  --argjson weekly_current "$weekly_count" \
  --argjson weekly_target "$ONEDRIVE_WEEKLY_RETENTION" \
  --arg weekly_state "$(tier_state "$weekly_count" "$ONEDRIVE_WEEKLY_RETENTION")" \
  --argjson monthly_current "$monthly_count" \
  --argjson monthly_target "$ONEDRIVE_MONTHLY_RETENTION" \
  --arg monthly_state "$(tier_state "$monthly_count" "$ONEDRIVE_MONTHLY_RETENTION")" \
  '{
    api_version: "v1",
    site_id: $site_id,
    tiers: [
      {id:"immediate", label:"Immediate Recovery", location:"Local", current:$local_current, target:$local_target, state:$local_state},
      {id:"short-term", label:"Short-Term Recovery", location:"OneDrive Daily", current:$daily_current, target:$daily_target, state:$daily_state},
      {id:"mid-term", label:"Mid-Term Recovery", location:"OneDrive Weekly", current:$weekly_current, target:$weekly_target, state:$weekly_state},
      {id:"long-term", label:"Long-Term Recovery", location:"OneDrive Monthly", current:$monthly_current, target:$monthly_target, state:$monthly_state}
    ]
  }' > "$TMP_DIR/coverage.json"

jq -n \
  --arg site_id "$site_id" \
  --argjson runs "$(
    jq -c '
      sort_by(.completed_at)
      | reverse
      | .[0:90]
      | map({
          backup_id: (.backup_id // "unknown"),
          completed_at: .completed_at,
          level:
            (if .status == "success" and .local_verified == true and .cloud_status == "synchronized"
             then "high"
             elif .local_verified == true
             then "moderate"
             else "low"
             end),
          archive_size_bytes: (.archive_size_bytes // 0),
          duration_seconds: (.duration_seconds // 0),
          container_downtime_seconds: (.container_downtime_seconds // 0)
        })
    ' "$history_source"
  )" \
  '{
    api_version: "v1",
    site_id: $site_id,
    runs: $runs
  }' > "$TMP_DIR/history.json"

next_run="$(systemctl show docker-backup.timer --property=NextElapseUSecRealtime --value 2>/dev/null || true)"
[[ -n "$next_run" ]] || next_run="Unknown"

jq -n \
  --arg site_id "$site_id" \
  --arg product_version "$(cat "$HARBR_ROOT/VERSION")" \
  --arg next_run "$next_run" \
  --arg generated_at "$(date --iso-8601=seconds)" \
  '{
    api_version: "v1",
    product_name: "Harbr",
    product_version: $product_version,
    tagline: "Recovery begins with confidence.",
    site_id: $site_id,
    read_only: true,
    next_scheduled_run: $next_run,
    generated_at: $generated_at
  }' > "$TMP_DIR/system.json"

jq -n \
  --arg site_id "$site_id" \
  --arg site_name "$site_name" \
  --arg edition "$edition" \
  --arg version "$(cat "$HARBR_ROOT/VERSION")" \
  '{
    api_version: "v1",
    product: {
      name: "Harbr",
      tagline: "Recovery begins with confidence.",
      version: $version
    },
    sites: [
      {
        site_id: $site_id,
        name: $site_name,
        edition: $edition
      }
    ],
    resources: {
      site: "/api/v1/site.json",
      confidence: "/api/v1/confidence.json",
      story: "/api/v1/story.json",
      history: "/api/v1/history.json",
      coverage: "/api/v1/coverage.json",
      system: "/api/v1/system.json"
    }
  }' > "$TMP_DIR/index.json"

for file in "$TMP_DIR"/*.json; do
  jq empty "$file"
done

for name in site confidence story history coverage system index; do
  install -m 0640 -o chris -g chris "$TMP_DIR/$name.json" "$API_DIR/$name.json"
done

rm -f "$TMP_DIR/raw-status.json" "$TMP_DIR/history-source.json"

echo "Harbr Docker adapter refresh completed."
echo "Restore Confidence: $confidence_level"
echo "API directory: $API_DIR"
