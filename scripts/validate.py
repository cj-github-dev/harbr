#!/usr/bin/env python3
"""Dependency-free structural validation for the Harbr web experience."""

from __future__ import annotations

import json
import hashlib
import runpy
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
API_SOURCE_ROOT = ROOT / "api" / "bootstrap" / "v1"
HTML_PATH = ROOT / "ui" / "experience" / "index.html"
APP_PATH = ROOT / "ui" / "experience" / "app.js"
REFERENCE_PATH = ROOT / "ui" / "experience" / "data" / "reference.json"
RING_CONFIG_PATH = ROOT / "ui" / "experience" / "config" / "confidence-ring.json"
RING_CSS_PATH = ROOT / "ui" / "experience" / "config" / "confidence-ring.generated.css"
REFRESH_UNIT_PATH = ROOT / "deploy" / "systemd" / "harbr-api-refresh.service"
BACKUP_DROP_IN_PATH = ROOT / "deploy" / "systemd" / "docker-backup.service.d" / "harbr-api-refresh.conf"
RCLONE_INSTALLER_PATH = ROOT / "scripts" / "install-rclone-remote.sh"
HOST_PREFLIGHT_PATH = ROOT / "scripts" / "preflight-refresh-host.sh"
PREREQUISITES_PATH = ROOT / "state" / "recovery" / "prerequisites.json"
INVENTORY_GENERATOR_PATH = ROOT / "plugins" / "docker" / "generate-inventory.sh"
INFRASTRUCTURE_GENERATOR_PATH = ROOT / "plugins" / "service-check" / "generate-infrastructure.sh"
INFRASTRUCTURE_SCHEMA_PATH = ROOT / "contracts" / "v1" / "infrastructure.schema.json"
SERVICE_CHECK_V03_FIXTURE_PATH = ROOT / "scripts" / "fixtures" / "service-check-v0.3.json"
APPROVED_RING_HASHES = {
    RING_CONFIG_PATH: "c78248ebd91194730a5e6ae045970de64321508af8c871b0bc79314871e48d5e",
    RING_CSS_PATH: "73fab272f1ab3ce8c4c19208e1fc727a0af25ed23ad616b2f9058e8a79fd0399",
}
REQUIRED_GUIDES = {
    "docker-platform",
    "nginx-proxy-manager",
    "pihole-recovery",
    "jellyfin-recovery",
    "home-assistant-recovery",
    "restore-harbr",
    "restore-guide",
    "verification-chain",
    "backup-retention",
    "offsite-sync",
    "confidence-methodology",
    "host-recovery-prerequisites",
    "blank-debian-bootstrap",
    "host-configuration-dependencies",
}
REQUIRED_RECOVERY_CATEGORIES = {
    "base-operating-system",
    "container-runtime",
    "source-control",
    "offsite-sync",
    "data-processing",
    "network-trust",
    "archive-filesystem",
    "access-control",
    "service-management",
    "administrative-tool",
}


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_json() -> None:
    for path in sorted(API_SOURCE_ROOT.glob("*.json")):
        load_json(path)
    for path in sorted((ROOT / "contracts" / "v1").glob("*.json")):
        load_json(path)
    load_json(REFERENCE_PATH)
    load_json(PREREQUISITES_PATH)
    load_json(SERVICE_CHECK_V03_FIXTURE_PATH)


def validate_internal_resources() -> None:
    index = load_json(API_SOURCE_ROOT / "index.json")
    for name, url in index["resources"].items():
        parsed = urlparse(url)
        require(not parsed.scheme and url.startswith("/api/v1/"), f"{name} is not an internal v1 resource")
        path = API_SOURCE_ROOT / Path(url).name
        require(path.is_file(), f"Missing internal resource: {url}")

    html = HTML_PATH.read_text(encoding="utf-8")
    for resource in ("/config/confidence-ring.generated.css", "/styles.css", "/app.js", "/assets/harbr-mark.svg"):
        require(resource in html, f"Missing HTML resource link: {resource}")
        path = ROOT / "ui" / "experience" / resource.lstrip("/")
        require(path.is_file(), f"Missing UI resource: {resource}")


def validate_confidence_ring_config() -> None:
    config = load_json(RING_CONFIG_PATH)
    require(config.get("schema_version") == 1, "Unsupported Confidence Ring configuration schema")
    require(config.get("approved") is True, "Confidence Ring configuration is not approved")

    generator = runpy.run_path(str(ROOT / "scripts" / "generate-confidence-ring-css.py"))
    mappings = generator["MAPPINGS"]
    values = config.get("values", {})
    require(values.keys() == mappings.keys(), "Confidence Ring values and production mapping have drifted")
    require(generator["render"](config) == RING_CSS_PATH.read_text(encoding="utf-8"), "Generated Confidence Ring CSS is stale")

    styles = (ROOT / "ui" / "experience" / "styles.css").read_text(encoding="utf-8")
    for _, (variable, _) in mappings.items():
        require(f"var({variable})" in styles, f"Production ring does not consume {variable}")
    for path, approved_hash in APPROVED_RING_HASHES.items():
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual_hash == approved_hash, f"Approved Confidence Ring asset changed: {path.name}")


def validate_startup() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    app = APP_PATH.read_text(encoding="utf-8")
    styles = (ROOT / "ui" / "experience" / "styles.css").read_text(encoding="utf-8")
    for marker in ('id="startup-icon"', 'id="startup-wordmark"', 'id="startup-tagline"'):
        require(marker in html, f"Startup markup missing {marker}")
    for marker in ("icon-away", "wordmark-away", "endingStart + 1500"):
        require(marker in app, f"Startup sequence missing {marker}")
    for marker in (
        "animation: intro 900ms var(--ease) backwards",
        "animation: fade 700ms 420ms var(--ease) backwards",
        "animation: fade 700ms 820ms var(--ease) backwards",
        "transition: opacity 650ms var(--ease)",
    ):
        require(marker in styles, f"Startup fade treatment missing {marker}")


def validate_archives() -> None:
    app = APP_PATH.read_text(encoding="utf-8")
    for marker in (
        "button.dataset.backupId",
        "aria-pressed",
        "selectArchive",
        "renderHistoricalView",
        "Viewing archive from",
        "transitionArchiveView",
        "archive-view-fading",
        "setGlanceStatus",
    ):
        require(marker in app, f"Archive interaction missing {marker}")

    html = HTML_PATH.read_text(encoding="utf-8")
    for icon_id in (
        "system-health-icon",
        "backup-status-icon",
        "offsite-status-icon",
        "restore-status-icon",
        "coverage-status-icon",
    ):
        require(f'id="{icon_id}"' in html, f"Semantic glance icon missing {icon_id}")

    styles = (ROOT / "ui" / "experience" / "styles.css").read_text(encoding="utf-8")
    require("card.dataset.status = status" in app, "Glance status is not applied to the shared card state")
    require("--glance-status-color" in styles, "Semantic heading and icon color variable is missing")
    require(
        ".summary-grid .glance-icon,\n.summary-grid article strong" in styles,
        "Glance icons and headings do not consume the same semantic color",
    )

    history = load_json(API_SOURCE_ROOT / "history.json")
    require(history.get("runs"), "History fixture must contain at least one run")
    for run in history["runs"]:
        snapshot = run.get("snapshot")
        require(snapshot is not None, f"Run {run.get('backup_id')} has no snapshot")
        for key in ("generated_at", "confidence", "story", "coverage"):
            require(key in snapshot, f"Run {run.get('backup_id')} snapshot lacks {key}")


