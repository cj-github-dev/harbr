# ADR-003: Docker Integration Through an Adapter

- Status: Accepted
- Date: 2026-08-03
- Product: Harbr 1.0

## Context

Harbr's first protected environment is the existing Lac du Flambeau Docker backup system.

The backup engine already produces trusted local status and history files. Harbr must consume those facts without coupling the user interface to Docker, shell scripts, rclone, systemd, or local backup paths.

## Decision

The first implementation integration will be a Docker adapter under:

`plugins/docker/`

The adapter translates implementation-specific facts into the Harbr v1 API contracts.

The adapter may read:

- the existing backup status file;
- the existing backup history file;
- sanitized retention counts;
- the systemd timer's next scheduled run;
- the Harbr site configuration.

The adapter writes only the versioned Harbr API documents.

It does not modify backup archives, backup policy, Docker containers, OneDrive data, Home Assistant, or the backup schedule.

## Consequences

Harbr can evolve independently from the existing backup engine.

Future integrations may implement their own adapters while publishing the same Harbr contracts.
