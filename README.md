# Run

A self-hosted, open-source running dashboard that reads your own Garmin data
and explains fitness, progress, race potential and training priorities. One
place for the numbers, with their provenance and confidence — not another
metric dump.

> **Status: M13 — portability and operation.** The dashboard opens with the
> current 10K fitness anchor, its 4/8/12-week evolution, the four distance
> predictions, a weekly message, the main strength, the main limitation and
> the next action. Sync, import, activities, weekly summary and data audit
> work. Performance turns your efforts into 5K/10K/half/marathon predictions
> with ranges and confidence. Diagnostics scores six training dimensions and
> explains every limiter; Training turns that reading and your goal into a
> conservative seven-day plan. Progress adds trends, personal bests, goals and
> named races, plus a pace–heart-rate comparison that groups similar aerobic
> runs and asks whether you are faster at the same effort. The calendar merges
> real activities, suggested sessions and planned races; reports are generated
> on demand for any week or month. Scenarios compare four 8- or 12-week
> training hypotheses with explicit assumptions, capped effects and the
> projected goal gap; Tracking compares past predictions with real results,
> follows goal revisions and training actions, and pairs training factors with
> fitness changes as associations. The briefing composes those views instead
> of repeating them. Comparison puts two sessions side by side, states whether
> they are comparable, and only reads the difference when the data supports it.
> Reports open with a derived period reading: the strongest measured change,
> the current main limitation and the next action, with an explicit fallback
> when there are not enough fitness snapshots. Recovery adds sleep, HRV,
> resting heart rate, Body Battery and weight from the Garmin data export; it
> is context only and never changes the fitness or diagnostics scores. Training
> reconstructs what the suggested plan would have asked each recent week and
> compares it with actual volume, long run, hard sessions and rest; the current
> week stays in progress. Analysis settings add persistent max, resting and
> threshold heart rates plus a threshold pace and an auto/pace/HR classification
> mode, always showing what was observed, what was set by hand and what is
> actually used. Any running activity can be corrected to easy, moderate or hard
> and given an RPE; the correction feeds the analysis views but never rewrites
> the 10K anchor, best efforts or predictions. You can register your own plan
> with dated sessions, mark them completed or skipped, link real activities and
> read adherence against those exact targets; while a plan is active it replaces
> the suggested sessions in the calendar. The Backup page downloads a consistent
> archive, validates an uploaded ZIP without touching live data, stages a restore
> for the next startup and reports pending status. Polite in-app notifications
> announce completed syncs and imports.

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
- **Future scenarios**: maintain, improve consistency, add specific work or
  deload, projected over 8 or 12 weeks. Every scenario shows its starting
  assumptions, evidence, capped modelled effect and widening 80% range. The
  focus distance comes from the next goal or race, otherwise 10K. When there
  is a target, every scenario also shows the conditional gap and whether it
  would be ahead, close or behind; it is never a probability of achieving it.
- **Continuous tracking**: daily snapshots are compared with the first real
  result after them, up to 90 days later, to report bias, mean absolute error
  and how often the result fell inside the 80% range. Training efforts are
  marked separately from races.
- **Goal and action follow-up**: every target change is a revision with the
  prediction in force at the time; goals show their 28-day trend, gap and the
  actual race or best-effort results overlaid on the prediction history.
  Recommendations can be marked pending, in progress or completed, with a
  baseline score so later improvement, stability or decline is explicit.
- **Association analysis**: weekly volume, sessions, longest run, hard
  sessions, active days and estimated load are paired with the change in the
  10K fitness anchor. Each factor reports its correlation, a median split and
  the number of paired weeks; it is explicitly an association, not a cause.
- **Registered training plan**: a stored plan with a date range, an optional
  goal race, dated sessions (type, intensity, distance or duration, notes) and
  a single active plan. Sessions can be created one by one or in an atomic
  batch of up to 400, marked completed or skipped, and linked to a real
  activity; a linked activity marks the session completed and can only satisfy
  one session. While the plan covers a week, the calendar shows its sessions
  instead of the suggestion and adherence scores those exact targets; outside
  the range, or with no active plan, the suggested plan is used unchanged.
