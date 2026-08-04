#!/usr/bin/env bash
set -Eeuo pipefail

required_commands=(setfacl awk find getent install jq mktemp rclone stat systemctl)

for command in "${required_commands[@]}"; do
  if ! command -v "$command" >/dev/null 2>&1; then
    if [[ "$command" == "setfacl" ]]; then
      echo "Missing required command: setfacl. Install the acl package before continuing." >&2
    else
      echo "Missing required command: $command" >&2
    fi
    exit 1
  fi
done

echo "Harbr refresh host prerequisites are available."
