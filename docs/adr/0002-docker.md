# ADR 0002 — Containerization with Docker

- **Status:** Accepted
- **Phase:** 1 — Docker
- **Date:** 2026-03-30

## Context

The pipeline must run the same way on any machine: generate synthetic data and
load it into Postgres without a bespoke local setup. We need a reproducible
runtime image and a one-command local stack (Postgres + a runner), wired through
`.env`, that later phases (Airflow, Kafka) can compose with.

## Decision

- **Runner image** (`Dockerfile`, `python:3.11-slim`): a single image that both
  generates data (default `CMD`) and loads it (override the CMD). Slim base +
  `psycopg2-binary` means **no C build toolchain** is needed in the image.
- **Deliberate layer ordering** for build-cache efficiency, least-changing first:
  1. system libs (`libpq5`) — almost never change,
  2. `COPY requirements.txt` then `pip install` — changes only when deps change,
  3. `COPY` app code — changes on every edit,
  4. create the non-root user.
  Editing application code therefore reuses the cached dependency layer; we
  verified `pip install` stays `CACHED` after a code-only rebuild.
- **`ENTRYPOINT ["python"]` + `CMD ["-m", "data_generator.generate"]`**: the
  entrypoint fixes the *program* (python); the CMD supplies *default arguments*
  that are easy to override —
  `docker compose run --rm runner -m ingestion.load_to_postgres`.
- **Non-root runtime**: a dedicated `appuser` (uid 10001) owns `/app`; the
  container does not run as root.
- **`docker-compose.yml`**: `postgres:16` with a named volume (`pgdata`) and a
  `pg_isready` **healthcheck**; the runner `depends_on` Postgres
  `condition: service_healthy` so it never starts against a cold DB. A shared
  external network (`health-net`) lets later compose files (Airflow, Kafka) join.
- **`.dockerignore`** trims the build context to just the generator + ingestion
  code, keeping builds fast and ensuring data/secrets are never baked in.
- **Host port 5433 → container 5432** for Postgres, so the stack doesn't collide
  with a Postgres already running on the host's 5432 (overridable via
  `HOST_PG_PORT`).

## Alternatives considered

- **`python:3.11` (full) base** — rejected; ~3× larger for no benefit here.
- **Multi-stage build with a compiler** — unnecessary because `psycopg2-binary`
  ships wheels; a builder stage would add complexity for no size win.
- **Installing dbt/Spark into this image** — rejected; that would bloat the
  runner and couple unrelated phases. Each heavy tool gets its own image.
- **`command:` in compose instead of ENTRYPOINT/CMD** — the ENTRYPOINT/CMD split
  is more reusable and documents the program vs args distinction explicitly.

## Consequences

- One `docker compose up -d postgres` + two `docker compose run` commands take
  you from nothing to a loaded warehouse. Verified end-to-end on a clean engine.
- The shared network + healthcheck make Phases 4/6 composable.
- The image is ~667MB — acceptable for a pandas/pyarrow/numpy stack; documented
  rather than hidden.

## Interview check

**Why is each Dockerfile layer ordered as it is?**
Docker caches layers top-to-bottom and invalidates everything below the first
changed layer. Ordering least-volatile → most-volatile (system libs →
requirements+pip → app code) means an ordinary code edit only rebuilds the cheap
final COPY, not the expensive `pip install`. Copying `requirements.txt` *before*
the source is the linchpin: dependencies reinstall only when they actually change.

**`CMD` vs `ENTRYPOINT`?**
`ENTRYPOINT` is the executable that always runs (`python`); `CMD` provides the
default arguments (`-m data_generator.generate`) that callers can override
without restating the program. Together they make `docker compose run runner
-m ingestion.load_to_postgres` switch tasks cleanly. (If `ENTRYPOINT` is unset,
`CMD` is the whole command and is replaced entirely on override.)

**How is the image kept small?**
Slim base; `psycopg2-binary` to avoid a build toolchain; `--no-install-recommends`
plus `rm -rf /var/lib/apt/lists/*` for apt; `PIP_NO_CACHE_DIR`; a tight
`.dockerignore` so data, `.venv`, and other phases never enter the build context;
and not installing dbt/Spark into this image.