- **Suggested-plan adherence**: the training page reconstructs the plan that
  each recent week would have received from the phase and 28-day base volume,
  then compares actual volume, longest run, hard sessions and rest against it.
  The current week is shown in progress and excluded; the score is explicit
  that the plan is derived and that adherence is a heuristic.
- **Analysis settings and manual corrections**: global max, resting and
  threshold heart rates, a threshold pace and an auto/pace/HR classification
  mode. The settings page separates observed, manual and effective values with
  a source for each field; a threshold heart rate is derived from max HR and
  never presented as measured. A running activity can be corrected to easy,
  moderate or hard and tagged with an RPE 1–10. The corrections feed
  diagnostics, intensity, load, plan, calendar, reports, adherence, tracking,
  comparable runs and driver analysis, while performance, best efforts and
  prediction snapshots keep using the observed 10K anchor.
- **Recovery context**: sleep duration and score, HRV, resting heart rate,
  Body Battery and weight imported from the Garmin data export. Each metric
  shows its latest value, 7/28-day averages, 28-day change and coverage. The
  page states explicitly that recovery is context and does not feed the
  fitness, prediction or diagnostics models.
- **Workout comparison**: two sessions side by side with distance, duration,
  pace, heart rate, cadence, power, elevation, training effect and load. The
  page scores comparability first, lists why it is limited, and only computes
  one-kilometre splits when both sessions have distance and elapsed streams.
- **Weekly briefing** on the dashboard: current 10K fitness with its 80%
  range, 4/8/12-week evolution, the four distance predictions, a rule-based
  weekly message backed by visible evidence, the strongest dimension, the
  top limiter and the next action. Missing history or a weak signal lowers
  confidence instead of inventing a conclusion.
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
- **Progress and consistency**: weekly distance and estimated load, the daily
  10K fitness trend with its 80% range, streak and active-day stats, personal
  bests per standard distance, goal progress against the B forecast, and
  period highlights.
- **Pace–heart-rate comparison**: aerobic runs are grouped by distance band
  and terrain. Each group removes the within-group heart-rate effect, compares
  the earlier and recent halves, and reports the pace change at the same heart
  rate with a confidence score. Hard sessions and races are excluded; narrow
  HR ranges or small samples lower confidence instead of producing a trend.
- **Calendar and race planning**: real activities, suggested sessions from the
  current plan and several named races in one Monday–Sunday grid. Races carry
  priority A/B/C, an optional time goal, a location, notes and an optional link
  to the activity that completed them. Planned races are the only stored M3
  input; the calendar and its sessions are derived.
- **Weekly and monthly reports**: totals, deltas, daily/weekly volume, load,
  sessions by sport, goal gaps, races and period highlights. Each report opens
  with a derived reading: main improvement, current limitation and suggested
  action. Reports are built when requested and never persisted.
- **Deduplication and provenance**: every activity records where it came
  from, when it was imported, its raw file hash and the parser version.
  Cross-format duplicates are merged instead of double-counted.
- **Activity library** with search, sport filter, sorting and pagination.
- **Activity detail** with pace/HR streams, route, laps, quality flags and
  editable name/race flag.
- **Weekly summary** with week-over-week comparisons.
- **Data audit** with a deterministic score, coverage by stream/HR/GPS/laps,
  suspicious data detection and race candidates.
- **Portable backups and safe restore**: one ZIP with a consistent SQLite
  snapshot (taken with the sqlite3 backup API, WAL included), every raw file
  referenced by the database, readable CSV/JSON exports and a manifest with the
  Alembic revision, row counts and SHA-256 checksums. Uploads are validated
  against path traversal, symlinks, zip bombs, size limits, checksums, expected
  tables and revision compatibility. A restore is staged under
  `DATA_DIR/restore/pending`; startup replaces the database and raw files
  atomically after keeping `run.db.pre-restore-<timestamp>`.
- **Polite notifications** for completed syncs, imports, backups and restore
  actions, with links to Data quality or Settings and the last seen run stored
  in the browser.
- **Bilingual UI** (Spanish default, English) and metric/imperial units.
- **Optional password login** and a localhost-only Docker Compose setup.

### Scenarios and tracking

Scenarios are conditional simulations, not forecasts. Each one changes a
single training assumption for the next 8 or 12 weeks and projects the existing
prediction curve with a capped effect. Twelve weeks is deliberately less than
1.5× the eight-week effect: adaptation flattens and uncertainty grows faster
than the central estimate. The UI shows the assumptions, the current training
evidence, the confidence and the 80% range next to every number.

