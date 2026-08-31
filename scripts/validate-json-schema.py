#!/usr/bin/env python3
"""Validate Harbr JSON fixtures against the repository's schema subset."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


def validate(instance, schema, root, path="$", errors=None):
    errors = errors if errors is not None else []
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return validate(instance, target, root, path, errors)
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value is outside enum")
    allowed = schema.get("type")
    if allowed:
        allowed = [allowed] if isinstance(allowed, str) else allowed
        checks = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
                  "string": lambda v: isinstance(v, str), "null": lambda v: v is None,
                  "boolean": lambda v: isinstance(v, bool),
                  "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                  "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}
        if not any(checks[k](instance) for k in allowed):
            errors.append(f"{path}: expected {' or '.join(allowed)}")
            return errors
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance: errors.append(f"{path}: missing {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance.keys() - properties.keys(): errors.append(f"{path}: unexpected {key}")
        for key, child in instance.items():
            if key in properties: validate(child, properties[key], root, f"{path}.{key}", errors)
    if isinstance(instance, list) and "items" in schema:
        for index, child in enumerate(instance): validate(child, schema["items"], root, f"{path}[{index}]", errors)
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0): errors.append(f"{path}: string is too short")
        if schema.get("format") == "date-time":
            try: datetime.fromisoformat(instance.replace("Z", "+00:00"))
            except ValueError: errors.append(f"{path}: invalid date-time")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]: errors.append(f"{path}: below minimum")
        if "maximum" in schema and instance > schema["maximum"]: errors.append(f"{path}: above maximum")
    return errors


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate-json-schema.py SCHEMA JSON")
    schema = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    instance = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    errors = validate(instance, schema, schema)
    if errors: raise SystemExit("\n".join(errors))
    print(f"Schema validation passed: {sys.argv[2]}")


if __name__ == "__main__": main()
