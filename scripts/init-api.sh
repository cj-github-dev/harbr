#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

HARBR_ROOT="${HARBR_ROOT:-/srv/docker/harbr}"
BOOTSTRAP_DIR="${HARBR_ROOT}/api/bootstrap/v1"
API_DIR="${HARBR_ROOT}/api/v1"

if (( EUID == 0 )); then
  echo "Refusing to initialize Harbr API as root. Run as the deployment user." >&2
  exit 1
fi

for command in jq install mv basename; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Required command missing: $command" >&2
    exit 1
  }
done

[[ -d "$BOOTSTRAP_DIR" ]] || {
  echo "Bootstrap API directory missing: $BOOTSTRAP_DIR" >&2
  exit 1
}

mkdir -p "$API_DIR"
chmod 0755 "$API_DIR"

for source in "$BOOTSTRAP_DIR"/*.json; do
  name="$(basename "$source")"
  target="$API_DIR/$name"
  [[ -e "$target" ]] && continue
  jq empty "$source"
  temporary="$API_DIR/.$name.init.$$"
  install -m 0644 "$source" "$temporary"
  mv -f "$temporary" "$target"
done

echo "Harbr API initialized from source-controlled bootstrap fixtures."
