#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SOURCE_CONFIG="${SOURCE_CONFIG:-/root/.config/rclone/rclone.conf}"
DEST_CONFIG="${DEST_CONFIG:-/etc/harbr/rclone.conf}"
REMOTE_NAME="${REMOTE_NAME:-OneDrive}"
ACCESS_GROUP="${ACCESS_GROUP:-harbr-api}"

if (( EUID != 0 )); then
  echo "Run this installer as root so it can read the source rclone configuration." >&2
  exit 1
fi

for command in awk dirname getent install mktemp rclone; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Required command missing: $command" >&2
    exit 1
  }
done

[[ -r "$SOURCE_CONFIG" ]] || {
  echo "Source rclone configuration is not readable: $SOURCE_CONFIG" >&2
  exit 1
}

getent group "$ACCESS_GROUP" >/dev/null || {
  echo "Required access group does not exist: $ACCESS_GROUP" >&2
  exit 1
}

temp_config="$(mktemp)"
cleanup() {
  rm -f -- "$temp_config"
}
trap cleanup EXIT

awk -v remote="$REMOTE_NAME" '
  $0 == "[" remote "]" { found = 1; print; next }
  found && /^\[/ { exit }
  found { print }
  END { if (!found) exit 1 }
' "$SOURCE_CONFIG" > "$temp_config" || {
  echo "Rclone remote not found: $REMOTE_NAME" >&2
  exit 1
}

mapfile -t remotes < <(rclone --config "$temp_config" listremotes)
if (( ${#remotes[@]} != 1 )) || [[ "${remotes[0]}" != "$REMOTE_NAME:" ]]; then
  echo "Extracted configuration must contain only the $REMOTE_NAME remote." >&2
  exit 1
fi

destination_dir="$(dirname "$DEST_CONFIG")"
install -d -o root -g "$ACCESS_GROUP" -m 0750 "$destination_dir"
install -o root -g "$ACCESS_GROUP" -m 0640 "$temp_config" "$DEST_CONFIG"

echo "Installed dedicated Harbr rclone remote: $REMOTE_NAME"
echo "Configuration: $DEST_CONFIG"
