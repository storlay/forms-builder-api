# Forms / Survey Builder

A small, production-shaped backend that shows where MongoDB's document model genuinely pays off: **every form defines its own schema, and each response is validated at runtime against that schema** — no fixed columns, no EAV, no pile of nullable JSON fields.

Built as a focused demonstration of async FastAPI, the native async PyMongo driver (no ODM), Pydantic v2, GridFS, aggregation pipelines, and the operational glue around them (Docker, replica-set transactions, TTL indexes, keyset pagination).

<p>
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="MongoDB 7" src="https://img.shields.io/badge/MongoDB-7-47A248?logo=mongodb&logoColor=white">
  <img alt="Pydantic v2" src="https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white">
</p>

## The core idea

A form is a document holding an array of arbitrary field definitions. A response is a document holding values for those fields. In a relational store this collapses into entity-attribute-value tables or schema migrations per form; as documents it is just the natural shape of the data.

The interesting consequence: the validation schema isn't known ahead of time. On submit, the service loads the form's fields and builds a Pydantic model on the fly with `create_model()`, mapping each field type to a Python type plus constraints:

| Field type | Generated type / constraints |
|---|---|
| `short_text`, `long_text` | `str` + `min_length` / `max_length` / `pattern` |
| `email` | `str` + email pattern |
| `number` | `int \| float` + `ge` / `le` |
| `rating` | `int` + `ge` / `le` |
| `date` | `date` |
| `single_choice` | `Literal[*options]` |
| `multi_choice` | `list[Literal[*options]]` |
| `file` | GridFS reference, existence + ownership checked |

The model is built with `extra="forbid"`, so respondents can't smuggle unknown keys into the stored document, and Pydantic's own error report is reshaped into a clean `422`.

## Highlights

- **Runtime-built validation** — schema assembled from data, not hardcoded; partial mode reuses the same builder for draft saves.
- **Form versioning** — published forms are immutable; an edit bumps `version` and writes a snapshot to `form_versions`, so analytics over historical responses never break.
- **Keyset pagination** — cursor-based on `(submitted_at, _id)` with an opaque base64 cursor; no `$skip`, stable under concurrent writes.
- **`$facet` analytics** — one aggregation pass produces per-field summaries (choice counts, numeric stats, `$bucket` histograms with empty buckets back-filled) plus a daily timeline.
- **Streaming export** — CSV/JSON served via `StreamingResponse` straight off an async cursor, so memory stays flat regardless of response volume.
- **GridFS uploads** — files are streamed in/out and tied to their form; a response can't reference a file uploaded for a different form.
- **TTL drafts** — "save and continue later" responses expire themselves via a TTL index on `expires_at`.
- **Defensive authorization** — not-found and not-owned both return `404`, so form existence isn't disclosed to non-owners.
- **Rate-limited public surface** — anonymous submit/draft/upload endpoints run behind a per-IP sliding-window limiter, and uploads are read in capped chunks so an oversized body is rejected before it's buffered.

## Stack

- **Python 3.13** · **FastAPI** · **Gunicorn** with Uvicorn workers
- **MongoDB 7** as a single-node replica set (enables transactions for atomic submits)
- **PyMongo** `AsyncMongoClient` — the native async driver, no ODM; pipelines, GridFS and indexes are written by hand
- **Pydantic v2** + `pydantic-settings`
- Auth: **PyJWT** + `pwdlib[argon2]`
- **uv** (packaging) · **ruff** (lint/format) · **pytest** + `httpx` ASGI transport (tests run against a real Mongo)

## Architecture

Clean layering with dependency injection via `Depends`. The Mongo client lives in `app.state` and is opened/closed in the `lifespan` handler, where indexes are also ensured.

```
API (routers)  ->  services (business logic)  ->  repositories (Mongo access)  ->  MongoDB
```

```
app/
  main.py            # app factory, lifespan (connect + ensure_indexes), error handler
  core/              # config, security (JWT / argon2), db, exceptions, rate limiter
  models/            # domain models (Pydantic) — own the _id <-> id mapping
  schemas/           # request/response DTOs
  repositories/      # Mongo access: forms, responses, users, files (GridFS)
  services/          # forms, responses (dynamic validation), analytics, auth, files
  api/               # deps + routers (auth, forms, responses, files, analytics, health)
  db/indexes.py      # ensure_indexes() on startup
tests/               # pytest against the docker-compose Mongo
```

Domain errors subclass a single `AppError` carrying `status_code`/`detail`; one handler in `main.py` maps them to HTTP, so routers stay free of `try/except`.

### Indexes

| Collection | Index | Purpose |
|---|---|---|
| `users` | `{email: 1}` unique | login |
| `forms` | `{owner_id: 1, status: 1}` | owner's form list |
| `form_versions` | `{form_id: 1, version: 1}` unique | snapshot lookup |
| `responses` | `{form_id: 1, submitted_at: -1, _id: -1}` | pagination + sort |
| `responses` | `{form_id: 1, "answers.key": 1}` | field aggregations |
| `draft_responses` | `{expires_at: 1}` TTL (`expireAfterSeconds: 0`) | auto-delete drafts |

## Running

### Docker Compose (recommended)

Starts Mongo (auto-initializing the replica set via a healthcheck) and the app on Gunicorn:

```bash
docker compose up --build
```

API → http://localhost:8000 · interactive docs → http://localhost:8000/docs

### Locally

Requires a running Mongo — `docker compose up -d mongo` is enough.

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload
```

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `MONGO_URI` | Mongo connection string | `mongodb://localhost:27017/?directConnection=true` |
| `MONGO_DB` | database name | `forms` |
| `JWT_SECRET` | token signing secret | dev placeholder — set in production |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | access token lifetime | `30` |
| `DRAFT_TTL_SECONDS` | draft lifetime | `604800` (7 days) |
| `PUBLIC_RATE_LIMIT` | requests per window per IP on public endpoints | `30` |
| `PUBLIC_RATE_WINDOW_SECONDS` | rate-limit window | `60` |
| `MAX_UPLOAD_BYTES` | hard cap on a single uploaded file | `5242880` (5 MiB) |

## Tests & lint

Tests exercise the real database (`docker compose up -d mongo`), driven through `httpx`'s ASGI transport:

```bash
uv run pytest
uv run ruff check
```

## API

The full, interactive API reference is the OpenAPI/Swagger UI at [`/docs`](http://localhost:8000/docs) once the app is running.