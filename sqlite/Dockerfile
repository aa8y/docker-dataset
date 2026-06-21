# syntax=docker/dockerfile:1
#
# Two-stage, ETL-shaped build. Exactly one dataset per image.
#
# This is the SQLite counterpart of ../postgres/Dockerfile. SQLite is
# serverless -- a database is just a file -- so the pattern inverts: there is no
# server to boot and no /docker-entrypoint-initdb.d scripts to run at start.
# Instead the builder stage *builds the database file* (Extract -> Transform ->
# Load), and the final stage simply ships that file. Build tools live only in
# the builder, so the final image never carries them.
#
# Engine note. There is an Alpine-based SQLite image (the statically-linked
# `keinos/sqlite3`, multi-arch amd64 + arm64), so the final image is genuinely
# thin and Alpine-based. Its entrypoint is `tini` with `sqlite3` as the default
# command, so the CMD below opens the shipped database file directly.
#
# The Dockerfile is dataset-agnostic: nothing here names a specific dataset.
# A dataset is described either by a text SQL source (SQL_FILES, fed to the
# sqlite3 CLI to build the database) or by a prebuilt SQLite database file
# (DB_FILE, shipped as-is). Datasets with bespoke logic plug into the ETL steps
# without editing this file, via the convention-located
# scripts/<dataset>/{extract,transform,load} hooks.
#
# Data Sources.
# Chinook:   https://github.com/lerocha/chinook-database (vendor-specific
#            Chinook_Sqlite.sql release asset; native SQLite SQL script).
# Northwind: https://github.com/jpwhite3/northwind-SQLite3 (SQLite3 port of the
#            Microsoft Access Northwind sample, shipped as a prebuilt
#            dist/northwind.db).

# ---------------------------------------------------------------------------
# Builder: extract, transform, load.
# ---------------------------------------------------------------------------
FROM alpine:3.21 AS builder

ARG DATASET
# One URL or a space-separated list. Dispatched on suffix: *.git is cloned,
# *.tar.gz is streamed through tar, anything else is treated as a list of
# files to fetch individually (e.g. a .sql script or a prebuilt .db).
ARG EXTRACT_URL
# Ordered, space-separated paths (relative to the build dir) of text SQL files
# fed to the sqlite3 CLI to build the database. Mutually exclusive with DB_FILE.
ARG SQL_FILES
# Path (relative to the build dir) of a prebuilt SQLite database file to ship
# as-is. Mutually exclusive with SQL_FILES.
ARG DB_FILE
# apk packages beyond the shared set.
ARG EXTRA_PREREQS

WORKDIR /tmp/build
# Per-dataset ETL hooks, located by convention as scripts/<dataset>/<step>
# (extract|transform|load) and executed at the matching stage below if present.
# Hooks are extensionless and run via their shebang, so a hook may be written in
# any language whose interpreter is in the builder (bash always; others via
# EXTRA_PREREQS).
COPY scripts/ /usr/local/lib/scripts/

# Resilient download options shared by the extract step and any dataset extract
# hook (inherited via the environment). Upstreams return transient 5xx/429s
# under load; retry with backoff so a momentary hiccup doesn't fail the whole
# build. Builder-only, so it never leaks into the final image.
ENV WGET_OPTS="--tries=5 --waitretry=10 --timeout=30 --retry-connrefused --retry-on-host-error --retry-on-http-error=429,500,502,503,504"

# Upstream-content fingerprint, computed on the host from cheap source metadata
# by bin/dataset-checksum and passed in as a build arg. Referenced in the RUN
# below so a real upstream change busts this layer and cascades a rebuild
# through EXTRACT -> TRANSFORM -> LOAD, while an unchanged dataset reuses the
# registry cache. Builder-only, so it never leaks into the final image.
ARG DATASET_CHECKSUM=
RUN echo "dataset checksum: ${DATASET_CHECKSUM}"

# EXTRACT. Shared tools + per-dataset extras, then fetch by URL type and run an
# optional dataset extract hook.
RUN apk add --no-cache \
      bash \
      bzip2 \
      ca-certificates \
      git \
      sqlite \
      unzip \
      wget \
      $EXTRA_PREREQS && \
    bash -c ' \
      set -e; \
      case "$EXTRACT_URL" in \
        *.git)    git clone "$EXTRACT_URL" ;; \
        *.tar.gz) wget $WGET_OPTS -qO- "$EXTRACT_URL" | tar -xzf - ;; \
        *)        for u in $EXTRACT_URL; do wget $WGET_OPTS -q "$u"; done ;; \
      esac; \
      h="/usr/local/lib/scripts/${DATASET}/extract"; if [ -f "$h" ]; then "$h"; fi'

# TRANSFORM. Optional per-dataset transform hook.
RUN bash -c ' \
      set -e; \
      h="/usr/local/lib/scripts/${DATASET}/transform"; if [ -f "$h" ]; then "$h"; fi'

# LOAD. Build the database file at /data/${DATASET}.db -- either by feeding the
# text SQL_FILES to the sqlite3 CLI, or by shipping a prebuilt DB_FILE as-is --
# then run an optional dataset load hook.
RUN bash -c ' \
      set -e; \
      mkdir -p /data; \
      DB="/data/${DATASET}.db"; \
      if [ -n "$SQL_FILES" ]; then \
        for f in $SQL_FILES; do cat "$f"; echo; done | sqlite3 "$DB"; \
      elif [ -n "$DB_FILE" ]; then \
        cp "$DB_FILE" "$DB"; \
      else \
        echo "error: set either SQL_FILES (text SQL) or DB_FILE (prebuilt db)" >&2; exit 1; \
      fi; \
      h="/usr/local/lib/scripts/${DATASET}/load"; if [ -f "$h" ]; then "$h"; fi'

# ---------------------------------------------------------------------------
# Final image: thin Alpine SQLite + the assembled database file only.
# ---------------------------------------------------------------------------
FROM keinos/sqlite3:3.53.2

# Re-declared in this stage so the upstream-content fingerprint can be recorded
# on the final image (visible via `docker inspect`) for observability.
ARG DATASET_CHECKSUM=
LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="SQLite databases pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${DATASET_CHECKSUM}" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/sqlite-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/sqlite-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

ARG DATASET
# Recorded so the CMD can open the shipped database file by name at runtime.
ENV DATASET=${DATASET}

COPY --from=builder /data /data
WORKDIR /data

# Open the shipped database in the sqlite3 shell. The base image's entrypoint is
# tini, so this shell-form CMD is exec'd through it; ${DATASET} is resolved from
# the environment at start. Run with `-it` for an interactive session, or pass
# your own arguments (e.g. `... /usr/bin/sqlite3 /data/<dataset>.db "SELECT 1"`).
CMD /usr/bin/sqlite3 /data/${DATASET}.db
