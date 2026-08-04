# ADR-002: Harbr Core Owns Restore Confidence

- Status: Accepted
- Date: 2026-08-03
- Product: Harbr 1.0

## Context

Restore Confidence is Harbr's primary product concept.

Different clients will present Restore Confidence:

- desktop web;
- mobile web;
- PWA;
- future native mobile applications;
- Home Assistant notifications.

If each client independently calculates Restore Confidence, clients may disagree about whether a site is protected.

## Decision

Harbr Core is the only component permitted to calculate Restore Confidence.

Clients receive:

- confidence level;
- explanation;
- verification checks;
- last verified time;
- seven-day history.

Clients may format and animate the result but may not reinterpret it.

## Initial levels

- High
- Moderate
- Low
- Unknown

## Consequences

All Harbr clients communicate the same recovery state.

Changes to Restore Confidence logic occur in one place and can be tested independently from presentation.
