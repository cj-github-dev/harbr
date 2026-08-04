# Harbr

**Recovery begins with confidence.**

Harbr is a read-only recovery-confidence platform.

Its purpose is to answer one question:

> Can I recover right now?

Harbr v4 Founder's Edition begins with the Lac du Flambeau site and the
existing Docker backup implementation.

## Web experience

The interface is intentionally small: plain HTML, CSS, JavaScript, and JSON.
It has no package dependencies, build step, or generated frontend output.

The Docker Compose service exposes the UI and read-only JSON API together.
Run `docker compose up -d`, then open `http://localhost:8088`. The experience
reads live documents from `/api/v1/`; it never inspects the host directly.

The v4 experience retains Harbr's startup animation, Confidence Ring,
seasonal landscape, glass surfaces, typography, and responsive navigation.

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
