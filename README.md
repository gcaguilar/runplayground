# Run

A self-hosted, open-source running dashboard that reads your own Garmin data
and explains fitness, progress, race potential and training priorities. One
place for the numbers, with their provenance and confidence — not another
metric dump.

> **Status: M2 — diagnostics and training.** Sync, import, activities,
> weekly summary and data audit work. Performance turns your efforts into
> 5K/10K/half/marathon predictions with ranges and confidence. Diagnostics
> scores six training dimensions and explains every limiter; Training turns
> that reading and your goal into a conservative seven-day plan. Progress
> remains a placeholder for M3.

## What works today

- **Garmin sync** through the official Personal API: incremental sync,
  full backfill, and original FIT file download.
- **Manual import** of FIT, TCX and GPX files, individually or in batches.
- **Garmin bulk export** (ZIP) for historical VO₂max, Training Readiness,
  acute/chronic load and Garmin race predictions, plus any FIT files inside.
- **Performance predictions** for 5K, 10K, half and marathon. Each distance
  shows the official PR, the recent best effort, your goal, a speed ceiling
  (A), a distance-specific forecast (B), the A–B gap and an 80% range.
- **10K fitness anchor** and daily prediction snapshots to follow changes over
  time. Confidence is explicit and explains what is missing.
- **Diagnostics** across six dimensions: volume, consistency, intensity, load,
  recovery and specificity. Every score shows its status, confidence, evidence
  and reason codes; missing data lowers confidence instead of inventing a value.
- **Intensity and load analysis**: approximate easy/moderate/hard distribution
  from pace relative to the 10K anchor (HR fallback), plus a transparent
  internally estimated load model, acute/chronic ratio and a 12-week chart.
- **Limiting factors and weekly training plan**: ranked limiters, a conservative
  seven-day plan for the current phase (maintenance, base, build, peak, taper or
  recovery), and weekly volume, long-run and quality targets. Garmin readiness
  and load remain reference-only and never change the diagnostics score.
- **Deduplication and provenance**: every activity records where it came
  from, when it was imported, its raw file hash and the parser version.
  Cross-format duplicates are merged instead of double-counted.
- **Activity library** with search, sport filter, sorting and pagination.
- **Activity detail** with pace/HR streams, route, laps, quality flags and
  editable name/race flag.
- **Weekly summary** with week-over-week comparisons.
- **Data audit** with a deterministic score, coverage by stream/HR/GPS/laps,
  suspicious data detection and race candidates.
- **Bilingual UI** (Spanish default, English) and metric/imperial units.
- **Optional password login** and a localhost-only Docker Compose setup.

## Quick start

Requirements: Docker with Compose v2.

```bash
cp .env.example .env
# edit .env if you have a Garmin Personal API key
docker compose up --build -d
```

Open <http://127.0.0.1:8080>.

Database migrations run automatically at container start. Data lives in the
`run-dashboard-data` Docker volume.

### Prebuilt image

GitHub Actions builds and publishes multi-arch images (amd64 and arm64) to
GitHub Container Registry on every push to `main` and on `v*` tags. To run the
published image instead of building locally:

```bash
docker compose pull
docker compose up -d
```

Tags include `latest`, `main`, the version tag and `sha-<commit>`. The publish
workflow lives in
[`.github/workflows/docker-image.yml`](.github/workflows/docker-image.yml).

### Garmin Personal API key

