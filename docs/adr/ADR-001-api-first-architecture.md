# ADR-001: API-First Architecture

- Status: Accepted
- Date: 2026-08-03
- Product: Harbr 1.0
- Edition: Founder's Edition

## Context

Harbr begins by presenting recovery confidence for the Lac du Flambeau Docker environment.

The existing implementation uses Docker, shell scripts, systemd, rclone, Microsoft OneDrive, Home Assistant, and filesystem-based status records.

Harbr must not become permanently coupled to those implementation details.

The product is expected to support desktop browsers, mobile browsers, Progressive Web App installation, a future native mobile application, multiple protected sites, and potentially additional backup platforms.

## Decision

Harbr will use an API-first architecture.

The Harbr user interface will consume only versioned, sanitized Harbr data contracts.

The user interface will not directly read:

- Docker
- systemd
- rclone
- Home Assistant
- backup archives
- host logs
- local backup directories
- implementation-specific status files

Harbr Core will convert implementation-specific facts into Harbr concepts.

The first public contract version is `/api/v1/`.

Initial resources are:

- `/api/v1/site.json`
- `/api/v1/confidence.json`
- `/api/v1/story.json`
- `/api/v1/history.json`
- `/api/v1/coverage.json`
- `/api/v1/system.json`
- `/api/v1/index.json`

The first implementation adapter resides under `plugins/docker/`.

The web interface, PWA, and future native mobile applications consume the same API contracts.

## Data ownership

Harbr Core owns:

- Restore Confidence level
- Restore Confidence explanation
- Confidence History
- Backup Story
- Protection Coverage
- sanitized backup history
- site identity
- seasonal presentation metadata

The user interface owns:

- layout
- typography
- animation
- responsive behavior
- accessibility presentation
- seasonal visual rendering
- Confidence Ring presentation

The user interface does not calculate Restore Confidence.

## Security boundary

Only sanitized data may be published through the Harbr API.

The API must not expose:

- secrets
- credentials
- authentication tokens
- webhook identifiers
- internal IP addresses
- environment variables
- raw logs
- local filesystem paths
- archive downloads
- Microsoft account information
- executable administrative actions

## Consequences

### Positive

- Web and native mobile clients share the same contracts.
- Harbr can support multiple sites without redesigning the interface.
- Docker remains an implementation rather than the product identity.
- Backup logic and product presentation can evolve independently.
- Security review is simplified because published data is explicit.
- API versions can evolve without silently breaking clients.

### Negative

- A translation layer is required between the existing backup implementation and Harbr.
- Data contracts must be deliberately maintained.
- Changes to published structures require versioning discipline.

## Alternatives considered

### UI directly reads backup status files

Rejected because it couples the product experience to the current shell-script implementation.

### UI directly queries Docker and rclone

Rejected because it exposes infrastructure details and makes native-app support substantially harder.

### Build the web interface first and define an API later

Rejected because this would allow implementation details to leak into the user interface and would likely require a redesign for mobile clients.

## Result

Harbr will be built from the data contract outward.

Every Harbr client receives the same recovery-confidence model regardless of which underlying system produced it.