def validate_documentation() -> None:
    reference = load_json(REFERENCE_PATH)
    require(reference.get("version") == "1.5", "Recovery Center reference version must be 1.5")
    require(reference.get("updated_at") == "2026-08-31T14:23:29-05:00", "Recovery Center updated_at must use the actual Chicago-local timestamp")
    entries = reference.get("entries", [])
    ids = {entry.get("id") for entry in entries}
    host_recovery_id = "host-recovery-prerequisites"
    restore_harbr_id = "restore-harbr"
    docker_platform_id = "docker-platform"
    nginx_proxy_manager_id = "nginx-proxy-manager"
    pihole_recovery_id = "pihole-recovery"
    jellyfin_recovery_id = "jellyfin-recovery"
    home_assistant_recovery_id = "home-assistant-recovery"
    placeholder_paragraphs = [
        "This operational recovery procedure is being developed.",
        "Future versions of Harbr will replace this placeholder with an interactive recovery runbook designed to guide operators through recovery, verification, and confidence validation.",
    ]
    host_recovery_headings = [
        "1. Install Debian",
        "2. Configure the expected hostname",
        "3. Verify network and Internet connectivity",
        "4. Verify SSH access",
        "5. Restore and mount the expected storage",
        "6. Verify that /srv/storage is writable",
        "7. Install or verify the required host software",
        "8. Install or verify Docker Engine and Docker Compose",
        "9. Select, verify, and preserve a backup set",
        "10. Restore host-level recovery configuration",
        "11. Recreate the harbr-api identity boundary",
        "12. Reload and verify restored host services",
        "13. Verify collector, updater, inventory, state, and protected access",
        "14. Hand off to Restore Harbr",
    ]
    restore_harbr_headings = [
        "1. Reconfirm the verified working backup set",
        "2. Restore the Harbr application",
        "3. Verify restored host integration and initialize Harbr",
        "4. Start Harbr",
        "5. Verify the Recovery Center is available",
        "6. Verify recovery evidence",
        "7. Generate and publish fresh Infrastructure evidence",
        "8. Verify operator access",
        "9. Confirm Harbr is ready to guide recovery",
    ]
    docker_platform_headings = [
        "1. Verify Harbr remains operational",
        "2. Reverify the selected two-artifact backup set",
        "3. Restore the remaining /srv/docker tree without overwriting Harbr",
        "4. Verify restored project and shared configuration",
        "5. Restore required Docker networks",
        "6. Verify Docker storage paths and permissions",
        "7. Verify Docker Compose projects can be evaluated",
        "8. Compare the protected inventory with the restored platform",
        "9. Confirm the Docker Platform is ready for application recovery",
        "10. Identify the next application recovery procedure",
    ]
    nginx_proxy_manager_headings = [
        "1. Verify prerequisites",
        "2. Locate the protected Nginx Proxy Manager recovery material",
        "3. Restore the application",
        "4. Restore application data",
        "5. Start the application",
        "6. Verify operational health",
        "7. Verify reverse proxy configuration",
        "8. Verify TLS readiness",
        "9. Confirm Nginx Proxy Manager is ready for service recovery",
        "10. Identify the next recovery procedure",
    ]
    pihole_recovery_headings = [
        "1. Locate the Pi-hole Compose project",
        "2. Verify required persistent data exists",
        "3. Verify required Docker networks",
        "4. Start the Pi-hole stack",
        "5. Verify container health",
        "6. Verify DNS service",
        "7. Verify administrative interface",
        "8. Verify upstream DNS functionality",
        "9. Complete manual validation",
        "10. Confirm Pi-hole recovery is complete",
    ]
    jellyfin_recovery_headings = [
        "1. Locate the Jellyfin Compose project",
        "2. Classify Jellyfin mounts",
        "3. Verify protected Jellyfin application state",
        "4. Verify external media storage",
        "5. Verify required Docker networking",
        "6. Start the Jellyfin stack",
        "7. Verify container stability and Jellyfin HTTP service",
        "8. Verify Jellyfin recognizes restored application state",
        "9. Complete manual Jellyfin validation",
        "10. Confirm Jellyfin recovery is complete",
    ]
    home_assistant_recovery_headings = [
        "1. Locate the Home Assistant Compose project",
        "2. Classify Home Assistant mounts",
        "3. Verify protected Home Assistant state",
        "4. Verify required host dependencies",
        "5. Verify Home Assistant networking",
        "6. Start the Home Assistant stack",
        "7. Verify container stability and Home Assistant availability",
        "8. Verify restored Home Assistant application state",
        "9. Complete manual Home Assistant validation",
        "10. Confirm Home Assistant recovery is complete",
    ]
    step_field_prefixes = (
        "Required operator action:",
        "Verification command:",
        "Expected successful result:",
        "If verification fails:",
        "Blocks recovery:",
    )
    require(REQUIRED_GUIDES <= ids, f"Missing guides: {sorted(REQUIRED_GUIDES - ids)}")
    require(entries and entries[0].get("id") == host_recovery_id, "Host Recovery must be the first Recovery Center entry")
    require(len(entries) > 1 and entries[1].get("id") == restore_harbr_id, "Restore Harbr must be the second Recovery Center entry")
    require(len(entries) > 2 and entries[2].get("id") == docker_platform_id, "Docker Platform must be the third Recovery Center entry")
    require(len(entries) > 3 and entries[3].get("id") == nginx_proxy_manager_id, "Nginx Proxy Manager must be the fourth Recovery Center entry")
    require(len(entries) > 4 and entries[4].get("id") == pihole_recovery_id, "Pi-hole Recovery must be the fifth Recovery Center entry")
    require(len(entries) > 5 and entries[5].get("id") == jellyfin_recovery_id, "Jellyfin Recovery must be the sixth Recovery Center entry")
    require(len(entries) > 6 and entries[6].get("id") == home_assistant_recovery_id, "Home Assistant Recovery must be the seventh Recovery Center entry")
    require(len(ids) == len(entries), "Recovery Center entry IDs must be unique")
    for entry in entries:
        require(entry.get("title") and entry.get("summary"), f"Incomplete guide metadata: {entry.get('id')}")
        if entry.get("id") in {host_recovery_id, restore_harbr_id, docker_platform_id, nginx_proxy_manager_id, pihole_recovery_id, jellyfin_recovery_id, home_assistant_recovery_id}:
            is_host_recovery = entry.get("id") == host_recovery_id
            is_restore_harbr = entry.get("id") == restore_harbr_id
            is_docker_platform = entry.get("id") == docker_platform_id
            is_nginx_proxy_manager = entry.get("id") == nginx_proxy_manager_id
            is_pihole_recovery = entry.get("id") == pihole_recovery_id
            is_jellyfin_recovery = entry.get("id") == jellyfin_recovery_id
            if is_host_recovery:
                expected_title = "Host Recovery"
                expected_headings = host_recovery_headings
            elif is_restore_harbr:
                expected_title = "Restore Harbr"
                expected_headings = restore_harbr_headings
            elif is_docker_platform:
                expected_title = "Docker Platform"
                expected_headings = docker_platform_headings
            elif is_nginx_proxy_manager:
                expected_title = "Nginx Proxy Manager"
                expected_headings = nginx_proxy_manager_headings
            elif is_pihole_recovery:
                expected_title = "Pi-hole Recovery"
                expected_headings = pihole_recovery_headings
            elif is_jellyfin_recovery:
                expected_title = "Jellyfin Recovery"
                expected_headings = jellyfin_recovery_headings
            else:
                expected_title = "Home Assistant Recovery"
                expected_headings = home_assistant_recovery_headings
            require(entry.get("title") == expected_title, f"{expected_title} has the wrong user-facing title")
            sections = entry.get("sections", [])
            require([section.get("heading") for section in sections] == expected_headings, f"{expected_title} steps are missing or out of order")
            sections_by_heading = {section["heading"]: section for section in sections}
            for section in sections:
                paragraphs = section.get("paragraphs", [])
                require(len(paragraphs) == len(step_field_prefixes), f"Incomplete {expected_title} step: {section.get('heading')}")
                require(
                    all(paragraph.startswith(prefix) for paragraph, prefix in zip(paragraphs, step_field_prefixes)),
                    f"{expected_title} step fields are missing or out of order: {section.get('heading')}",
                )
            if is_host_recovery:
                ssh_step = "\n".join(sections_by_heading[host_recovery_headings[3]]["paragraphs"])
                require("Recorded management IP:" in ssh_step and "chris@$MANAGEMENT_IP" in ssh_step, "Host Recovery SSH verification must use the recorded management IP")
                require("ssh chris@dockerhost" not in ssh_step, "Host Recovery SSH verification must not depend on local hostname resolution")
                require(ssh_step.index("'id -un'") < ssh_step.index("'hostnamectl --static'"), "Host Recovery must authenticate over SSH before verifying the hostname")
                docker_step = "\n".join(sections_by_heading[host_recovery_headings[7]]["paragraphs"])
                require("sudo -u chris docker info" in docker_step, "Host Recovery must prove Docker daemon access as chris")
                backup_step = "\n".join(sections_by_heading[host_recovery_headings[8]]["paragraphs"])
                for material in ("SHA256SUMS", "srv-docker.tar.zst", "disaster-recovery-config.tar.zst", "working copy"):
                    require(material in backup_step, f"Host Recovery backup-set verification is missing: {material}")
                host_config_step = "\n".join(sections_by_heading[host_recovery_headings[9]]["paragraphs"])
                for marker in ("--numeric-owner", "--acls", "--xattrs", "/root/.config/rclone/rclone.conf"):
                    require(marker in host_config_step, f"Host Recovery disaster-recovery extraction is missing: {marker}")
                identity_step = "\n".join(sections_by_heading[host_recovery_headings[10]]["paragraphs"])
                identity_command = sections_by_heading[host_recovery_headings[10]]["paragraphs"][1]
                for marker in ("stat --format='%g' /var/lib/service-check/status.json", "getent group \"$ARCHIVED_HARBR_GID\"", "groupadd --gid", "usermod --append --groups harbr-api chris", "sudo -u chris -g harbr-api test -r"):
                    require(marker in identity_step, f"Host Recovery harbr-api reconstruction is missing: {marker}")
                for forbidden in ("groupadd harbr-api", "chmod", "chgrp"):
                    require(forbidden not in identity_command, f"Host Recovery harbr-api reconstruction uses an unsafe shortcut: {forbidden}")
                require("test -z \"$GID_OWNER\" || test \"$GID_OWNER\" = harbr-api" in identity_step, "Host Recovery must block incompatible archived-GID collisions")
                services_step = "\n".join(sections_by_heading[host_recovery_headings[11]]["paragraphs"])
                for unit in ("docker-backup.timer", "service-check.timer", "harbr-infrastructure.service", "harbr-api-refresh.service"):
                    require(unit in services_step, f"Host Recovery service verification is missing: {unit}")
                require("do not start service-check" in services_step.lower(), "Host Recovery must defer service-check until Harbr exists")
                updater_step = "\n".join(sections_by_heading[host_recovery_headings[12]]["paragraphs"])
                require("service-update --help" in updater_step and "service-update v0.4.0" in updater_step, "Host Recovery must verify service-update with its supported help command")
                require("service-update --version" not in updater_step, "Host Recovery must not invoke unsupported service-update --version")
            elif is_restore_harbr:
                require(entry.get("summary") == "Restore Harbr and verify that the recovery console is operational.", "Restore Harbr has the wrong summary")
                application_step = "\n".join(sections_by_heading[restore_harbr_headings[1]]["paragraphs"])
                require("/srv/docker/harbr" in application_step and "harbr-experience" in application_step, "Restore Harbr must verify the isolated application location")
                center_step = "\n".join(sections_by_heading[restore_harbr_headings[4]]["paragraphs"])
                require('entries[0].id == "host-recovery-prerequisites"' in center_step, "Restore Harbr must verify Host Recovery availability")
                evidence_step = "\n".join(sections_by_heading[restore_harbr_headings[5]]["paragraphs"])
                require("do not infer or calculate confidence" in evidence_step, "Restore Harbr must preserve explicit evidence states")
                infrastructure_step = "\n".join(sections_by_heading[restore_harbr_headings[6]]["paragraphs"])
                for marker in ("systemctl start service-check.service", "PRIVATE_BEFORE", "PUBLIC_BEFORE", "PRIVATE_AFTER", "PUBLIC_AFTER", "/var/lib/service-check/status.json", "harbr-infrastructure.service", "api/v1/infrastructure.json", "stale_after_seconds == 32400", "warning"):
                    require(marker in infrastructure_step, f"Restore Harbr fresh Infrastructure verification is missing: {marker}")
                require("sudo /usr/local/sbin/service-check" not in infrastructure_step, "Restore Harbr must run service-check through systemd OnSuccess")
                guidance_step = "\n".join(sections_by_heading[restore_harbr_headings[8]]["paragraphs"])
                for marker in ("harbr-experience", "Recovery Center", "api/v1/index.json", "infrastructure.json"):
                    require(marker in guidance_step, f"Restore Harbr guidance-readiness check is missing: {marker}")
                next_step = "\n".join(sections_by_heading[restore_harbr_headings[8]]["paragraphs"])
                require("Next Recovery Step" in next_step and "Restore the Docker Platform." in next_step, "Restore Harbr must identify the next recovery step")
            elif is_docker_platform:
                require(entry.get("summary") == "Restore and verify the shared Docker environment required before application recovery can begin.", "Docker Platform has the wrong summary")
                inventory_step = "\n".join(sections_by_heading[docker_platform_headings[1]]["paragraphs"])
                for artifact in ("disaster-recovery-config.tar.zst", "srv-docker.tar.zst", "SHA256SUMS"):
                    require(artifact in inventory_step, f"Docker Platform backup-set verification is missing: {artifact}")
                restore_step = "\n".join(sections_by_heading[docker_platform_headings[2]]["paragraphs"])
                require("--exclude='srv/docker/harbr'" in restore_step and "--acls" in restore_step and "--xattrs" in restore_step, "Docker Platform must preserve live Harbr and archived filesystem metadata")
                commands = "\n".join(section["paragraphs"][1] for section in sections)
                for forbidden_command in ("docker compose up", "docker compose start", "docker start", "docker restart"):
                    require(forbidden_command not in commands, f"Docker Platform must not start application stacks: {forbidden_command}")
                readiness_step = "\n".join(sections_by_heading[docker_platform_headings[8]]["paragraphs"])
                for marker in ("harbr-experience", "systemctl is-active", "sudo -u chris docker info", "config --quiet", "Automatic checks alone do not authorize application recovery"):
                    require(marker in readiness_step, f"Docker Platform readiness check is missing: {marker}")
                next_step = "\n".join(sections_by_heading[docker_platform_headings[9]]["paragraphs"])
                require("no authoritative application recovery order" in next_step.lower(), "Docker Platform must not fabricate an application recovery order")
                require("Manual operator selection required" in next_step, "Docker Platform must require manual selection without authoritative order metadata")
            elif is_nginx_proxy_manager:
                require(entry.get("summary") == "Restore Nginx Proxy Manager and verify that reverse proxy services are operational.", "Nginx Proxy Manager has the wrong summary")
                prerequisite_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[0]]["paragraphs"])
                for prerequisite in ("host-recovery-prerequisites", "restore-harbr", "docker-platform", "manual procedure completion confirmation"):
                    require(prerequisite in prerequisite_step, f"Nginx Proxy Manager prerequisite check is missing: {prerequisite}")
                manual_input_label = "Manual operator input required because no authoritative recovery value is currently recorded."
                commands = "\n".join(section["paragraphs"][1] for section in sections)
                require(commands.count("read -r -p") == 3, "Nginx Proxy Manager must limit free-form input to the recovery source and two missing URLs")
                require(commands.count(manual_input_label) == 3, "Every free-form Nginx Proxy Manager input must explain the missing authoritative datum")
                prompt_endings = {
                    "NPM_RECOVERY_SOURCE": " NPM_RECOVERY_SOURCE &&",
                    "NPM_INTERFACE_URL": " NPM_INTERFACE_URL; fi",
                    "NPM_PROXY_TEST_URL": " NPM_PROXY_TEST_URL; fi",
                }
                for variable, prompt_ending in prompt_endings.items():
                    require(commands.count(prompt_ending) == 1, f"Nginx Proxy Manager must prompt for {variable} once")
                for forbidden_prompt in ("container name:", "service name:", "network name:", "container port:", "service user:", "Compose project name:", "Compose file:", "project directory:"):
                    require(forbidden_prompt not in commands, f"Nginx Proxy Manager must discover rather than prompt for: {forbidden_prompt}")
                locate_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[1]]["paragraphs"])
                require("same shell through step 9" in locate_step and "Keep this shell open through step 9" in locate_step, "Nginx Proxy Manager must establish a reusable same-shell recovery context")
                restore_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[2]]["paragraphs"])
                for marker in ("NPM_COMPOSE_CANDIDATES", "select NPM_COMPOSE_FILE", "config --services", "config --networks", "config --volumes"):
                    require(marker in restore_step, f"Nginx Proxy Manager Compose discovery is missing: {marker}")
                require(restore_step.count("select NPM_COMPOSE_FILE") == 1, "Nginx Proxy Manager must select the discovered Compose definition once")
                require("${#NPM_COMPOSE_CANDIDATES[@]} == 1" in restore_step, "Nginx Proxy Manager must automatically reuse a uniquely discovered Compose definition")
                data_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[3]]["paragraphs"])
                for marker in ("select NPM_APP_SERVICE", "select NPM_DB_SERVICE", 'in "${NPM_SERVICES[@]}"', "NPM_MOUNT_REPORT", "docker volume inspect"):
                    require(marker in data_step, f"Nginx Proxy Manager protected-data discovery is missing: {marker}")
                require(data_step.count('in "${NPM_SERVICES[@]}"') == 2, "Nginx Proxy Manager role selection must be constrained to discovered services")
                distinct_role_check = 'test "$NPM_APP_SERVICE" != "$NPM_DB_SERVICE"'
                require(distinct_role_check in data_step, "Nginx Proxy Manager application and database roles must be distinct")
                require(data_step.index(distinct_role_check) < data_step.index("NPM_MOUNT_REPORT"), "Nginx Proxy Manager duplicate role selection must fail before data or health verification")
                require("roles must identify distinct services; repeat the constrained selection" in data_step, "Nginx Proxy Manager must explain how to correct duplicate role selection")
                for marker in ("NPM_MISSING_VOLUMES=()", 'NPM_MISSING_VOLUMES+=("$source")', "Missing required named volumes:", '${#NPM_MISSING_VOLUMES[@]}', "false"):
                    require(marker in data_step, f"Nginx Proxy Manager missing-volume blocker is incomplete: {marker}")
                require("Named volume requires restoration before startup" not in data_step, "Nginx Proxy Manager must not handle missing named volumes as warnings")
                require("Step 5 must not start" in data_step and "every required" in data_step, "Nginx Proxy Manager must explicitly block startup while required volumes are missing")
                require("NPM_SERVICE_USER" not in commands and "NPM_TLS_USER" not in commands, "Nginx Proxy Manager must not assume container identities are host users")
                require("docker volume create" not in commands, "Nginx Proxy Manager must never create replacement named volumes")
                require(commands.count(" up -d") == 1, "Nginx Proxy Manager must contain exactly one application start command")
                require('docker compose -f "$NPM_COMPOSE_FILE" up -d' in commands, "Nginx Proxy Manager start must be scoped to the selected Compose file")
                start_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[4]]["paragraphs"])
                for marker in ('ps -q', "NPM_CONTAINER_IDS", "com.docker.compose.project"):
                    require(marker in start_step, f"Nginx Proxy Manager container discovery is missing: {marker}")
                require('docker volume inspect "$source"' in start_step, "Nginx Proxy Manager must recheck named volumes immediately before startup")
                for marker in ("NPM_START_MISSING_VOLUMES=()", 'NPM_START_MISSING_VOLUMES+=("$source")', '${#NPM_START_MISSING_VOLUMES[@]}', "false"):
                    require(marker in start_step, f"Nginx Proxy Manager pre-start missing-volume blocker is incomplete: {marker}")
                require(start_step.index('docker volume inspect "$source"') < start_step.index(' up -d'), "Nginx Proxy Manager must block before Compose can create an empty volume")
                require("startup blocked" in start_step and "Startup must remain blocked" in start_step, "Nginx Proxy Manager startup must remain blocked while a required named volume is absent")
                for forbidden_identity in ("NPM_APP_CONTAINER", "NPM_DB_CONTAINER"):
                    require(forbidden_identity not in commands, f"Nginx Proxy Manager must not request or depend on generated container identity: {forbidden_identity}")
                health_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[5]]["paragraphs"])
                for marker in ("NPM_EXPECTED_SERVICES", "NPM_RUNNING_SERVICES", "ps -q", "NPM_EXPECTED_NETWORKS", "docker network inspect", ".Mounts", ".NetworkSettings.Networks", "Publishers", "NPM_APP_SERVICE", "NPM_DB_SERVICE"):
                    require(marker in health_step, f"Nginx Proxy Manager specific health verification is missing: {marker}")
                require("no published host port is acceptable" in health_step, "Nginx Proxy Manager must permit intentional network-only publication")
                proxy_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[6]]["paragraphs"])
                require("manual administrative login and protected proxy-host comparison required" in proxy_step, "Nginx Proxy Manager must preserve manual administrative and proxy-host verification")
                require("read -r -p" not in proxy_step, "Nginx Proxy Manager must reuse the interface URL")
                tls_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[7]]["paragraphs"])
                require("manual certificate assignment and validity confirmation still required" in tls_step, "Nginx Proxy Manager must distinguish manual TLS confirmation")
                require("never display certificates, credentials, or private keys" in tls_step, "Nginx Proxy Manager must protect TLS and credential material")
                require("NPM_MOUNT_REPORT" in tls_step and ".Mounts" in tls_step, "Nginx Proxy Manager TLS verification must reuse discovered mounts")
                readiness_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[8]]["paragraphs"])
                require("Automatic verification alone does not authorize service recovery" in readiness_step, "Nginx Proxy Manager must preserve manual readiness confirmation")
                require("NPM_PROXY_TEST_URL" in readiness_step and "manual administrative, proxy-host, TLS, and database-backed behavior confirmation" in readiness_step, "Nginx Proxy Manager must preserve manual operational verification")
                require("chmod 600" in health_step and "chmod 600" in readiness_step, "Nginx Proxy Manager logs must remain restricted")
                require(commands.count("config --format json") == commands.count("config --format json | jq"), "Nginx Proxy Manager resolved Compose data must be filtered rather than displayed")
                for unsafe_output in ("printenv", "docker inspect --format '{{.Config.Env", "docker compose config >", "docker compose config |", "cat .env", "cat /run/secrets"):
                    require(unsafe_output not in commands, f"Nginx Proxy Manager must not display protected content: {unsafe_output}")
                next_step = "\n".join(sections_by_heading[nginx_proxy_manager_headings[9]]["paragraphs"])
                require("no authoritative application recovery order" in next_step.lower(), "Nginx Proxy Manager must not fabricate the next recovery procedure")
                require("Manual operator selection required" in next_step, "Nginx Proxy Manager must require manual selection without authoritative order metadata")
            elif is_pihole_recovery:
                require(entry.get("summary") == "Restore Pi-hole and verify that dependable local DNS is operational.", "Pi-hole Recovery has the wrong summary")
                commands = "\n".join(section["paragraphs"][1] for section in sections)
                require("read -r -p" not in commands, "Pi-hole Recovery must discover values rather than request free-form input")
                locate_step = "\n".join(sections_by_heading[pihole_recovery_headings[0]]["paragraphs"])
                for marker in ("same shell", "PIHOLE_COMPOSE_CANDIDATES", "select PIHOLE_COMPOSE_FILE", "PIHOLE_SERVICE_CANDIDATES", "select PIHOLE_SERVICE", "PIHOLE_MOUNT_REPORT", "Keep this shell open through step 10"):
                    require(marker in locate_step, f"Pi-hole Compose discovery is missing: {marker}")
                require("${#PIHOLE_COMPOSE_CANDIDATES[@]} == 1" in locate_step, "Pi-hole Recovery must automatically reuse a unique Compose definition")
                require("${#PIHOLE_SERVICE_CANDIDATES[@]} == 1" in locate_step, "Pi-hole Recovery must automatically reuse a unique Pi-hole service")
                persistent_step = "\n".join(sections_by_heading[pihole_recovery_headings[1]]["paragraphs"])
                for marker in ("PIHOLE_MISSING_DATA=()", 'PIHOLE_MISSING_DATA+=("bind:$source")', 'PIHOLE_MISSING_DATA+=("volume:$source")', "docker volume inspect", "Missing required Pi-hole persistent data:", '${#PIHOLE_MISSING_DATA[@]}', "false"):
                    require(marker in persistent_step, f"Pi-hole persistent-data blocker is incomplete: {marker}")
                require("Do not create an empty directory or volume" in persistent_step, "Pi-hole Recovery must prohibit replacement empty data")
                network_step = "\n".join(sections_by_heading[pihole_recovery_headings[2]]["paragraphs"])
                for marker in ("PIHOLE_NETWORK_REPORT", "PIHOLE_MISSING_NETWORKS=()", "docker network inspect", "Missing required Pi-hole networks:", '${#PIHOLE_MISSING_NETWORKS[@]}', "false"):
                    require(marker in network_step, f"Pi-hole network verification is incomplete: {marker}")
                for marker in ("PIHOLE_NETWORK_MODE", ".network_mode", "host)", "none)", "service:*|container:*)", "'')", "bridge)"):
                    require(marker in network_step, f"Pi-hole network-mode handling is missing: {marker}")
                require('networks // {"default": null}' not in network_step, "Pi-hole Recovery must not fabricate a default network for host or shared network modes")
                require("host networking; no Compose network entry is required" in network_step and "intentionally empty network report" in network_step, "Pi-hole host networking must pass without a Docker network report entry")
                require("network_mode is none; DNS network service is unavailable and recovery is blocked" in network_step, "Pi-hole network_mode none must block DNS recovery")
                require("shares a network namespace" in network_step and "restore and independently verify the shared network-namespace dependency" in network_step, "Pi-hole shared network namespace modes must block pending dependency verification")
                require("service has no explicit network and Compose would genuinely attach it" in network_step, "Pi-hole default network must be limited to genuine Compose default attachment")
                require("does not mutate Docker state" in network_step, "Pi-hole network verification must remain non-mutating")
                start_step = "\n".join(sections_by_heading[pihole_recovery_headings[3]]["paragraphs"])
                require(commands.count(" up -d") == 1, "Pi-hole Recovery must contain exactly one stack startup command")
                require('docker compose -f "$PIHOLE_COMPOSE_FILE" up -d' in start_step, "Pi-hole startup must be scoped to the selected Compose definition")
                for marker in ("PIHOLE_START_BLOCKERS=()", "PIHOLE_MOUNT_REPORT", "PIHOLE_NETWORK_REPORT", "docker volume inspect", "docker network inspect", "PIHOLE_CONTAINER_ID", 'ps -q "$PIHOLE_SERVICE"'):
                    require(marker in start_step, f"Pi-hole pre-start safety or container discovery is missing: {marker}")
                for marker in ("PIHOLE_START_NETWORK_MODE", ".network_mode", 'test "$PIHOLE_START_NETWORK_MODE" = "$PIHOLE_NETWORK_MODE"', "host)", 'test ! -s "$PIHOLE_NETWORK_REPORT"', "network_mode:none", "unverified-network-namespace", "''|bridge)"):
                    require(marker in start_step, f"Pi-hole pre-start network-mode recheck is missing: {marker}")
                require(start_step.index("PIHOLE_START_BLOCKERS") < start_step.index(" up -d"), "Pi-hole dependencies must be rechecked before startup")
                require(start_step.index("PIHOLE_START_NETWORK_MODE") < start_step.index(" up -d"), "Pi-hole network mode must be re-derived before startup")
                require("docker volume create" not in commands and "docker network create" not in commands and "mkdir" not in commands, "Pi-hole verification must not create missing recovery dependencies")
                health_step = "\n".join(sections_by_heading[pihole_recovery_headings[4]]["paragraphs"])
                for marker in ('ps --status running -q "$PIHOLE_SERVICE"', "RestartCount", "PIHOLE_RESTARTS_BEFORE", "PIHOLE_RESTARTS_AFTER", ".State.Health", "healthy"):
                    require(marker in health_step, f"Pi-hole container health verification is missing: {marker}")
                dns_step = "\n".join(sections_by_heading[pihole_recovery_headings[5]]["paragraphs"])
                for marker in ("PIHOLE_DNS_PUBLICATION", "PIHOLE_DNS_HOST", "PIHOLE_DNS_PORT", "Publishers", "TargetPort == 53", "HostConfig.NetworkMode", "ss -lunt", 'dig @"$PIHOLE_DNS_HOST"', 'nslookup example.com "$PIHOLE_DNS_HOST"', "example.com"):
                    require(marker in dns_step, f"Pi-hole local DNS verification is missing: {marker}")
                admin_step = "\n".join(sections_by_heading[pihole_recovery_headings[6]]["paragraphs"])
                for marker in ("PIHOLE_CONTAINER_ID", "PIHOLE_WEB_PUBLICATION", "Publishers", "TargetPort", "PublishedPort", "PIHOLE_WEB_HOST_PORT", "HostConfig.NetworkMode", "ExposedPorts", "NetworkSettings.Networks", "PIHOLE_ADMIN_URL", "PIHOLE_HTTP_STATUS"):
                    require(marker in admin_step, f"Pi-hole administrative interface verification is missing: {marker}")
                require(admin_step.index("PIHOLE_WEB_PUBLICATION") < admin_step.index("HostConfig.NetworkMode") < admin_step.index("NetworkSettings.Networks"), "Pi-hole administrative endpoint discovery must prefer publication, then host mode, then container networking")
                require('PIHOLE_WEB_ENDPOINT_PORT=$PIHOLE_WEB_HOST_PORT' in admin_step, "Pi-hole administrative verification must support host ports that differ from container ports")
                require("2[0-9]{2}|3[0-9]{2}|401|403" in admin_step, "Pi-hole administrative verification must allow only success, redirect, and authentication-related responses")
                require("404 means the administrative endpoint was not proven" in admin_step and "-lt 500" not in admin_step, "Pi-hole administrative verification must reject arbitrary 404 responses")
                require("non-mutating availability check" in admin_step, "Pi-hole administrative verification must remain non-mutating")
                require("without logging in" in admin_step and "without logging in or exposing a password" in admin_step, "Pi-hole administrative verification must remain unauthenticated and secret-safe")
                upstream_step = "\n".join(sections_by_heading[pihole_recovery_headings[7]]["paragraphs"])
                upstream_command = sections_by_heading[pihole_recovery_headings[7]]["paragraphs"][1]
                for marker in ("PIHOLE_DNS_HOST", "PIHOLE_DNS_PORT", 'dig @"$PIHOLE_DNS_HOST"', 'nslookup example.com "$PIHOLE_DNS_HOST"', "example.com"):
                    require(marker in upstream_step, f"Pi-hole host-side upstream verification is missing: {marker}")
                require("exec -T" not in upstream_command and "sh -c" not in upstream_command, "Pi-hole upstream verification must not require container diagnostic utilities")
                require("install packages" in upstream_step and "Do not install tools in the container" in upstream_step, "Pi-hole upstream verification must prohibit container mutation")
                for hardcoded_resolver in ("8.8.8.8", "1.1.1.1", "9.9.9.9"):
                    require(hardcoded_resolver not in upstream_step, f"Pi-hole Recovery must not hardcode upstream resolver {hardcoded_resolver}")
                manual_step = "\n".join(sections_by_heading[pihole_recovery_headings[8]]["paragraphs"])
                for marker in ("expected blocklists", "expected local DNS records", "expected DHCP configuration", "expected client query activity"):
                    require(marker in manual_step, f"Pi-hole manual validation is missing: {marker}")
                completion_step = "\n".join(sections_by_heading[pihole_recovery_headings[9]]["paragraphs"])
                completion_command = sections_by_heading[pihole_recovery_headings[9]]["paragraphs"][1]
                require("dependable local DNS has been restored" in completion_step and "later application recovery may continue" in completion_step, "Pi-hole Recovery completion statement is incomplete")
                require("PIHOLE_DNS_HOST" in completion_step and "PIHOLE_DNS_PORT" in completion_step, "Pi-hole completion must reuse the discovered host-side DNS listener")
                require("exec -T" not in completion_command and "sh -c" not in completion_command, "Pi-hole completion must not require diagnostic utilities inside the container")
                for forbidden_identity in ("container name", "PIHOLE_CONTAINER_NAME"):
                    require(forbidden_identity not in commands, f"Pi-hole Recovery must not depend on generated container identity: {forbidden_identity}")
                require(commands.count("config --format json") == commands.count("config --format json | jq"), "Pi-hole resolved Compose data must be filtered rather than displayed")
                for unsafe_output in ("printenv", "Config.Env", "cat .env", "cat /run/secrets", "docker compose config >", "docker compose config |"):
                    require(unsafe_output not in commands, f"Pi-hole Recovery must not display protected content: {unsafe_output}")
            elif is_jellyfin_recovery:
                require(entry.get("summary") == "Restore Jellyfin application state and verify its separately maintained media library.", "Jellyfin Recovery has the wrong summary")
                commands = "\n".join(section["paragraphs"][1] for section in sections)
                require("read -r -p" not in commands, "Jellyfin Recovery must discover values rather than request free-form input")
                locate_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[0]]["paragraphs"])
                for marker in ("same shell", "JELLYFIN_COMPOSE_CANDIDATES", "select JELLYFIN_COMPOSE_FILE", "JELLYFIN_SERVICE_CANDIDATES", "select JELLYFIN_SERVICE", "JELLYFIN_RAW_MOUNTS", "Keep this shell open through step 10"):
                    require(marker in locate_step, f"Jellyfin Compose discovery is missing: {marker}")
                classification_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[1]]["paragraphs"])
                for marker in ("protected-state", "rebuildable", "external-media", "runtime-support", "JELLYFIN_MOUNT_REPORT", "select classification in protected-state rebuildable external-media runtime-support"):
                    require(marker in classification_step, f"Jellyfin mount classification is missing: {marker}")
                require("JELLYFIN_UNCLASSIFIED" not in classification_step and "no mount remains unresolved or review-required" in classification_step, "Jellyfin ambiguous mounts must have a constrained resolution path")
                require("do not classify a mount as protected merely because Compose declares it" in classification_step, "Jellyfin mounts must not all be treated as protected state")
                state_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[2]]["paragraphs"])
                for marker in ("jellyfin_state_present()", "JELLYFIN_MISSING_STATE", "protected-state", "docker volume inspect", ".Mountpoint", "-mindepth 1 -maxdepth 3 -print -quit", "Missing or empty protected Jellyfin application state", "runtime-support", "JELLYFIN_MISSING_RUNTIME", "false"):
                    require(marker in state_step, f"Jellyfin protected-state blocker is missing: {marker}")
                require("Do not create, initialize, repair, hash, or fully traverse protected state" in state_step, "Jellyfin Recovery must prohibit mutation and unbounded protected-state inspection")
                media_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[3]]["paragraphs"])
                for marker in ("JELLYFIN_MEDIA_REPORT", "external-media", "findmnt --noheadings --output TARGET", "-print -quit", "JELLYFIN_MISSING_MEDIA", "JELLYFIN_ROOT_MEDIA_APPROVED", "select root_media_decision", "jellyfin_media_present()", "separately maintained"):
                    require(marker in media_step, f"Jellyfin external-media verification is missing: {marker}")
                require("/srv/storage deployment, passes automatically" in media_step, "Jellyfin mounted /srv/storage media must pass automatically")
                require("intentional root-filesystem" in media_step and "protected evidence confirms this exact source" in media_step, "Jellyfin root-filesystem media must require constrained protected evidence")
                require("excluded from the protected Docker application backup" in media_step and "Do not create directories" in media_step, "Jellyfin Recovery must distinguish and protect excluded media")
                network_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[4]]["paragraphs"])
                for marker in ("JELLYFIN_NETWORK_MODE", "host)", "none)", "service:*|container:*)", "'')", "bridge)", "docker network inspect"):
                    require(marker in network_step, f"Jellyfin network-mode handling is missing: {marker}")
                require('networks // {"default": null}' not in network_step, "Jellyfin Recovery must not fabricate default networks")
                start_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[5]]["paragraphs"])
                require(commands.count(" up -d") == 1 and 'docker compose -f "$JELLYFIN_COMPOSE_FILE" up -d' in start_step, "Jellyfin Recovery must contain one scoped startup")
                for marker in ("JELLYFIN_START_BLOCKERS", "protected-state", "external-media", "runtime-support", "jellyfin_state_present", "jellyfin_media_present", "JELLYFIN_START_NETWORK_MODE", "docker volume inspect", "docker network inspect", "JELLYFIN_CONTAINER_ID", 'ps -q "$JELLYFIN_SERVICE"'):
                    require(marker in start_step, f"Jellyfin pre-start recheck is missing: {marker}")
                require(start_step.index("jellyfin_state_present") < start_step.index(" up -d") and start_step.index("jellyfin_media_present") < start_step.index(" up -d"), "Jellyfin protected state and media evidence must be rechecked before startup")
                http_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[6]]["paragraphs"])
                for marker in ("RestartCount", ".State.Health", "JELLYFIN_WEB_PUBLICATION", "PublishedPort", "NetworkSettings.Networks", "System/Info/Public", "JELLYFIN_HTTP_STATUS", '= 200'):
                    require(marker in http_step, f"Jellyfin stability or HTTP verification is missing: {marker}")
                require("arbitrary 404 responses do not pass" in http_step, "Jellyfin HTTP verification must reject 404 responses")
                restored_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[7]]["paragraphs"])
                for marker in ("StartupWizardCompleted", "JELLYFIN_PUBLIC_INFO", ".Mounts", "chmod 600", "database", "configuration initialization failure"):
                    require(marker in restored_step, f"Jellyfin restored-state verification is missing: {marker}")
                manual_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[8]]["paragraphs"])
                for marker in ("expected users", "expected libraries", "representative playback", "expected recordings", "proxied access", "hardware transcoding", "scheduled library scans"):
                    require(marker in manual_step, f"Jellyfin manual validation is missing: {marker}")
                completion_step = "\n".join(sections_by_heading[jellyfin_recovery_headings[9]]["paragraphs"])
                for marker in ("Jellyfin application state has been restored", "separately maintained media library is available", "Representative playback has been manually confirmed", "Jellyfin recovery is complete"):
                    require(marker in completion_step, f"Jellyfin completion is missing: {marker}")
                require("jellyfin_state_present" in completion_step and "jellyfin_media_present" in completion_step, "Jellyfin completion must reuse corrected state and media verification")
                require("docker volume create" not in commands and "docker network create" not in commands and "mkdir" not in commands, "Jellyfin verification must not create missing recovery data")
                require("container name" not in commands and "JELLYFIN_CONTAINER_NAME" not in commands, "Jellyfin Recovery must not use generated container names")
                require(commands.count("config --format json") == commands.count("config --format json | jq"), "Jellyfin resolved Compose data must be filtered")
                for unsafe_output in ("printenv", "Config.Env", "cat .env", "cat /run/secrets"):
                    require(unsafe_output not in commands, f"Jellyfin Recovery must not display protected content: {unsafe_output}")
            else:
                require(entry.get("summary") == "Restore Home Assistant's protected application state and verify that the restored instance is operational.", "Home Assistant Recovery has the wrong summary")
                commands = "\n".join(section["paragraphs"][1] for section in sections)
                require("read -r -p" not in commands, "Home Assistant Recovery must discover values rather than request free-form input")
                locate_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[0]]["paragraphs"])
                for marker in ("same shell", "HOMEASSISTANT_COMPOSE_CANDIDATES", "HOMEASSISTANT_SERVICE_CANDIDATES", "select HOMEASSISTANT_SELECTION", "HOMEASSISTANT_MOUNT_REPORT", "HOMEASSISTANT_PORT_REPORT", "Keep this shell open through step 10"):
                    require(marker in locate_step, f"Home Assistant Compose discovery is missing: {marker}")
                classification_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[1]]["paragraphs"])
                for marker in ("protected-state", "rebuildable", "runtime-support", "HOMEASSISTANT_CLASSIFIED_MOUNTS", "select classification in protected-state rebuildable runtime-support", "no mount remains unresolved"):
                    require(marker in classification_step, f"Home Assistant mount classification is missing: {marker}")
                state_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[2]]["paragraphs"])
                for marker in ("homeassistant_state_present()", "homeassistant_runtime_present()", "HOMEASSISTANT_MISSING_STATE", "HOMEASSISTANT_MISSING_RUNTIME", ".Mountpoint", "-mindepth 1 -maxdepth 3 -print -quit", "Missing or empty protected Home Assistant state"):
                    require(marker in state_step, f"Home Assistant protected-state verification is missing: {marker}")
                require("Do not create directories or volumes, initialize clean state" in state_step, "Home Assistant Recovery must block clean-state initialization")
                dependency_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[3]]["paragraphs"])
                for marker in ("HOMEASSISTANT_HOST_REPORT", ".devices", ".privileged", ".cap_add", "HOMEASSISTANT_MISSING_DEVICES"):
                    require(marker in dependency_step, f"Home Assistant host-dependency verification is missing: {marker}")
                network_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[4]]["paragraphs"])
                for marker in ("HOMEASSISTANT_NETWORK_MODE", "host)", "none)", "service:*|container:*)", "bridge)", "'')", "docker network inspect"):
                    require(marker in network_step, f"Home Assistant network-mode handling is missing: {marker}")
                require('networks // {"default": null}' not in network_step and "Do not fabricate a default network" in network_step, "Home Assistant Recovery must not fabricate default networks")
                for marker in (". as $config", "$config.services[$service].networks", "$config.networks[$key].name", '$config.name + "_" + $key', '$config.name + "_default"'):
                    require(marker in network_step, f"Home Assistant explicit-network resolution does not retain root Compose context: {marker}")
                start_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[5]]["paragraphs"])
                require(commands.count(" up -d") == 1 and 'docker compose -f "$HOMEASSISTANT_COMPOSE_FILE" up -d' in start_step, "Home Assistant Recovery must contain exactly one scoped startup")
                for marker in ("HOMEASSISTANT_START_BLOCKERS", "homeassistant_state_present", "homeassistant_runtime_present", "HOMEASSISTANT_HOST_REPORT", "HOMEASSISTANT_NETWORK_REPORT", "HOMEASSISTANT_START_NETWORK_MODE", '.network_mode // ""', 'test "$HOMEASSISTANT_START_NETWORK_MODE" != "$HOMEASSISTANT_NETWORK_MODE"', "network-mode-changed", "HOMEASSISTANT_CONTAINER_ID", 'ps -q "$HOMEASSISTANT_SERVICE"'):
                    require(marker in start_step, f"Home Assistant pre-start recheck is missing: {marker}")
                require(start_step.index("homeassistant_state_present") < start_step.index(" up -d"), "Home Assistant protected state must be rechecked before startup")
                require(start_step.index("HOMEASSISTANT_START_NETWORK_MODE") < start_step.index(" up -d") and start_step.index("network-mode-changed") < start_step.index(" up -d"), "Home Assistant network mode must be re-derived and compared before startup")
                availability_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[6]]["paragraphs"])
                for marker in ("RestartCount", ".State.Health", "HOMEASSISTANT_NETWORK_MODE", "8123/tcp", "NetworkSettings.Networks", "manifest.json", "api/discovery_info", '.name == "Home Assistant"', ".version", '= 200'):
                    require(marker in availability_step, f"Home Assistant stability or endpoint verification is missing: {marker}")
                require("arbitrary 2xx pages" in availability_step and "authentication responses" in availability_step, "Home Assistant endpoint verification must reject arbitrary HTTP success")
                restored_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[7]]["paragraphs"])
                for marker in ("api/onboarding", "all(.[]; .done == true)", ".Mounts", "version", "first-run onboarding", "initialization", "HOMEASSISTANT_INIT_LOG", "mktemp", "chmod 600", 'docker compose -f "$HOMEASSISTANT_COMPOSE_FILE" logs', "--since 15m", "--tail 200", "configuration", "recorder", "sqlite", "database", "migration", "fatal", "! grep -Eiq"):
                    require(marker in restored_step, f"Home Assistant restored-state verification is missing: {marker}")
                require('> "$HOMEASSISTANT_INIT_LOG" 2>&1' in restored_step, "Home Assistant scoped logs must be captured without printing")
                require('cat "$HOMEASSISTANT_INIT_LOG"' not in restored_step and 'printf "$HOMEASSISTANT_INIT_LOG"' not in restored_step, "Home Assistant initialization logs must not be printed")
                require("HOMEASSISTANT_PERSISTENT_INIT_FAILURES" not in restored_step and "-lt 3" not in restored_step, "Home Assistant initialization failures must not use an occurrence-count tolerance")
                require("any narrowly matched initialization failure is present" in restored_step and "Ordinary warnings, unavailable integrations, and recoverable external-dependency errors do not block" in restored_step, "Home Assistant narrow initialization matches must block without treating ordinary dependency warnings as fatal")
                manual_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[8]]["paragraphs"])
                for marker in ("dashboards", "users", "integrations", "automations", "scripts", "scenes", "devices", "entities", "notifications", "Nginx Proxy Manager", "representative automation"):
                    require(marker in manual_step, f"Home Assistant manual validation is missing: {marker}")
                completion_step = "\n".join(sections_by_heading[home_assistant_recovery_headings[9]]["paragraphs"])
                for marker in ("Home Assistant application state has been restored", "Configuration has been successfully recognized", "Representative automation has been manually validated", "Home Assistant recovery is complete", "homeassistant_state_present", "homeassistant_runtime_present", "api/onboarding", ".HostConfig.Devices", ".HostConfig.Privileged", ".HostConfig.CapAdd"):
                    require(marker in completion_step, f"Home Assistant completion is missing: {marker}")
                require("docker volume create" not in commands and "docker network create" not in commands and "mkdir" not in commands, "Home Assistant verification must not create missing recovery data")
                require("container name" not in commands and "HOMEASSISTANT_CONTAINER_NAME" not in commands, "Home Assistant Recovery must not use generated container names")
                require(commands.count("config --format json") == commands.count("config --format json | jq"), "Home Assistant resolved Compose data must be filtered")
                for unsafe_output in ("printenv", "Config.Env", "cat .env", "cat /run/secrets", "secrets.yaml", "docker logs"):
                    require(unsafe_output not in commands, f"Home Assistant Recovery must not display protected content: {unsafe_output}")
            continue
        require(entry.get("summary") == placeholder_paragraphs[0], f"Guide summary is not the Recovery Center placeholder: {entry.get('id')}")
        require(
            entry.get("sections") == [{"heading": "Recovery Center", "paragraphs": placeholder_paragraphs}],
            f"Guide contains content outside the Recovery Center placeholder: {entry.get('id')}",
        )


