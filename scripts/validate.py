#!/usr/bin/env python3
"""Dependency-free structural validation for the Harbr web experience."""

from __future__ import annotations

import json
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
REQUIRED_GUIDES = {
    "restore-guide",
    "verification-chain",
    "backup-retention",
    "offsite-sync",
    "confidence-methodology",
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


def validate_startup() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    app = APP_PATH.read_text(encoding="utf-8")
    for marker in ('id="startup-icon"', 'id="startup-wordmark"', 'id="startup-tagline"'):
        require(marker in html, f"Startup markup missing {marker}")
    for marker in ("icon-away", "wordmark-away", "endingStart + 1500"):
        require(marker in app, f"Startup sequence missing {marker}")


def validate_archives() -> None:
    app = APP_PATH.read_text(encoding="utf-8")
    for marker in (
        "button.dataset.backupId",
        "aria-pressed",
        "selectArchive",
        "renderHistoricalView",
        "Viewing archive from",
    ):
        require(marker in app, f"Archive interaction missing {marker}")

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
    require(REQUIRED_GUIDES <= ids, f"Missing guides: {sorted(REQUIRED_GUIDES - ids)}")
    for entry in entries:
        require(entry.get("title") and entry.get("summary"), f"Incomplete guide metadata: {entry.get('id')}")
        require(entry.get("sections"), f"Guide has no sections: {entry.get('id')}")
        for section in entry["sections"]:
            require(section.get("heading") and section.get("paragraphs"), f"Incomplete section in {entry.get('id')}")


def main() -> None:
    validate_json()
    validate_internal_resources()
    validate_confidence_ring_config()
    validate_startup()
    validate_archives()
    validate_documentation()
    print("Harbr validation passed")


if __name__ == "__main__":
    main()
