#!/usr/bin/env python3
"""Translate the approved Confidence Ring Lab export into production CSS."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "ui" / "experience" / "config" / "confidence-ring.json"
OUTPUT_PATH = ROOT / "ui" / "experience" / "config" / "confidence-ring.generated.css"

MAPPINGS = {
    "breathing_amplitude_percent": ("--ring-breathing-amplitude", lambda value: f"{value / 100:g}"),
    "breathing_period_seconds": ("--ring-breathing-period", lambda value: f"{value:g}s"),
    "confidence_sweep_period_seconds": ("--confidence-sweep-period", lambda value: f"{value:g}s"),
    "aura_radius_pixels": ("--ring-aura-radius", lambda value: f"{value:g}px"),
    "aura_intensity": ("--ring-aura-intensity", lambda value: f"{value:g}"),
    "ripple_period_seconds": ("--ring-ripple-period", lambda value: f"{value:g}s"),
    "ripple_opacity": ("--ring-ripple-opacity", lambda value: f"{value:g}"),
    "ripple_scale": ("--ring-ripple-scale", lambda value: f"{value:g}"),
    "buoyancy_amount_pixels": ("--ring-buoyancy-amount", lambda value: f"{value:g}px"),
    "buoyancy_period_seconds": ("--ring-buoyancy-period", lambda value: f"{value:g}s"),
    "bloom_intensity": ("--ring-bloom-intensity", lambda value: f"{value:g}"),
}


def render(config: dict) -> str:
    values = config["values"]
    missing = MAPPINGS.keys() - values.keys()
    unknown = values.keys() - MAPPINGS.keys()
    if missing or unknown:
        raise ValueError(f"Configuration mapping mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}")

    declarations = [
        f"  {css_name}: {formatter(values[json_name])};"
        for json_name, (css_name, formatter) in MAPPINGS.items()
    ]
    ripple_period = values["ripple_period_seconds"]
    buoyancy = values["buoyancy_amount_pixels"]
    declarations.extend([
        f"  --ring-ripple-delay-2: {ripple_period * 0.2:g}s;",
        f"  --ring-ripple-delay-3: {ripple_period * 0.4:g}s;",
        f"  --ring-ripple-delay-4: {ripple_period * 0.6:g}s;",
        f"  --ring-ripple-delay-5: {ripple_period * 0.8:g}s;",
        f"  --ring-buoyancy-half: {buoyancy * 0.5:g}px;",
        f"  --ring-buoyancy-negative: {-buoyancy:g}px;",
        f"  --ring-buoyancy-negative-half: {-buoyancy * 0.5:g}px;",
    ])
    return "\n".join([
        "/* Generated from config/confidence-ring.json. Do not edit directly. */",
        ":root {",
        *declarations,
        "}",
        "",
    ])


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1 or config.get("approved") is not True:
        raise ValueError("Confidence Ring configuration must be approved schema version 1")
    OUTPUT_PATH.write_text(render(config), encoding="utf-8", newline="\n")
    print(f"Generated {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
