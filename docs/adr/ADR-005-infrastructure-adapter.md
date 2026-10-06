# ADR-005: Normalized Infrastructure Through Collector Adapters

- Status: Accepted
- Date: 2026-08-31
- Product: Harbr 4.3

## Context

Harbr needs current operational and maintenance information across multiple
sites and unlike backup history this information expires quickly. The first
private collector, service-check, describes the LDF Docker host. Future sites
may use unrelated collectors for Synology, virtualization, Linux, or appliance
platforms.

## Decision

Harbr publishes one sanitized v1 aggregate at `/api/v1/infrastructure.json`.
Stable sites contain stable hosts; each host exposes only the capabilities it
has, including optional containers, platform services, storage, and explicit
virtual-machine entities. Collector-specific shapes terminate at adapters.

The service-check adapter reads its already-generated private document,
performs an allow-list transformation, validates in private build storage, and
atomically publishes as a non-root Harbr user. It performs no collection and
has no Docker socket requirement. Publication failure preserves the last valid
document.

The contract separates runtime status from maintenance/update status and uses
only Harbr's healthy, warning, failure, and unknown operational vocabulary.
Clients use `generated_at` and `stale_after_seconds` to downgrade stale data.
Infrastructure does not participate in Restore Confidence.

## Consequences

Additional sites and collectors can join by supplying normalized site/host
records without changing the browser contract. Private digests, addresses,
paths, logs, and credentials remain outside the public boundary. Deployment
must explicitly grant the Harbr publisher read access to each collector record.
