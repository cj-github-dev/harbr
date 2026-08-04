# Harbr

**Recovery begins with confidence.**

Harbr is a read-only recovery-confidence platform.

Its purpose is to answer one question:

> Can I recover right now?

Harbr 1.0 Founder's Edition begins with the Lac du Flambeau site and the
existing Docker backup implementation.

## Architecture

Harbr is divided into four layers:

1. **Core**
   - Converts implementation-specific backup facts into Harbr concepts.
   - Calculates Restore Confidence.
   - Produces versioned, sanitized data.

2. **API**
   - Publishes read-only JSON documents.
   - Is consumed by the web interface, PWA, and future native mobile apps.

3. **UI**
   - Presents the Harbr experience.
   - Does not inspect Docker, systemd, rclone, backup archives, or host files.

4. **Plugins**
   - Adapt implementation-specific systems to Harbr.
   - The first plugin is the Docker backup implementation.

## Product vocabulary

- Confidence Ring
- Restore Confidence
- Confidence History
- Backup Story
- Protection Coverage
- Reference Center
- Seasons

## Security

Harbr publishes sanitized operational status only.

It must never publish:

- credentials;
- tokens;
- webhook identifiers;
- internal IP addresses;
- environment variables;
- raw logs;
- archive downloads;
- local backup paths;
- recovery secrets.

## Current site

- Site ID: `LDF`
- Name: Lac du Flambeau
- Edition: Founder's Edition