Tracking uses the daily prediction snapshots. For each real result at a
standard distance, the app picks the most recent snapshot at least one day
earlier and up to 90 days before it, then reports the signed error, mean
absolute error and range coverage. A best effort from training is included but
labelled as such; a small sample or a training result never becomes a
statistical validation.

Goal targets are append-only: saving a different target records what was asked
for and what the model predicted at that moment. Re-saving the same target
does not create noise. The goal chart overlays real races and best efforts on
the prediction line, so the distance between what the model expected and what
was actually run stays visible. Tracked actions store a baseline diagnostic
score when they are created, so a later review can say whether the related
dimension improved, stayed stable or got worse without claiming causality.

The association panel pairs each week of training with the fitness change
observed in that week's snapshot. It reports Pearson's correlation and the
average improvement when the factor was above or below its median. It needs at
least four paired weeks and labels small samples explicitly; a strong
correlation is still not evidence that the factor caused the improvement.

Narrative reports are derived, not generated prose. They compare the first and
last fitness snapshot inside the period, fall back to the volume delta when
there are fewer than two snapshots, pair the result with the current
diagnostics limiter and its recommended action, and state that the limitation
belongs to the current profile. The reading is rebuilt on every request and
never stored.

Recovery metrics come from the Garmin export and stay deliberately separate
from the performance models. The parser recognises sleep duration and score,
HRV, resting heart rate, Body Battery and weight from the wellness JSON files,
stores them as external metrics and tolerates nested or renamed fields. The
Recovery page shows the latest value, averages, change and coverage; an
incomplete or stale export lowers confidence instead of filling gaps. A bad
night is never read as a loss of fitness.

### Comparing two workouts

Comparison starts with a comparability check: different sports, a distance
ratio of 1.6 or more, or a large terrain gap make the pair non-comparable; a
smaller distance, duration or elevation gap makes it limited. Missing heart
rate, streams or cadence, or one race against one training run, are shown as
caveats. The page then reports summary differences and, when both sessions
have distance and elapsed streams, the pace and heart rate of each shared
kilometre. It never attributes the difference to a cause and does not treat
the comparison as a controlled test.

The pace–heart-rate comparison only uses aerobic runs of at least 4 km, groups
them by distance and terrain, and fits pace against heart rate inside each
group. It then compares the median heart-rate-adjusted pace of the earlier and
recent halves. Races and hard sessions are excluded because they answer a
different question. A narrow heart-rate range, fewer than six sessions or a
span under four weeks lowers confidence; the panel shows a provisional
sentence instead of a definitive gain.

The dashboard briefing is deliberately rule-based. It compares the current 10K
anchor with the closest snapshot before the 4-, 8- and 12-week cutoffs, picks
the top diagnostic limiter and writes one sentence from those facts. The
sentence is returned as a code plus parameters, and the underlying numbers and
evidence are always shown next to it. It never projects a result or replaces a
race.

### Analysis thresholds and manual corrections

The 10K anchor is measured, so it is not an input. Analysis settings calibrate
the reading around it: a maximum heart rate, a resting heart rate, an optional
threshold heart rate, a threshold pace and a classification mode. Every
response carries the observed value, the manual value, the effective value and
the source of each field. A threshold heart rate is never observed: if it is not
set by hand it is reported as missing, and HR classification falls back to max
HR. When no anchor exists the observed threshold pace is missing, not invented.
The classifier prefers pace in `auto`, can be forced to `pace` or `hr`, and
uses 0.95/0.85 cuts against a configured threshold HR or the conservative
0.85/0.75 cuts against max HR.

A running activity can override its automatic intensity and record an RPE from
1 to 10. The override wins over pace and heart rate everywhere the analysis
classifies sessions, and the detail page still shows the automatic result next
to it. It is deliberately not applied to best efforts, performance predictions
or stored snapshots: those answer what the athlete ran, while the correction
answers how the session should be read as training.

### Suggested-plan adherence

