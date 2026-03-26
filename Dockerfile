# syntax=docker/dockerfile:1
# ------------------------------------------------------------------------------
# Runner image: generates synthetic data and loads it into Postgres.
# Layer ordering is deliberate (see ADR-0002): the bits that change least are
# placed earliest so Docker's build cache is reused on every code-only change.
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS base

# Predictable, quiet Python in containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) System deps. Rarely change -> earliest layer. psycopg2-binary needs no
#    build toolchain, so we keep this tiny (libpq for runtime safety only).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 2) Python deps. Copy ONLY requirements first so this layer is cached until
#    the dependency set actually changes — editing app code won't reinstall.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 3) Application code. Changes most often -> last, so the expensive layers above
#    stay cached across ordinary code edits.
COPY data_generator/ ./data_generator/
COPY ingestion/ ./ingestion/

# 4) Non-root user for runtime (don't run app code as root).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/raw \
    && chown -R appuser:appuser /app
USER appuser

# ENTRYPOINT is the fixed program (python); CMD is the default, overridable args.
# `docker compose run runner python -m ingestion.load_to_postgres` overrides CMD.
ENTRYPOINT ["python"]
CMD ["-m", "data_generator.generate"]
