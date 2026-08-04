#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SOURCE_CONFIG="${SOURCE_CONFIG:-/root/.config/rclone/rclone.conf}"
DEST_CONFIG="${DEST_CONFIG:-/var/lib/harbr/rclone/rclone.conf}"
REMOTE_NAME="${REMOTE_NAME:-OneDrive}"
DEPLOY_USER="${DEPLOY_USER:-chris}"
DEPLOY_GROUP="${DEPLOY_GROUP:-chris}"

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

getent passwd "$DEPLOY_USER" >/dev/null || {
  echo "Deployment user does not exist: $DEPLOY_USER" >&2
  exit 1
}

getent group "$DEPLOY_GROUP" >/dev/null || {
  echo "Deployment group does not exist: $DEPLOY_GROUP" >&2
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
install -d -o "$DEPLOY_USER" -g "$DEPLOY_GROUP" -m 0700 "$destination_dir"
install -o "$DEPLOY_USER" -g "$DEPLOY_GROUP" -m 0600 "$temp_config" "$DEST_CONFIG"

echo "Installed dedicated Harbr rclone remote: $REMOTE_NAME"
echo "Configuration: $DEST_CONFIG"