The plan is derived, so adherence is reconstructed, not read from a stored
calendar. For each week the app chooses the phase at that week's start, takes
the 28-day base volume before it, builds the same seven-day session template
and compares four things: weekly volume, longest run, hard sessions and rest
days. Volume and long-run range checks tolerate 10%; quality follows the phase
target; rest is derived from days without running. The current week is marked
in progress and excluded from the average, because a long run scheduled for
Saturday is not missed on Wednesday. The score is a heuristic and is labelled
as such.

### Registered plan and adherence by session

A registered plan is user-owned data instead of a reconstruction. It stores its
name, description, start and end dates, optional goal race, source, version and
one active flag; a SQLite partial unique index guarantees that only one plan is
active. Its sessions store the date, order, type, intensity, distance or
duration target, decision and optional activity. The same validation runs on
single and bulk writes: dates must fall inside the plan, rest has no targets,
every other type needs a distance or duration, skipped sessions cannot link an
activity and an activity cannot satisfy two sessions.

The calendar reads the active plan. Inside its date range, registered sessions
are shown as `plan` entries and the suggested sessions disappear; outside it,
the M3 suggestion is untouched. Planned distance only adds running sessions, so
strength, cross-training and rest never inflate the weekly total. Registered
sessions do not depend on activities existing: an unlinked session is still
planned or missed, not invisible.

Training adherence chooses its basis per week. If the active plan covers the
week, the volume, long-run, quality and rest targets come from its exact
sessions and each session gets an outcome (completed, skipped, missed or
pending) plus a distance compliance percentage. Weeks not covered keep the
M10 suggested engine, so a window can mix both and says so. The score keeps the
M10 weights (volume 45%, long run 30%, quality 15%, rest 10%), the current week
stays in progress with no score, and archived plans are ignored.

### Backup and restore

**Backup → Descargar copia** (or `GET /api/v1/backups/export`) builds a
temporary ZIP and streams it with a timestamped filename. The archive contains:

- `manifest.json` with the format version, app version, Alembic revision,
  creation time, row counts, per-file sizes and SHA-256 checksums, and warnings.
- `run.db`, a consistent snapshot made with the sqlite3 backup API. This is not
  a hot file copy: committed WAL pages are included and no half-written
  transaction can leak into the archive.
- `raw/…`, only the original files referenced by `raw_files`, with their stored
  paths.
- `exports/activities.{csv,json}`, `goals`, `races`, `actions` and
  `external_metrics`, so the data remains readable without Run.

The ZIP is written under `DATA_DIR/tmp`, bounded by `MAX_BACKUP_MB`, and deleted
after the response finishes. It never contains `.env`, tokens, keys or other
configuration. The database itself stores no secrets.

**Restore** is deliberately two-phase:

1. Upload the ZIP in **Backup → Validar y restaurar** (or
   `POST /api/v1/backups/validate`). Validation never writes to live data. It
   checks the manifest, every checksum, the Alembic revision against the
   running application, expected tables, SQLite integrity, raw paths, symlinks,
   entry count, uncompressed size and compression ratio. The endpoint returns a
   validation report; an archive with problems gets HTTP 400 and `valid: false`.
2. Type `RESTORE` and stage it (`POST /api/v1/backups/restore`). Run copies the
   archive to `DATA_DIR/restore/pending/` with a metadata file and returns. It
   refuses with HTTP 409 while a sync or import is running, or when another
   restore is already pending. The live database and raw files are not touched.
3. Restart the application. `scripts/entrypoint.sh` runs
   `python -m app.cli apply-restore` **before** `alembic upgrade head`. The CLI
   validates the pending archive again, writes
   `run.db.pre-restore-<timestamp>`, atomically replaces the database and the
   `raw/` directory, removes stale WAL/SHM files and writes
   `DATA_DIR/restore/last-restore.json`. The pending directory is then removed.

`GET /api/v1/backups/status` shows the pending archive, the last applied restore,
the current and expected revisions, active ingest work and configured limits.
`DELETE /api/v1/backups/pending` cancels a staged restore. If you run the
application outside Docker, stop it and apply the same step manually:

```bash
cd backend
DATA_DIR=../data ../.venv/bin/python -m app.cli apply-restore
DATA_DIR=../data ../.venv/bin/alembic upgrade head
```

