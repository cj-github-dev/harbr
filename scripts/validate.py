#!/usr/bin/env python3
"""Dependency-free structural validation for the Harbr web experience."""

from __future__ import annotations

import json
import hashlib
import runpy
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
APPROVED_RING_HASHES = {
    RING_CONFIG_PATH: "c78248ebd91194730a5e6ae045970de64321508af8c871b0bc79314871e48d5e",
    RING_CSS_PATH: "73fab272f1ab3ce8c4c19208e1fc727a0af25ed23ad616b2f9058e8a79fd0399",
}
REQUIRED_GUIDES = {
    "docker-platform",
    "nginx-proxy-manager",
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
    entries = reference.get("entries", [])
    ids = {entry.get("id") for entry in entries}
    host_recovery_id = "host-recovery-prerequisites"
    restore_harbr_id = "restore-harbr"
    docker_platform_id = "docker-platform"
    nginx_proxy_manager_id = "nginx-proxy-manager"
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
        "9. Confirm that the host is ready to restore Harbr",
        "10. Identify restoring Harbr as the next recovery step",
    ]
    restore_harbr_headings = [
        "1. Locate the verified Harbr recovery source",
        "2. Restore the Harbr application",
        "3. Restore the Harbr configuration",
        "4. Start Harbr",
        "5. Verify the Recovery Center is available",
        "6. Verify recovery evidence",
        "7. Verify operator access",
        "8. Confirm Harbr is ready to guide recovery",
        "9. Identify the next recovery step",
    ]
    docker_platform_headings = [
        "1. Verify Harbr remains operational",
        "2. Review the protected Docker inventory",
        "3. Restore the expected Docker directory structure",
        "4. Restore shared Docker configuration",
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
    require(len(ids) == len(entries), "Recovery Center entry IDs must be unique")
    for entry in entries:
        require(entry.get("title") and entry.get("summary"), f"Incomplete guide metadata: {entry.get('id')}")
        if entry.get("id") in {host_recovery_id, restore_harbr_id, docker_platform_id, nginx_proxy_manager_id}:
            is_host_recovery = entry.get("id") == host_recovery_id
            is_restore_harbr = entry.get("id") == restore_harbr_id
            is_docker_platform = entry.get("id") == docker_platform_id
            if is_host_recovery:
                expected_title = "Host Recovery"
                expected_headings = host_recovery_headings
            elif is_restore_harbr:
                expected_title = "Restore Harbr"
                expected_headings = restore_harbr_headings
            elif is_docker_platform:
                expected_title = "Docker Platform"
                expected_headings = docker_platform_headings
            else:
                expected_title = "Nginx Proxy Manager"
                expected_headings = nginx_proxy_manager_headings
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
                readiness_step = "\n".join(sections_by_heading[host_recovery_headings[8]]["paragraphs"])
                require("Automatic checks alone do not authorize restoration" in readiness_step, "Host Recovery must distinguish automatic checks from restore authorization")
                for material in ("verified backup archive", "trusted Harbr source", "protected configuration", "secure credentials"):
                    require(material in readiness_step, f"Host Recovery manual readiness confirmation is missing: {material}")
            elif is_restore_harbr:
                require(entry.get("summary") == "Restore Harbr and verify that the recovery console is operational.", "Restore Harbr has the wrong summary")
                application_step = "\n".join(sections_by_heading[restore_harbr_headings[1]]["paragraphs"])
                require("/srv/docker/harbr" in application_step and "harbr-experience" in application_step, "Restore Harbr must verify the isolated application location")
                center_step = "\n".join(sections_by_heading[restore_harbr_headings[4]]["paragraphs"])
                require('entries[0].id == "host-recovery-prerequisites"' in center_step, "Restore Harbr must verify Host Recovery availability")
                evidence_step = "\n".join(sections_by_heading[restore_harbr_headings[5]]["paragraphs"])
                require("do not infer or calculate confidence" in evidence_step, "Restore Harbr must preserve explicit evidence states")
                guidance_step = "\n".join(sections_by_heading[restore_harbr_headings[7]]["paragraphs"])
                for marker in ("harbr-experience", "Recovery Center", "api/v1/index.json", "MANAGEMENT_IP", "Harbr is ready to guide recovery"):
                    require(marker in guidance_step, f"Restore Harbr guidance-readiness check is missing: {marker}")
                next_step = "\n".join(sections_by_heading[restore_harbr_headings[8]]["paragraphs"])
                require("Next Recovery Step" in next_step and "Restore the Docker Platform." in next_step, "Restore Harbr must identify the next recovery step")
            elif is_docker_platform:
                require(entry.get("summary") == "Restore and verify the shared Docker environment required before application recovery can begin.", "Docker Platform has the wrong summary")
                inventory_step = "\n".join(sections_by_heading[docker_platform_headings[1]]["paragraphs"])
                require("Do not substitute docker ps" in inventory_step, "Docker Platform must treat protected evidence as authoritative")
                commands = "\n".join(section["paragraphs"][1] for section in sections)
                for forbidden_command in ("docker compose up", "docker compose start", "docker start", "docker restart"):
                    require(forbidden_command not in commands, f"Docker Platform must not start application stacks: {forbidden_command}")
                readiness_step = "\n".join(sections_by_heading[docker_platform_headings[8]]["paragraphs"])
                for marker in ("harbr-experience", "systemctl is-active", "sudo -u chris docker info", "config --quiet", "Automatic checks alone do not authorize application recovery"):
                    require(marker in readiness_step, f"Docker Platform readiness check is missing: {marker}")
                next_step = "\n".join(sections_by_heading[docker_platform_headings[9]]["paragraphs"])
                require("no authoritative application recovery order" in next_step.lower(), "Docker Platform must not fabricate an application recovery order")
                require("Manual operator selection required" in next_step, "Docker Platform must require manual selection without authoritative order metadata")
            else:
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
    require("site confidence story history coverage system inventory index" in refresh, "Inventory is not atomically published")
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
    validate_refresh_deployment()
    print("Harbr validation passed")


if __name__ == "__main__":
    main()