Run uses Garmin's official **Personal API**, not account scraping. Access is
requested through the [Garmin Connect developer
program](https://developer.garmin.com/gc-developer-program/). Once you have a
key, put it in `.env`:

```dotenv
GARMIN_PERSONAL_API_KEY=your-key
```

Then restart the container. The key is only read from the environment; it is
never stored in the database or exposed in the UI.

Without a key the dashboard still works: import FIT/TCX/GPX files from
**Importar**. The audit page tells you exactly what is missing.

### Garmin bulk export

Garmin Connect can also produce a one-off archive: **Settings → Data
Management → Export your data**. Download the ZIP and upload it from
**Importar → Export histórico de Garmin**. The dashboard reads VO₂max,
Training Readiness, acute/chronic load and Garmin's own race predictions, and
imports any FIT files contained in the archive. Re-uploading the same ZIP is
idempotent. These values appear as a separate Garmin reference; they do not
feed the internal A/B prediction models or the diagnostics score.

The dashboard syncs activities and their FIT files. Sleep, HRV, Body Battery
and weight are still outside the current scope.

### Try it without a watch

Sample files are included in `backend/tests/fixtures/`:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/imports \
  -F "files=@backend/tests/fixtures/sample.fit" \
  -F "files=@backend/tests/fixtures/sample.tcx" \
  -F "files=@backend/tests/fixtures/sample.gpx"
```

The three files describe different runs; the FIT file is the most complete.

## Configuration

All settings are environment variables, read from `.env` by Docker Compose.
See [`.env.example`](.env.example) for the full annotated list.

| Variable | Default | Purpose |
| --- | --- | --- |
| `GARMIN_PERSONAL_API_KEY` | — | Official Garmin API key. Empty disables sync. |
| `AUTH_MODE` | `none` | `none` or `password`. |
| `APP_PASSWORD` | — | Required when `AUTH_MODE=password`. |
| `SECRET_KEY` | — | Session signing key, at least 16 characters. Required with password auth. |
| `SESSION_DAYS` | `30` | Login session lifetime. |
| `SYNC_INTERVAL_HOURS` | `12` | Automatic sync interval. `0` disables the scheduler. |
| `SYNC_ON_STARTUP` | `false` | Run a sync when the container starts. |
| `SYNC_DOWNLOAD_FIT` | `true` | Keep the original FIT file for each activity. |
| `MAX_UPLOAD_MB` | `50` | Maximum size per imported FIT/TCX/GPX file. |
| `GARMIN_EXPORT_MAX_MB` | `500` | Maximum size of a Garmin bulk-export ZIP. |
| `DATA_DIR` | `/data` | Database and raw files. Do not change inside Docker. |
| `LOG_LEVEL` | `INFO` | Python log level. |

## Data, backups and privacy

Everything stays on your machine: SQLite plus the original files under
`$DATA_DIR`. Nothing is sent anywhere except requests to Garmin when you
configure a key. There is no telemetry and no third-party analytics.

Back up the named volume (stop the container first so SQLite and its WAL are
consistent):

```bash
docker compose stop
docker run --rm \
  -v run-dashboard-data:/data \
  -v "$PWD":/backup \
  alpine tar czf /backup/run-backup.tgz -C /data .
docker compose start
```

To keep the data in a normal folder instead, use a bind mount in
`docker-compose.yml`:

```yaml
    volumes:
      - ./data:/data
```

and make it writable by the container user (UID 1000):

```bash
mkdir -p data && sudo chown -R 1000:1000 data
```

Secrets never enter the database. `.env` is excluded from git and from the
Docker build context.

## Exposing the dashboard

By default the container publishes on `127.0.0.1:8080`, so only this machine
can reach it. That is deliberate: `AUTH_MODE=none` is safe only on localhost
or behind a trusted network such as Tailscale.

Before exposing it to a LAN or the internet:

1. Set `AUTH_MODE=password`, `APP_PASSWORD` and a random `SECRET_KEY`.
2. Change the port mapping to `8080:8080` (or put it behind a reverse proxy).
3. Terminate TLS at the reverse proxy. The app does not serve HTTPS itself.

## Development

Requirements: Python 3.12+ and [Bun](https://bun.sh) 1.4+.

Backend:

```bash
python -m venv .venv
.venv/bin/pip install -e "backend[dev]"

cd backend
DATA_DIR=../data ../.venv/bin/alembic upgrade head
DATA_DIR=../data ../.venv/bin/uvicorn app.main:app --reload --port 8080
```

Frontend (Vite dev server with API proxy):

```bash
cd frontend
bun install
bun run dev
```

Open <http://127.0.0.1:5173>. To serve the built SPA from FastAPI instead,
run `bun run build` and start uvicorn with `STATIC_DIR=../frontend/dist`.

Checks:

```bash
.venv/bin/pytest
.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
cd frontend && bun run typecheck && bun run build
```

After changing the API schema, regenerate the checked-in contract and types:

```bash
cd backend && ../.venv/bin/python -m app.cli export-openapi
cd ../frontend && bun run api:types
```

### Layout

```
backend/
  app/
    api/          HTTP endpoints (activities, imports, sync, audit, …)
    services/     Garmin client, sync, parsers, ingestion, audit
    models.py     SQLAlchemy models
    schemas.py    API contracts (source of the OpenAPI file)
  alembic/        Schema migrations
  tests/          Backend tests and FIT/TCX/GPX fixtures
frontend/
  src/
    pages/        One component per section
    components/   Shell, tables, charts, map, shared UI
    api/          Typed client, generated schema, React Query hooks
    i18n.tsx      ES/EN dictionary
scripts/          Container entrypoint
```

The API is a single FastAPI process with an in-process sync scheduler, so run
exactly one worker/replica. SQLite and the scheduler are deliberate choices
for a single-user instance; horizontal scaling is not a goal.

## Design principles

- **No fake precision.** Estimates carry their source, date and confidence
  range when the data supports one. Measured and derived values are labelled
  differently.
- **Provenance first.** Imports are fingerprint-deduplicated and every
  activity can be traced back to a source and file hash.
- **Missing data lowers confidence**, it does not silently produce a number.
- **Local by default.** No account, no cloud, no telemetry.

## Roadmap

| Milestone | Scope |
| --- | --- |
| **M0** | Infrastructure, Garmin sync, FIT/TCX/GPX import, activities, weekly summary, audit, Docker. |
| **M1** | Performance and race predictions, recent best efforts, historical Garmin metrics from the bulk export, 10K fitness anchor. |
| **M2** | Diagnostics and training analysis: six dimensions, intensity distribution, load, limiting factors, recommendations. **Current.** |
| **M3** | Progress views, goals, calendar, reports and race planning. |
| **M4** | Future scenarios, continuous tracking of predictions and goals. |

## License and disclaimer

Licensed under the [GNU General Public License v3.0 or
later](LICENSE). Not affiliated with, endorsed by, or supported by Garmin.
Garmin and Garmin Connect are trademarks of Garmin Ltd. Use your own data at
your own risk; nothing here is medical advice.