def validate_recovery_prerequisites() -> None:
    source = load_json(PREREQUISITES_PATH)
    require(source.get("schema_version") == 1, "Unsupported prerequisite schema")
    components = source.get("components", [])
    require(components, "Recovery prerequisite catalog is empty")
    required_fields = {
        "id", "name", "category", "purpose", "requirement_level", "installation_source",
        "package", "command", "configuration_dependency", "verification_command", "recovery_notes",
    }
    ids = set()
    categories = set()
    for component in components:
        require(required_fields <= component.keys(), f"Incomplete prerequisite: {component.get('id')}")
        require(component["requirement_level"] in {"required", "recommended", "optional"}, f"Invalid requirement level: {component['id']}")
        require(component["id"] not in ids, f"Duplicate prerequisite: {component['id']}")
        ids.add(component["id"])
        categories.add(component["category"])
    require(REQUIRED_RECOVERY_CATEGORIES <= categories, f"Missing recovery categories: {sorted(REQUIRED_RECOVERY_CATEGORIES - categories)}")
    github_cli = next(component for component in components if component["id"] == "github-cli")
    require(github_cli["requirement_level"] == "optional", "GitHub CLI must not be presented as a restore requirement")


def validate_inventory() -> None:
    inventory = load_json(API_SOURCE_ROOT / "inventory.json")
    require(inventory.get("api_version") == "v1", "Inventory fixture is not versioned")
    require(inventory.get("inventory_status") == "not-generated", "Bootstrap inventory must not fabricate host detection")
    for field in ("generated_at", "host", "components", "systemd_units", "identities"):
        require(field in inventory, f"Inventory fixture lacks {field}")

    forbidden_fragments = ("password", "token", "private_key", "secret", "credential", "environment")

    def inspect_keys(value, path="inventory"):
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = key.lower()
                require(not any(fragment in lowered for fragment in forbidden_fragments), f"Unsafe inventory field: {path}.{key}")
                inspect_keys(child, f"{path}.{key}")
        elif isinstance(value, list):
            for position, child in enumerate(value):
                inspect_keys(child, f"{path}[{position}]")

    inspect_keys(inventory)
    generator = INVENTORY_GENERATOR_PATH.read_text(encoding="utf-8")
    for marker in (
        "component_version()",
        "dpkg-query",
        "docker-backup.timer",
        "harbr-api-refresh.service",
        'harbr_api_group: {name: "harbr-api"',
        'inventory_status: "generated"',
    ):
        require(marker in generator, f"Inventory generator missing {marker}")
    require("rclone.conf" not in generator or "SOURCE_CONFIG" not in generator, "Inventory generator must not inspect rclone credential contents")