Restores are strict about the Alembic revision: a backup from a different
schema version is rejected instead of being silently migrated. Keep the ZIP off
the server; it is a portable copy, not a substitute for a snapshot of the whole
Docker volume. If a restore is interrupted, the pre-restore database and the
pending metadata remain available for manual recovery.

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

The dashboard syncs activities and their FIT files. Sleep, HRV, resting heart
rate, Body Battery and weight are read from the Garmin data export and shown
as recovery context; they are not synced from the activity API and never change
the performance or diagnostics scores.

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
| `MAX_BACKUP_MB` | `4096` | Maximum uncompressed size of a generated backup. |
| `MAX_RESTORE_MB` | `1024` | Maximum compressed and uncompressed size of an uploaded restore. |
| `DATA_DIR` | `/data` | Database, raw files, temporary archives and restore staging. Do not change inside Docker. |
| `LOG_LEVEL` | `INFO` | Python log level. |

## Data, backups and privacy

Everything stays on your machine: SQLite plus the original files under
`$DATA_DIR`. Nothing is sent anywhere except requests to Garmin when you
configure a key. There is no telemetry and no third-party analytics.

For a portable copy, use **Backup → Descargar copia**. It reads a consistent
snapshot without stopping the container and includes the data plus the original
files in one archive. The in-app restore is validated before it is staged, and
only runs on the next startup. See [Backup and restore](#backup-and-restore).

For disaster recovery of the complete volume (including files Run does not
reference), stop the container first so SQLite and its WAL are consistent:

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

## Troubleshooting

### The container runs, but <http://127.0.0.1:8080> does not respond

Check that the port is actually published. The Compose file binds it
explicitly, but a container started with a bare `docker run` has no port
mapping:

```bash
docker compose ps
docker compose port run 8080    # should print 127.0.0.1:8080
```

Start the stack through Compose instead of `docker run`:

```bash
docker compose up -d
```

If Docker requires `sudo` on your machine, run the same commands with
`sudo` (or add your user to the `docker` group and log in again).

Other common causes:

- **Port 8080 is already in use.** `ss -ltn | grep 8080` shows the socket
  holding it. Stop that process or change the published port in
  `docker-compose.yml`.
- **The container exits during startup.** `docker compose logs run` shows the
  error; the usual culprit is a `/data` volume owned by another UID. With a
  bind mount, run `sudo chown -R 1000:1000 data`.
- **You are connecting from another device.** The default binding is
  `127.0.0.1`, so only this machine can reach it. See
  [Exposing the dashboard](#exposing-the-dashboard) before changing it.

The image health check probes `/api/v1/health` from inside the container, so
`docker compose ps` reporting `healthy` proves the app is up even when the
published port is wrong.

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
    services/     Garmin client, sync, parsers, ingestion, audit, backup/restore
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
| **M2** | Diagnostics and training analysis: six dimensions, intensity distribution, load, limiting factors, recommendations. |
| **M3** | Progress views, goals, calendar, weekly/monthly reports and race planning. |
| **M4** | Future scenarios, continuous tracking of predictions, goals and actions. |
| **M5** | Weekly briefing: current state, evolution, predictions, strength, limiter and next action. |
| **M6** | Comparable training: pace–heart-rate analysis by distance and terrain, with confidence and caveats. |
| **M7** | Workout comparison: side-by-side metrics, comparability check and one-kilometre splits. |
| **M8** | Narrative reports: derived main improvement, current limitation and suggested action per period. |
| **M9** | Recovery context: sleep, HRV, resting heart rate, Body Battery and weight from the Garmin export. |
| **M10** | Suggested-plan adherence: reconstructed weekly targets versus actual volume, long run, quality and rest. |
| **M11** | Analysis settings and manual corrections: persistent heart-rate/pace thresholds, classification mode and per-activity intensity override with RPE. |
| **M12** | Registered training plan: stored dated sessions, single active plan, atomic bulk create, activity linking and adherence by session. |
| **M13** | Portability and operation: consistent backup export, validated restore staging, startup apply with a pre-restore database, and polite notifications. **Current.** |

## License and disclaimer

Licensed under the [GNU General Public License v3.0 or
later](LICENSE). Not affiliated with, endorsed by, or supported by Garmin.
Garmin and Garmin Connect are trademarks of Garmin Ltd. Use your own data at
your own risk; nothing here is medical advice.
