# ADR-004: Shared Experience Foundation for Web, PWA, and Native Mobile

- Status: Accepted
- Date: 2026-08-03
- Product: Harbr 1.0

## Context

Harbr must feel like one product across desktop web, mobile web, a Home Screen PWA, and a future native mobile application.

## Decision

Harbr's interaction model, vocabulary, information hierarchy, Seasons, Confidence Ring behavior, and data contracts will be platform-independent.

The web experience will be responsive and touch-first. It will consume the same versioned Harbr API intended for future native clients.

The first Experience milestone may use static fixture data, but it must not bind presentation to Docker, shell scripts, or local backup paths.

## Consequences

The native application can reproduce the established Harbr experience without redesigning product concepts or backend contracts.