def validate_infrastructure() -> None:
    data = load_json(API_SOURCE_ROOT / "infrastructure.json")
    require(data.get("api_version") == "v1", "Infrastructure fixture is not versioned")
    require(data.get("status") == "unknown" and data.get("sites") == [], "Bootstrap Infrastructure must not fabricate healthy state")
    require(data.get("stale_after_seconds") == 300, "Infrastructure freshness contract changed unexpectedly")
    index = load_json(API_SOURCE_ROOT / "index.json")
    require(index["resources"].get("infrastructure") == "/api/v1/infrastructure.json", "Infrastructure is not registered")
    schema_text = INFRASTRUCTURE_SCHEMA_PATH.read_text(encoding="utf-8")
    for forbidden in ("local_digest", "remote_digest", "image_id", "management_ip", "compose_file", "compose_directory"):
        require(forbidden not in schema_text, f"Private field present in Infrastructure schema: {forbidden}")
    generator = INFRASTRUCTURE_GENERATOR_PATH.read_text(encoding="utf-8")
    for marker in ("SERVICE_CHECK_SOURCE", "/var/lib/service-check/status.json", "state/.api-build", "mktemp -d", "jq -e", "mv -f", "EUID == 0", "elif .site and .host", ".host.status", "failed_systemd_units", ".image.reference?", ".image.update_status?", "def docker_health", ".container_name // .name", ".health // \"unknown\""):
        require(marker in generator, f"Infrastructure adapter missing {marker}")
    require("docker.sock" not in generator and "systemctl" not in generator and "apt " not in generator, "Infrastructure adapter performs collection")
    fixture = load_json(SERVICE_CHECK_V03_FIXTURE_PATH)
    require("sites" not in fixture and {"site", "host"} <= fixture.keys(), "service-check fixture must use the v0.3 single-host shape")
    require(fixture.get("collector") == {"name": "service-check", "version": "0.3.0"}, "service-check fixture has the wrong collector identity")
    require(fixture["site"].get("id") == "LDF" and fixture["host"].get("id") == "ldf-dockerhost", "service-check fixture has the wrong stable identities")
    require(fixture["host"].get("failed_systemd_units") == [], "service-check fixture must exercise the systemd array shape")
    require(all("containers" in project and "services" not in project for project in fixture["host"]["docker"]["projects"]), "service-check fixture must use the v0.3 containers key")
    fixture_services = [service for project in fixture["host"]["docker"]["projects"] for service in project["containers"]]
    require(len(fixture_services) == 7 and all(service["status"] == "healthy" for service in fixture_services), "service-check fixture must contain seven healthy runtime services")
    require(all(service.get("runtime_state") == "running" and "health" in service and "started_at" in service for service in fixture_services), "service-check fixture lacks real container runtime fields")
    database = next(service for service in fixture_services if service["service_id"] == "db")
    require(database["image"]["reference"] == "mariadb:10.11" and database["image"]["update_status"] == "update_available", "service-check fixture does not exercise the nested MariaDB image update")
    app = APP_PATH.read_text(encoding="utf-8")
    for marker in ("renderInfrastructure", "pollInfrastructure", "60000", "visibilitychange", "infrastructure.json"):
        require(marker in app, f"Infrastructure browser integration missing {marker}")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate-json-schema.py"), str(INFRASTRUCTURE_SCHEMA_PATH), str(API_SOURCE_ROOT / "infrastructure.json")],
        check=True, capture_output=True, text=True,
    )


