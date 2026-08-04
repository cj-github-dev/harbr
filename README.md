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

### Confidence Ring configuration

`ui/experience/config/confidence-ring.json` is the authoritative approved
export from the Confidence Ring Lab. Future visual or motion tuning begins in
the Lab; after approval, export the complete configuration into that file and
run `python scripts/generate-confidence-ring-css.py`. The generated
`confidence-ring.generated.css` maps every exported value to shared production
CSS custom properties and must not be edited directly. Repository validation
fails when the export, mapping, and generated CSS drift apart.

The Lab term `living-light` is named **Confidence Sweep** in the product. Its
rotation period comes directly from the approved export. The production-only
orbit inset and mask geometry move the sweep outside the central copy so it
cannot overlap the label, confidence level, or explanation; this is the sole
approved visual departure from the exported configuration.

All values in the current schema-version-1 export are consumed by the
production ring. If a future export introduces a value that production cannot
yet use, preserve it in the JSON and document the reason here before updating
the explicit generator mapping—never silently discard it or add a preset.

First-party Reference Center guides live in
`ui/experience/data/reference.json`. The format is intentionally plain JSON:
each entry has a stable ID, title, summary, and ordered sections containing
headings and paragraphs. The UI also presents every resource published by the
API index with a formatted view and raw JSON view.

## Historical snapshots

`/api/v1/history.json` remains backward-compatible and keeps the existing run
metrics at the top level. A run may additionally include a `snapshot` with the
confidence evidence, backup story, and protection coverage recorded for that
point in time. The contract is defined in
`contracts/v1/history.schema.json`.

The Docker adapter builds confidence and story snapshots from each source
history record. It attaches current coverage to the newest run because that
coverage is measured during the same API generation. Older source records do
not contain retention counts, so their snapshot coverage is explicitly `null`
instead of borrowing the current value.

## Validation

Run the dependency-free repository validation with:

```powershell
python scripts/validate.py
node --check ui/experience/app.js
```

The repository validator checks JSON parsing, internal resources, startup
sequence markup, archive interaction hooks, historical snapshots, and the
required first-party documentation set. It also confirms that every Confidence
Ring export value has exactly one mapping and that the generated CSS is current.
JavaScript syntax is checked directly by the browser-compatible Node parser
without adding a project dependency.

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