def validate_refresh_deployment() -> None:
    unit = REFRESH_UNIT_PATH.read_text(encoding="utf-8")
    drop_in = BACKUP_DROP_IN_PATH.read_text(encoding="utf-8")
    refresh = (ROOT / "plugins" / "docker" / "refresh-api.sh").read_text(encoding="utf-8")
    rclone_installer = RCLONE_INSTALLER_PATH.read_text(encoding="utf-8")
    host_preflight = HOST_PREFLIGHT_PATH.read_text(encoding="utf-8")
    for marker in (
        "User=chris",
        "SupplementaryGroups=harbr-api",
        "BACKUP_CONFIG=/etc/harbr/backup-api.conf",
        "RCLONE_CONFIG=/var/lib/harbr/rclone/rclone.conf",
    ):
        require(marker in unit, f"Refresh service missing {marker}")
    require("OnSuccess=harbr-api-refresh.service" in drop_in, "Backup service does not trigger API refresh")
    require("ExecStartPost=/usr/bin/setfacl" in drop_in, "Backup service does not refresh metadata ACLs")
    require("g:harbr-api:r" in drop_in, "Backup metadata access must use the Harbr role group")
    require("EUID == 0" in refresh, "API refresh must refuse root execution")
    require('source_file in "$BACKUP_STATUS" "$BACKUP_HISTORY"' in refresh, "API refresh lacks source permission checks")
    require('"$INVENTORY_GENERATOR" "$TMP_DIR/inventory.json"' in refresh, "API refresh does not generate inventory")
    require("site confidence story history coverage system inventory infrastructure index" in refresh, "API resources are not atomically published")
    require('infrastructure: "/api/v1/infrastructure.json"' in refresh, "Infrastructure is not registered by runtime refresh")
    for marker in (
        'DEST_CONFIG="${DEST_CONFIG:-/var/lib/harbr/rclone/rclone.conf}"',
        'REMOTE_NAME="${REMOTE_NAME:-OneDrive}"',
        "listremotes",
        '${#remotes[@]} != 1',
        '-m 0700 "$destination_dir"',
        '-m 0600 "$temp_config"',
    ):
        require(marker in rclone_installer, f"Dedicated rclone installer missing {marker}")
    require('command" == "setfacl"' in host_preflight, "Host preflight must explain the missing acl dependency")
    require("Install the acl package" in host_preflight, "Host preflight lacks acl installation guidance")


def main() -> None:
    validate_json()
    validate_internal_resources()
    validate_confidence_ring_config()
    validate_startup()
    validate_archives()
    validate_documentation()
    validate_recovery_prerequisites()
    validate_inventory()
    validate_infrastructure()
    validate_refresh_deployment()
    print("Harbr validation passed")


if __name__ == "__main__":
    main()
